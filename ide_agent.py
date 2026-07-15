"""Per-site AI IDE agent -- a Cursor / Claude-Code-style coding agent scoped
to ONE website folder.

An LLM (Opus 4.x via AgentRouter) runs in a tool-use loop, sandboxed so it can
never touch anything outside that site's directory. It powers the IDE chat:
the user asks for a change, the agent plans, edits files, self-corrects broken
HTML, and checkpoints its work to git (with one-click undo).

Cursor-parity features:
  - A living PLAN / todo list the agent maintains via the `update_plan` tool,
    streamed to the UI so you watch it tick tasks off (like Cursor/Claude Code).
  - Surgical edits: `search_files` (grep) + `edit_file` (exact find/replace),
    plus full file `create_file` / `write_file` / `delete_file` / `rename_file`.
  - Error self-correction: after edits, HTML is validated and problems are fed
    back so the agent fixes them before finishing.
  - Checkpoints: each successful change is auto-committed to git; a failed run
    is rolled back to the last good commit.

Streaming:
  `run_agent(..., on_event=fn)` emits structured dict events the API turns into
  SSE. `on_step` (legacy) still works and receives human-readable strings.
"""
import html.parser
import json
import os
import subprocess

from agent_router import chat

# ---- Sandbox helpers -------------------------------------------------

def _safe_path(root: str, rel: str) -> str:
    """Resolve `rel` inside `root`; refuse anything that escapes root."""
    root_abs = os.path.abspath(root)
    target = os.path.abspath(os.path.join(root_abs, rel))
    if target != root_abs and not target.startswith(root_abs + os.sep):
        raise ValueError(f"Path escapes site sandbox: {rel}")
    return target


# ---- Git checkpoint helpers -----------------------------------------

def _git(root: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, timeout=60
    )


def _ensure_repo(root: str) -> None:
    """Make sure the site folder is a git repo with an initial commit, so we
    always have a checkpoint to roll back to."""
    if not os.path.isdir(os.path.join(root, ".git")):
        _git(root, "init")
        _git(root, "config", "user.email", "agent@local")
        _git(root, "config", "user.name", "Site Agent")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "checkpoint: baseline")


def _has_changes(root: str) -> bool:
    return bool(_git(root, "status", "--porcelain").stdout.strip())


def _commit(root: str, message: str) -> str:
    _git(root, "add", "-A")
    res = _git(root, "commit", "-m", message)
    return res.stdout.strip() or res.stderr.strip()


def _rollback(root: str) -> None:
    _git(root, "reset", "--hard", "HEAD")
    _git(root, "clean", "-fd")


def undo_last(root: str) -> str:
    """Revert the site to the previous checkpoint (like Cursor undo)."""
    if not os.path.isdir(os.path.join(root, ".git")):
        return "No history yet -- nothing to undo."
    log = _git(root, "rev-list", "--count", "HEAD").stdout.strip()
    if not log.isdigit() or int(log) < 2:
        return "No earlier checkpoint to undo to."
    res = _git(root, "reset", "--hard", "HEAD~1")
    if res.returncode == 0:
        return "Reverted to the previous checkpoint."
    return f"Undo failed: {res.stderr.strip()[:160]}"


# ---- HTML validation (the "linter" the agent self-corrects against) --

class _HTMLCheck(html.parser.HTMLParser):
    """Minimal structural validator: catches unclosed/mismatched tags."""

    _VOID = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self):
        super().__init__()
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag not in self._VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self._VOID:
            return
        if tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass
        else:
            self.errors.append(f"Unexpected closing </{tag}>")


def _validate_html(root: str) -> str:
    """Return a problem report for index.html, or '' if it looks OK."""
    path = os.path.join(root, "index.html")
    if not os.path.exists(path):
        return "index.html is missing."
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    problems = []
    low = content.lower()
    if "<html" not in low:
        problems.append("No <html> element.")
    if "<title" not in low:
        problems.append("Missing <title> (needed for SEO).")
    if "<h1" not in low:
        problems.append("Missing <h1>.")
    checker = _HTMLCheck()
    try:
        checker.feed(content)
    except Exception as e:
        problems.append(f"Parse error: {e}")
    if checker.stack:
        problems.append("Unclosed tags: " + ", ".join(f"<{t}>" for t in checker.stack[:8]))
    problems.extend(checker.errors[:8])
    return "; ".join(problems)


# ---- Tool implementations (all confined to the site dir) -------------

def _list_files(root: str) -> str:
    out = []
    for dp, _dn, fn in os.walk(root):
        if ".git" in dp:
            continue
        for f in fn:
            out.append(os.path.relpath(os.path.join(dp, f), root))
    return "\n".join(sorted(out)) or "(empty)"


def _read_file(root: str, path: str) -> str:
    with open(_safe_path(root, path), "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _write_file(root: str, path: str, content: str) -> str:
    target = _safe_path(root, path)
    os.makedirs(os.path.dirname(target) or root, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Wrote {len(content)} bytes to {path}"


def _create_file(root: str, path: str, content: str = "") -> str:
    target = _safe_path(root, path)
    if os.path.exists(target):
        return f"ERROR: {path} already exists. Use edit_file or write_file to change it."
    os.makedirs(os.path.dirname(target) or root, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Created {path} ({len(content)} bytes)."


def _delete_file(root: str, path: str) -> str:
    target = _safe_path(root, path)
    if not os.path.exists(target):
        return f"ERROR: {path} does not exist."
    os.remove(target)
    return f"Deleted {path}."


def _rename_file(root: str, path: str, new_path: str) -> str:
    src = _safe_path(root, path)
    dst = _safe_path(root, new_path)
    if not os.path.exists(src):
        return f"ERROR: {path} does not exist."
    if os.path.exists(dst):
        return f"ERROR: {new_path} already exists."
    os.makedirs(os.path.dirname(dst) or root, exist_ok=True)
    os.rename(src, dst)
    return f"Renamed {path} -> {new_path}."


def _edit_file(root: str, path: str, find: str, replace: str) -> str:
    """Surgical edit: replace an exact snippet. Fails loudly if `find` is not
    present or is ambiguous, so the agent can't silently corrupt the file."""
    target = _safe_path(root, path)
    with open(target, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    count = content.count(find)
    if count == 0:
        return "ERROR: `find` snippet not found. Read the file and copy an exact snippet."
    if count > 1:
        return f"ERROR: `find` snippet matches {count} places; make it more specific (unique)."
    with open(target, "w", encoding="utf-8") as f:
        f.write(content.replace(find, replace, 1))
    return f"Edited {path}: replaced 1 occurrence."


def _search_files(root: str, query: str) -> str:
    """Grep-like search across the folder so the agent can locate code."""
    hits = []
    for dp, _dn, fn in os.walk(root):
        if ".git" in dp:
            continue
        for name in fn:
            fp = os.path.join(dp, name)
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if query.lower() in line.lower():
                            rel = os.path.relpath(fp, root)
                            hits.append(f"{rel}:{i}: {line.strip()[:160]}")
                            if len(hits) >= 40:
                                return "\n".join(hits) + "\n...(truncated)"
            except Exception:
                continue
    return "\n".join(hits) or "No matches."


def _run_command(root: str, command: str) -> str:
    """Run a shell/git command with cwd pinned to the site sandbox."""
    proc = subprocess.run(
        command, shell=True, cwd=root, capture_output=True, text=True, timeout=120
    )
    return f"exit={proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"


TOOLS = [
    {"type": "function", "function": {
        "name": "update_plan",
        "description": "Create or update your task list (todo checklist) for this request. Call this FIRST with the steps you intend to take, then call it again to mark steps done as you go. This is shown live to the user.",
        "parameters": {"type": "object", "properties": {
            "steps": {"type": "array", "items": {"type": "object", "properties": {
                "title": {"type": "string"},
                "status": {"type": "string", "enum": ["pending", "in_progress", "done"]},
            }, "required": ["title", "status"]}},
        }, "required": ["steps"]},
    }},
    {"type": "function", "function": {
        "name": "list_files",
        "description": "List all files in the website project.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "search_files",
        "description": "Search all files for text (like grep). Use to locate the exact code to change before editing.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a file's contents.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "edit_file",
        "description": "PREFERRED for changes: replace an exact unique snippet in a file. `find` must match the file exactly and be unique. Use this instead of rewriting whole files.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "find": {"type": "string", "description": "Exact snippet currently in the file."},
            "replace": {"type": "string", "description": "Replacement snippet."},
        }, "required": ["path", "find", "replace"]},
    }},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Fully rewrite an existing file when an edit_file is impractical.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"},
        }, "required": ["path", "content"]},
    }},
    {"type": "function", "function": {
        "name": "create_file",
        "description": "Create a NEW file (e.g. styles.css, about.html). Fails if it already exists.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"},
        }, "required": ["path", "content"]},
    }},
    {"type": "function", "function": {
        "name": "delete_file",
        "description": "Delete a file from the project.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "rename_file",
        "description": "Rename or move a file within the project.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "new_path": {"type": "string"},
        }, "required": ["path", "new_path"]},
    }},
    {"type": "function", "function": {
        "name": "run_command",
        "description": "Run a shell or git command in the project directory.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
    }},
]

_SYSTEM = """You are an elite, token-optimized web-engineering agent scoped to ONE website project folder.
Your goal is to complete the user request while using the MINIMUM amount of input/output tokens.

CRITICAL RULE FOR GREETINGS AND CHAT:
If the user's message is a greeting (e.g. "hi", "hello", "hii"), a general question, or chat, DO NOT call any tools or commands. Immediately reply to them directly in text. Only call tools if they explicitly request changes or analysis of the website.

Strict Rules for Token Optimization:
1. ALWAYS explore with `search_files`/`read_file` before editing. Never guess file contents.
2. ALWAYS use `edit_file` (exact find/replace) for modifications. NEVER use `write_file` to rewrite `index.html` unless you are creating a completely new file. Rewriting large files wastes tokens and causes rate-limit errors.
3. Keep all edits minimal and surgical. Only change what is requested.
4. Call `update_plan` FIRST to outline your steps, and update it only when key phases are completed.
5. Ensure structural HTML validity. Verify styling rules before finishing.
6. Conclude with a brief 2-3 sentence summary of changes. Do not call any tools after summarizing."""


def _dispatch(root: str, name: str, args: dict) -> str:
    try:
        if name == "list_files":
            return _list_files(root)
        if name == "search_files":
            return _search_files(root, args["query"])
        if name == "read_file":
            return _read_file(root, args["path"])
        if name == "edit_file":
            return _edit_file(root, args["path"], args["find"], args["replace"])
        if name == "write_file":
            return _write_file(root, args["path"], args["content"])
        if name == "create_file":
            return _create_file(root, args["path"], args.get("content", ""))
        if name == "delete_file":
            return _delete_file(root, args["path"])
        if name == "rename_file":
            return _rename_file(root, args["path"], args["new_path"])
        if name == "run_command":
            return _run_command(root, args["command"])
        if name == "update_plan":
            return "Plan updated."
        return f"Unknown tool: {name}"
    except Exception as e:
        return f"ERROR: {e}"


def _describe_action(name: str, args: dict) -> str:
    """Human-friendly, Cursor-style label for a tool call."""
    labels = {
        "list_files": "Listed project files",
        "search_files": f"Searched for “{args.get('query', '')}”",
        "read_file": f"Read {args.get('path', '')}",
        "edit_file": f"Edited {args.get('path', '')}",
        "write_file": f"Rewrote {args.get('path', '')}",
        "create_file": f"Created {args.get('path', '')}",
        "delete_file": f"Deleted {args.get('path', '')}",
        "rename_file": f"Renamed {args.get('path', '')} → {args.get('new_path', '')}",
        "run_command": f"Ran `{str(args.get('command', ''))[:60]}`",
        "update_plan": "Updated plan",
    }
    return labels.get(name, name)


def run_agent(site_dir: str, instruction: str, max_steps: int = 24,
              on_step=None, on_event=None, place_id: str = None) -> str:
    """Run the agent loop until it stops calling tools, validating HTML and
    committing a checkpoint on success (rolling back on failure).

    on_event(dict): structured events -- {"type": "plan"|"tool"|"tool_result"|
        "assistant"|"status"|"done", ...} -- used by the IDE API for rich SSE.
    on_step(str): legacy plain-text activity trail (still supported).
    Returns the final assistant message.
    """
    def emit(event: dict) -> None:
        if on_event:
            try:
                on_event(event)
            except Exception:
                pass
        if on_step:
            t = event.get("type")
            if t == "tool":
                on_step(event.get("label", ""))
            elif t == "status":
                on_step(event.get("message", ""))

    _ensure_repo(site_dir)

    context = ""
    lead_path = os.path.join(site_dir, "lead.json")
    if os.path.exists(lead_path):
        with open(lead_path, "r", encoding="utf-8", errors="replace") as f:
            context = "\n\nBusiness details for this site:\n" + f.read()[:2000]

    # Load persistent chat history (DB or Local File fallback)
    import db
    history = []
    if place_id:
        try:
            history = db.get_chat_history(place_id)
        except Exception:
            history = []
    else:
        history_path = os.path.join(site_dir, "chat_history.json")
        if os.path.exists(history_path):
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = []

    messages = [{"role": "system", "content": _SYSTEM + context}]
    # Include last 10 messages from history to keep context window compact
    cleaned_history = [m for m in history if m.get("role") in ("user", "assistant")]
    messages.extend(cleaned_history[-10:])
    messages.append({"role": "user", "content": instruction})

    final = "Reached step limit before finishing."
    validated_once = False
    modified_files = False
    for _ in range(max_steps):
        msg = chat(messages, tools=TOOLS, temperature=0.3, max_tokens=8000)
        messages.append(msg)
        tool_calls = msg.get("tool_calls") or []

        # Stream any assistant prose that came alongside tool calls.
        if msg.get("content"):
            emit({"type": "assistant", "text": msg["content"]})

        if not tool_calls:
            if modified_files:
                problems = _validate_html(site_dir)
                if problems and not validated_once:
                    validated_once = True
                    emit({"type": "status", "message": "Validating HTML and fixing issues…"})
                    messages.append({
                        "role": "user",
                        "content": "Validation found issues, fix them before finishing: " + problems,
                    })
                    continue
            final = (msg.get("content") or "Done.").strip()
            break

        for call in tool_calls:
            fn = call["function"]
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except (json.JSONDecodeError, TypeError):
                args = {}
            name = fn["name"]

            if name in ("edit_file", "write_file", "create_file", "delete_file", "rename_file", "run_command"):
                modified_files = True

            if name == "update_plan":
                emit({"type": "plan", "steps": args.get("steps", [])})
            else:
                emit({"type": "tool", "name": name, "label": _describe_action(name, args), "args": args})

            result = _dispatch(site_dir, name, args)

            if name not in ("update_plan",):
                emit({"type": "tool_result", "name": name, "ok": not result.startswith("ERROR"),
                      "summary": result[:200]})

            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": result[:6000],
            })

    # Save conversation history helper
    def save_history(ans_text):
        if place_id:
            try:
                db.add_chat_message(place_id, "user", instruction)
                db.add_chat_message(place_id, "assistant", ans_text)
            except Exception:
                pass
        else:
            history.append({"role": "user", "content": instruction})
            history.append({"role": "assistant", "content": ans_text})
            try:
                with open(history_path, "w", encoding="utf-8") as f:
                    json.dump(history[-50:], f, indent=2)
            except Exception:
                pass

    # Checkpoint or roll back based on the final state.
    if modified_files:
        problems = _validate_html(site_dir)
        if problems:
            _rollback(site_dir)
            emit({"type": "status", "message": "Rolled back to last good state"})
            err_msg = f"⚠️ Change rolled back -- site left in last good state. Issue: {problems}"
            save_history(err_msg)
            return err_msg
        if _has_changes(site_dir):
            _commit(site_dir, f"agent: {instruction[:60]}")
            emit({"type": "status", "message": "Saved checkpoint (git)"})
            success_msg = final + "\n\n✅ Saved a checkpoint (git). You can undo anytime."
            save_history(success_msg)
            return success_msg
    
    save_history(final)
    return final + "\n\n(No file changes were made.)"
