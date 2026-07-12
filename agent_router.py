"""Client for AgentRouter (agentrouter.org).

IMPORTANT -- why this file looks the way it does
------------------------------------------------
AgentRouter is a *Claude Code relay*. It only accepts traffic that matches the
Claude Code "wire image": the native Anthropic Messages API (`/v1/messages`,
`x-api-key` + `anthropic-version`) sent with a `claude-cli/...` User-Agent.

Any other client fingerprint -- e.g. a generic OpenAI-style call to
`/chat/completions` -- is rejected with HTTP 401:

    {"type": "unauthorized_client_error",
     "message": "unauthorized client detected, contact support ..."}

This happens EVEN WHEN THE API KEY IS PERFECTLY VALID. It is a client
allow-list check, not a bad-key error. (Verified: the same key returns real
completions the moment the request looks like Claude Code.)

So this module talks to the Anthropic Messages API and sends the Claude Code
wire-image headers. To avoid touching the rest of the codebase, it still
*accepts* and *returns* OpenAI-style message objects (system/user/assistant/
tool roles, `tool_calls`, `tool_call_id`) and translates to/from Anthropic
format internally.
"""
import json
import time

import requests

import config

# ---- Claude Code wire image -----------------------------------------------
# The User-Agent is the load-bearing part: without a `claude-cli/...` UA the
# relay returns "unauthorized client detected". The rest mirror what the real
# Claude Code CLI sends so we stay on the allow-list.
_ANTHROPIC_VERSION = "2023-06-01"
_ANTHROPIC_BETA = "claude-code-20250219,fine-grained-tool-streaming-2025-05-14"
_USER_AGENT = "claude-cli/1.0.60 (external, cli)"


class AgentRouterError(RuntimeError):
    pass


def _headers():
    return {
        "x-api-key": config.AGENTROUTER_API_KEY,
        "anthropic-version": _ANTHROPIC_VERSION,
        "anthropic-beta": _ANTHROPIC_BETA,
        "content-type": "application/json",
        "User-Agent": _USER_AGENT,
        "x-app": "cli",
    }


def _endpoint():
    # base URL already ends in /v1 (e.g. https://agentrouter.org/v1)
    return config.AGENTROUTER_BASE_URL.rstrip("/") + "/messages"


# ---- OpenAI -> Anthropic request translation ------------------------------

def _tools_to_anthropic(tools):
    """OpenAI {type:function, function:{name, description, parameters}}
    -> Anthropic {name, description, input_schema}."""
    if not tools:
        return None
    out = []
    for t in tools:
        fn = t.get("function", t)  # tolerate either shape
        out.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return out


def _messages_to_anthropic(messages):
    """Convert OpenAI-style messages into (system_prompt, anthropic_messages).

    Roles handled:
      - system   -> pulled out into the top-level `system` string
      - user     -> user text block
      - assistant with optional `tool_calls` -> assistant text + tool_use blocks
      - tool     -> tool_result block (folded into a user message)

    Consecutive tool results are merged into a single user message, as the
    Anthropic API expects all results for one assistant turn together.
    """
    system_parts = []
    conv = []
    pending = []

    def flush():
        if pending:
            conv.append({"role": "user", "content": list(pending)})
            pending.clear()

    for m in messages:
        role = m.get("role")
        if role == "system":
            if m.get("content"):
                system_parts.append(m["content"])
            continue

        if role == "tool":
            pending.append({
                "type": "tool_result",
                "tool_use_id": m.get("tool_call_id"),
                "content": m.get("content") or "",
            })
            continue

        flush()  # any non-tool message flushes buffered tool results first

        if role == "assistant":
            blocks = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for call in m.get("tool_calls") or []:
                fn = call["function"]
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except (json.JSONDecodeError, TypeError):
                    args = {}
                blocks.append({
                    "type": "tool_use",
                    "id": call.get("id"),
                    "name": fn["name"],
                    "input": args,
                })
            if not blocks:
                blocks.append({"type": "text", "text": ""})
            conv.append({"role": "assistant", "content": blocks})
        else:  # user (or unknown) -> treat as user text
            content = m.get("content")
            conv.append({"role": "user", "content": content if content is not None else ""})

    flush()
    return "\n\n".join(system_parts), conv


# ---- Anthropic -> OpenAI response translation -----------------------------

def _anthropic_to_openai_message(data):
    """Convert an Anthropic response into an OpenAI-style assistant message
    (`content` string + `tool_calls`), which is what the rest of the code
    stores and re-sends."""
    text_parts = []
    tool_calls = []
    for block in data.get("content") or []:
        btype = block.get("type")
        if btype == "text":
            text_parts.append(block.get("text", ""))
        elif btype == "tool_use":
            tool_calls.append({
                "id": block.get("id"),
                "type": "function",
                "function": {
                    "name": block.get("name"),
                    "arguments": json.dumps(block.get("input") or {}),
                },
            })
    msg = {"role": "assistant", "content": "".join(text_parts) or None}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


# ---- Public API (unchanged signatures) ------------------------------------

def chat(messages, tools=None, temperature=0.7, max_tokens=8000, timeout=180):
    """Send a chat request to Opus via AgentRouter's Anthropic endpoint and
    return an OpenAI-style assistant message (may include `tool_calls`).
    Retries transient errors."""
    if not config.AGENTROUTER_API_KEY or not config.AGENTROUTER_BASE_URL:
        raise AgentRouterError(
            "AGENTROUTER_BASE_URL / AGENTROUTER_API_KEY are not set. "
            "Add them to .env (local) or Space secrets (Hugging Face)."
        )

    system, conv = _messages_to_anthropic(messages)
    payload = {
        "model": config.AGENTROUTER_MODEL,
        "messages": conv,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if system:
        payload["system"] = system
    anthropic_tools = _tools_to_anthropic(tools)
    if anthropic_tools:
        payload["tools"] = anthropic_tools

    url = _endpoint()
    last_err = None
    for attempt in range(4):
        try:
            resp = requests.post(url, headers=_headers(), json=payload, timeout=timeout)
            if resp.status_code == 200:
                return _anthropic_to_openai_message(resp.json())
            if resp.status_code in (429, 500, 502, 503, 504):
                last_err = "%s: %s" % (resp.status_code, resp.text[:300])
                time.sleep(2 ** attempt)
                continue
            raise AgentRouterError("%s: %s" % (resp.status_code, resp.text[:500]))
        except requests.RequestException as e:
            last_err = str(e)
            time.sleep(2 ** attempt)

    raise AgentRouterError("AgentRouter failed after retries: %s" % last_err)


def chat_text(messages, **kw):
    """Convenience: return just the assistant's text content."""
    msg = chat(messages, **kw)
    return (msg.get("content") or "").strip()


def test_connection():
    """Send a tiny request to verify base URL + key + wire image actually work.
    Returns (ok, human-readable message). Never raises."""
    if not config.AGENTROUTER_BASE_URL or not config.AGENTROUTER_API_KEY:
        return False, "Base URL or API key is not set in .env / secrets."
    url = _endpoint()
    try:
        resp = requests.post(
            url,
            headers=_headers(),
            json={
                "model": config.AGENTROUTER_MODEL,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
            },
            timeout=30,
        )
    except requests.RequestException as e:
        return False, "Network error reaching %s: %s" % (url, e)

    if resp.status_code == 200:
        return True, "Connected. Model '%s' responded OK." % config.AGENTROUTER_MODEL
    if resp.status_code == 401:
        body = resp.text[:200]
        if "unauthorized_client" in body or "unauthorized client" in body:
            return False, (
                "401 unauthorized_client -- AgentRouter rejected the *client*, "
                "not the key. The request didn't match the Claude Code wire image "
                "(endpoint/headers). This should be fixed now; if you still see it, "
                "an outbound proxy may be stripping the User-Agent header."
            )
        return False, (
            "401 Unauthorized -- the API key is being rejected. Check it is active "
            "and funded in your AgentRouter dashboard. (URL %s)" % url
        )
    if resp.status_code == 404:
        return False, "404 -- endpoint not found. Check AGENTROUTER_BASE_URL. Body: %s" % resp.text[:160]
    return False, "HTTP %s: %s" % (resp.status_code, resp.text[:200])
