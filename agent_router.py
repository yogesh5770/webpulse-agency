"""Client for AgentRouter with fallback support for direct Anthropic, Gemini,
and OpenAI APIs.

If the primary API (AgentRouter) is rate-limited or fails, this module
automatically falls back to direct API keys configured in .env:
1. AgentRouter
2. Anthropic Direct (Claude 3.5 Sonnet)
3. Google Gemini Direct (Gemini 1.5 Pro / 2.5 Flash)
4. OpenAI Direct (GPT-4o / GPT-4o-mini / DeepSeek)
"""
import json
import time
import requests
import logging
import config

logger = logging.getLogger(__name__)

# Anthropic wire settings
_ANTHROPIC_VERSION = "2023-06-01"
_ANTHROPIC_BETA = "claude-code-20250219,fine-grained-tool-streaming-2025-05-14"
_USER_AGENT = "claude-cli/1.0.60 (external, cli)"


class AgentRouterError(RuntimeError):
    pass


# ---- Helper translations between formats ----

def _tools_to_anthropic(tools):
    if not tools:
        return None
    out = []
    for t in tools:
        fn = t.get("function", t)
        out.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return out


def _messages_to_anthropic(messages):
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

        flush()

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
        else:
            content = m.get("content")
            conv.append({"role": "user", "content": content if content is not None else ""})

    flush()
    return "\n\n".join(system_parts), conv


def _anthropic_to_openai_message(data):
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


# ---- Direct API implementations ----

def _try_agent_router(messages, tools, temperature, max_tokens, timeout):
    if not config.AGENTROUTER_API_KEYS or not config.AGENTROUTER_BASE_URL:
        raise AgentRouterError("AgentRouter not configured.")

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

    url = config.AGENTROUTER_BASE_URL.rstrip("/") + "/messages"
    last_err = None

    # Rotate through all loaded keys
    for key in config.AGENTROUTER_API_KEYS:
        headers = {
            "x-api-key": key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "anthropic-beta": _ANTHROPIC_BETA,
            "content-type": "application/json",
            "User-Agent": _USER_AGENT,
            "x-app": "cli",
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 200:
                return _anthropic_to_openai_message(resp.json())
            logger.warning(f"AgentRouter key failed ({key[:10]}...): HTTP {resp.status_code} {resp.text[:150]}")
            last_err = f"HTTP {resp.status_code}: {resp.text[:150]}"
        except Exception as e:
            logger.warning(f"AgentRouter key exception ({key[:10]}...): {e}")
            last_err = str(e)
            continue

    raise AgentRouterError(f"All AgentRouter keys exhausted. Last error: {last_err}")


def _try_anthropic_direct(messages, tools, temperature, max_tokens, timeout):
    if not config.ANTHROPIC_API_KEY:
        raise AgentRouterError("Anthropic direct key not set.")

    system, conv = _messages_to_anthropic(messages)
    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "messages": conv,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if system:
        payload["system"] = system
    anthropic_tools = _tools_to_anthropic(tools)
    if anthropic_tools:
        payload["tools"] = anthropic_tools

    headers = {
        "x-api-key": config.ANTHROPIC_API_KEY,
        "anthropic-version": _ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    url = "https://api.anthropic.com/v1/messages"
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code == 200:
        return _anthropic_to_openai_message(resp.json())
    raise AgentRouterError(f"Anthropic HTTP {resp.status_code}: {resp.text[:300]}")


def _try_gemini_direct(messages, tools, temperature, max_tokens, timeout):
    if not config.GEMINI_API_KEYS:
        raise AgentRouterError("Gemini direct keys not set.")

    # Clean OpenAI-compatible messages for Google
    clean_messages = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        msg_obj = {"role": role, "content": content}
        if m.get("tool_calls"):
            msg_obj["tool_calls"] = m["tool_calls"]
        if m.get("tool_call_id"):
            msg_obj["tool_call_id"] = m["tool_call_id"]
        clean_messages.append(msg_obj)

    payload = {
        "messages": clean_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools

    models_to_try = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash", "gemini-2.5-flash"]
    last_err = None
    # Rotate through all loaded keys
    for key in config.GEMINI_API_KEYS:
        url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}"
        }
        for model in models_to_try:
            payload["model"] = model
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
                if resp.status_code == 200:
                    result = resp.json()
                    choice = result["choices"][0]["message"]
                    out_msg = {"role": "assistant", "content": choice.get("content")}
                    if choice.get("tool_calls"):
                        out_msg["tool_calls"] = choice["tool_calls"]
                    return out_msg
                logger.warning(f"Gemini key failed ({key[:10]}...) for model {model}: HTTP {resp.status_code} {resp.text[:150]}")
                last_err = f"Model {model} - HTTP {resp.status_code}: {resp.text[:150]}"
            except Exception as e:
                logger.warning(f"Gemini key exception ({key[:10]}...) for model {model}: {e}")
                last_err = f"Model {model} - {e}"
                continue

    raise AgentRouterError(f"All Gemini keys and models exhausted. Last error: {last_err}")


def _try_openai_direct(messages, tools, temperature, max_tokens, timeout):
    if not config.OPENAI_API_KEY:
        raise AgentRouterError("OpenAI direct key not set.")

    clean_messages = []
    for m in messages:
        role = m.get("role")
        content = m.get("content") or ""
        clean_messages.append({"role": role, "content": content})

    payload = {
        "model": "gpt-4o",
        "messages": clean_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {config.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    url = "https://api.openai.com/v1/chat/completions"
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code == 200:
        result = resp.json()
        choice = result["choices"][0]["message"]
        return {"role": "assistant", "content": choice.get("content")}
    raise AgentRouterError(f"OpenAI HTTP {resp.status_code}: {resp.text[:300]}")


# ---- Public Entrypoint with Failover Router ----

def chat(messages, tools=None, temperature=0.7, max_tokens=8000, timeout=180):
    """Sends chat request. Retries and fails over across active providers.
    Prioritizes Gemini Direct (which offers a robust free tier) if the key is present.
    """
    providers = []
    # If Gemini direct key is set, prioritize it for the free tier
    if config.GEMINI_API_KEY:
        providers.append(("Gemini Direct", _try_gemini_direct))
        
    # Add other providers
    if config.AGENTROUTER_API_KEY:
        providers.append(("AgentRouter", _try_agent_router))
    if config.ANTHROPIC_API_KEY:
        providers.append(("Anthropic Direct", _try_anthropic_direct))
    if config.OPENAI_API_KEY:
        providers.append(("OpenAI Direct", _try_openai_direct))

    # Fallback to check all if none are explicitly matching active flags
    if not providers:
        providers = [
            ("Gemini Direct", _try_gemini_direct),
            ("AgentRouter", _try_agent_router),
            ("Anthropic Direct", _try_anthropic_direct),
            ("OpenAI Direct", _try_openai_direct)
        ]

    last_error = None
    for name, method in providers:
        try:
            logger.info(f"Attempting API call using {name}...")
            return method(messages, tools, temperature, max_tokens, timeout)
        except Exception as e:
            logger.warning(f"Provider {name} failed: {e}")
            last_error = str(e)
            continue

    raise AgentRouterError(f"All AI providers failed. Last error: {last_error}")


def chat_text(messages, **kw):
    msg = chat(messages, **kw)
    return (msg.get("content") or "").strip()


def test_connection():
    """Verify that at least one provider is responsive."""
    try:
        reply = chat([{"role": "user", "content": "ping"}], max_tokens=5)
        return True, f"Connection OK. Response: {reply.get('content') or '(empty)'}"
    except Exception as e:
        return False, f"All connections failed: {e}"
