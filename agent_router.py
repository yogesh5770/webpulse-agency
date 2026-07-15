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

    models_to_try = ["gemini-3.5-flash", "gemini-3.1-pro-preview", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
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
                
                # If quota/prepayment depleted or suspended, additional model requests for this key will fail as well.
                if resp.status_code in (403, 429):
                    break
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


def _try_deepseek_direct(messages, tools, temperature, max_tokens, timeout):
    if not config.DEEPSEEK_API_KEYS:
        raise AgentRouterError("DeepSeek direct keys not set.")

    # Clean OpenAI-compatible messages
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
        "model": "deepseek-chat",
        "messages": clean_messages,
        "temperature": temperature,
        "max_tokens": min(max_tokens or 4096, 4096),
    }
    if tools:
        payload["tools"] = tools

    last_err = None
    for key in config.DEEPSEEK_API_KEYS:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}"
        }
        url = "https://api.deepseek.com/chat/completions"
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 200:
                result = resp.json()
                choice = result["choices"][0]["message"]
                out_msg = {"role": "assistant", "content": choice.get("content")}
                if choice.get("tool_calls"):
                    out_msg["tool_calls"] = choice["tool_calls"]
                return out_msg
            logger.warning(f"DeepSeek key failed: HTTP {resp.status_code} {resp.text[:150]}")
            last_err = f"HTTP {resp.status_code}: {resp.text[:150]}"
        except Exception as e:
            logger.warning(f"DeepSeek key exception: {e}")
            last_err = str(e)
            continue

    raise AgentRouterError(f"All DeepSeek keys exhausted. Last error: {last_err}")


def _try_bedrock_direct(messages, tools, temperature, max_tokens, timeout):
    # First, check which Bedrock authentication mode to use
    if config.AWS_BEARER_TOKEN_BEDROCK:
        # Use Bedrock bearer token mode
        logger.info("Using Bedrock bearer token mode")
        
        # Clean and convert messages to Bedrock converse API format
        system_prompt_parts = []
        conv = []
        for m in messages:
            role = m.get("role")
            content = m.get("content") or ""
            if role == "system":
                system_prompt_parts.append(content)
                continue
            # Bedrock expects 'user' or 'assistant' roles
            bedrock_role = "user" if role == "user" else "assistant"
            conv.append({
                "role": bedrock_role,
                "content": [{"text": content}]
            })
        
        # Build Bedrock converse API payload
        native_request = {
            "messages": conv,
            "inferenceConfig": {
                "temperature": temperature or 0.7,
                "maxTokens": max_tokens or 4096
            }
        }
        if system_prompt_parts:
            native_request["system"] = [{"text": " ".join(system_prompt_parts)}]
        
        # Try models in order of preference: Claude 3.5 Sonnet (APAC) → Claude 3.5 Haiku (APAC) → Claude 3.5 Sonnet v2 → Claude 3.5 Sonnet v1 → Claude 3 Haiku
        model_ids_to_try = [
            "apac.anthropic.claude-3-5-sonnet-20241022-v2:0",
            "apac.anthropic.claude-3-5-haiku-20241022-v1:0",
            "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "anthropic.claude-3-5-sonnet-20240620-v1:0",
            "anthropic.claude-3-haiku-20240307-v1:0",
            "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
        ]
        
        last_error = None
        for model_id in model_ids_to_try:
            try:
                logger.info(f"Trying Bedrock model (bearer token): {model_id}")
                url = f"{config.BEDROCK_BASE_URL.rstrip('/')}/model/{model_id}/converse"
                
                # Bedrock bearer token uses Authorization: Bearer header
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {config.AWS_BEARER_TOKEN_BEDROCK}"
                }
                
                resp = requests.post(url, headers=headers, json=native_request, timeout=timeout)
                if resp.status_code == 200:
                    # Parse Bedrock converse API response
                    response_json = resp.json()
                    output_message = response_json["output"]["message"]
                    text_content = "".join([
                        block["text"] for block in output_message.get("content", [])
                        if "text" in block
                    ])
                    return {"role": "assistant", "content": text_content}
                
                logger.warning(f"Bedrock bearer token model {model_id} failed: HTTP {resp.status_code} {resp.text[:150]}")
                last_error = f"HTTP {resp.status_code}: {resp.text[:150]}"
            except Exception as e:
                logger.warning(f"Bedrock bearer token model {model_id} exception: {e}")
                last_error = str(e)
                continue
        
        raise AgentRouterError(f"All Bedrock bearer token models failed. Last error: {last_error}")
    elif config.BEDROCK_API_KEY:
        # Use Bedrock long-term API key mode
        logger.info("Using Bedrock long-term API key mode")
        
        # Clean and convert messages to Bedrock converse API format
        system_prompt_parts = []
        conv = []
        for m in messages:
            role = m.get("role")
            content = m.get("content") or ""
            if role == "system":
                system_prompt_parts.append(content)
                continue
            # Bedrock expects 'user' or 'assistant' roles
            bedrock_role = "user" if role == "user" else "assistant"
            conv.append({
                "role": bedrock_role,
                "content": [{"text": content}]
            })
        
        # Build Bedrock converse API payload
        native_request = {
            "messages": conv,
            "inferenceConfig": {
                "temperature": temperature or 0.7,
                "maxTokens": max_tokens or 4096
            }
        }
        if system_prompt_parts:
            native_request["system"] = [{"text": " ".join(system_prompt_parts)}]
        
        # Try models in order of preference: Claude 3.5 Sonnet (APAC) → Claude 3.5 Haiku (APAC) → Claude 3.5 Sonnet v2 → Claude 3.5 Sonnet v1 → Claude 3 Haiku
        model_ids_to_try = [
            "apac.anthropic.claude-3-5-sonnet-20241022-v2:0",
            "apac.anthropic.claude-3-5-haiku-20241022-v1:0",
            "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "anthropic.claude-3-5-sonnet-20240620-v1:0",
            "anthropic.claude-3-haiku-20240307-v1:0",
            "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
        ]
        
        last_error = None
        for model_id in model_ids_to_try:
            try:
                logger.info(f"Trying Bedrock model (long-term API key): {model_id}")
                url = f"{config.BEDROCK_BASE_URL.rstrip('/')}/model/{model_id}/converse"
                
                # Bedrock long-term API key uses the X-Amz-Bedrock-Api-Key header
                headers = {
                    "Content-Type": "application/json",
                    "X-Amz-Bedrock-Api-Key": config.BEDROCK_API_KEY
                }
                
                resp = requests.post(url, headers=headers, json=native_request, timeout=timeout)
                if resp.status_code == 200:
                    # Parse Bedrock converse API response
                    response_json = resp.json()
                    output_message = response_json["output"]["message"]
                    text_content = "".join([
                        block["text"] for block in output_message.get("content", [])
                        if "text" in block
                    ])
                    return {"role": "assistant", "content": text_content}
                
                logger.warning(f"Bedrock API key model {model_id} failed: HTTP {resp.status_code} {resp.text[:150]}")
                last_error = f"HTTP {resp.status_code}: {resp.text[:150]}"
            except Exception as e:
                logger.warning(f"Bedrock API key model {model_id} exception: {e}")
                last_error = str(e)
                continue
        
        raise AgentRouterError(f"All Bedrock API key models failed. Last error: {last_error}")
    elif config.AWS_ACCESS_KEY_ID and config.AWS_SECRET_ACCESS_KEY:
        # Use AWS credentials mode (real Bedrock)
        logger.info("Using Bedrock AWS credentials mode")
        import boto3
        from botocore.config import Config

        # Clean and convert messages to Bedrock format
        system_prompt_parts = []
        conv = []
        for m in messages:
            role = m.get("role")
            content = m.get("content") or ""
            if role == "system":
                system_prompt_parts.append(content)
                continue
            # Bedrock expects 'user' or 'assistant' roles
            bedrock_role = "user" if role == "user" else "assistant"
            conv.append({
                "role": bedrock_role,
                "content": [{"text": content}]
            })

        # Create Bedrock client
        bedrock_config = Config(
            region_name=config.AWS_REGION or "us-east-1",
            connect_timeout=timeout,
            read_timeout=timeout
        )
        bedrock_runtime = boto3.client(
            "bedrock-runtime",
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            config=bedrock_config
        )

        # Build native request with correct structure
        native_request = {
            "messages": conv,
            "inferenceConfig": {
                "temperature": temperature or 0.7,
                "maxTokens": max_tokens or 4096
            }
        }
        if system_prompt_parts:
            native_request["system"] = [{"text": " ".join(system_prompt_parts)}]
        
        # Try models in order of preference: Claude 3.5 Sonnet (APAC) → Claude 3.5 Haiku (APAC) → Claude 3.5 Sonnet v2 → Claude 3.5 Sonnet v1 → Claude 3 Haiku
        model_ids_to_try = [
            "apac.anthropic.claude-3-5-sonnet-20241022-v2:0",
            "apac.anthropic.claude-3-5-haiku-20241022-v1:0",
            "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "anthropic.claude-3-5-sonnet-20240620-v1:0",
            "anthropic.claude-3-haiku-20240307-v1:0",
            "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
        ]
        
        last_error = None
        for model_id in model_ids_to_try:
            try:
                logger.info(f"Trying Bedrock model (AWS): {model_id}")
                # Invoke Bedrock model using converse API
                response = bedrock_runtime.converse(
                    modelId=model_id,
                    **native_request
                )
                
                # Parse response
                output_message = response["output"]["message"]
                text_content = "".join([
                    block["text"] for block in output_message.get("content", [])
                    if "text" in block
                ])
                
                return {"role": "assistant", "content": text_content}
            except Exception as e:
                logger.warning(f"Bedrock AWS model {model_id} failed: {e}")
                last_error = e
                continue
        
        raise AgentRouterError(f"All Bedrock AWS models failed. Last error: {last_error}")
    else:
        raise AgentRouterError("Neither Bedrock API key nor AWS credentials set.")


# ---- Public Entrypoint with Failover Router ----

def chat(messages, tools=None, temperature=0.7, max_tokens=8000, timeout=25):
    """Sends chat request using ONLY Bedrock (per user request)."""
    if not (config.AWS_BEARER_TOKEN_BEDROCK or config.BEDROCK_API_KEY or (config.AWS_ACCESS_KEY_ID and config.AWS_SECRET_ACCESS_KEY)):
        raise AgentRouterError("Neither Bedrock bearer token, API key, nor AWS credentials set.")
    
    try:
        logger.info("Attempting API call using Bedrock Direct...")
        return _try_bedrock_direct(messages, tools, temperature, max_tokens, timeout)
    except Exception as e:
        logger.error(f"Bedrock Direct failed: {e}")
        raise AgentRouterError(f"Bedrock failed: {e}")


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
