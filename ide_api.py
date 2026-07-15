"""FastAPI backend for the Monaco (VS Code-style) IDE.

Files are read/written straight to the DATABASE via site_store (source of
truth, so edits persist across restarts). The AI agent needs real files on
disk, so for an agent run we materialize the site DB -> temp dir, run the
agent there, then sync the result back into the DB.
"""
import json
import os
import queue
import threading

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

import db
import site_store
import ide_agent as agent
from deploy import deploy as deploy_site

_HERE = os.path.dirname(os.path.abspath(__file__))
_FRONTEND = os.path.join(_HERE, "ide_frontend.html")


# ---- site resolution -------------------------------------------------

def _published():
    return [l for l in db.all_leads() if l.get("site_dir")]


def _resolve(site_id: str):
    """Match a site by place_id (full or 8-char prefix)."""
    if not site_id:
        return None
    for l in _published():
        pid = l.get("place_id") or ""
        if pid == site_id or pid[:8] == site_id:
            return l
    return None


def _pid(site_id: str):
    l = _resolve(site_id)
    return l["place_id"] if l else None


# ---- route registration ---------------------------------------------

def register_ide_routes(app) -> None:
    """Attach all /ide routes to the given FastAPI app (call BEFORE mounting
    Gradio at '/')."""

    @app.get("/ide", response_class=HTMLResponse)
    def ide_page():
        try:
            with open(_FRONTEND, "r", encoding="utf-8") as f:
                return HTMLResponse(f.read())
        except FileNotFoundError:
            return HTMLResponse("<h1>ide_frontend.html not found</h1>", status_code=500)

    @app.get("/ide/api/sites")
    def sites():
        out = []
        for l in _published():
            item = dict(l)
            item["id"] = (l.get("place_id") or "")[:8]
            # Exclude large file markers
            if "site_dir" in item:
                del item["site_dir"]
            out.append(item)
        return JSONResponse(out)

    @app.get("/ide/api/tree")
    def tree(site: str):
        pid = _pid(site)
        if not pid:
            return JSONResponse({"error": "site not found"}, status_code=404)
        return JSONResponse({"files": site_store.list_files(pid)})

    @app.get("/ide/api/file")
    def read_file(site: str, path: str):
        pid = _pid(site)
        if not pid:
            return JSONResponse({"error": "site not found"}, status_code=404)
        try:
            return JSONResponse({"path": path, "content": site_store.read_file(pid, path)})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    @app.post("/ide/api/save")
    async def save_file(req: Request):
        body = await req.json()
        pid = _pid(body.get("site"))
        if not pid:
            return JSONResponse({"error": "site not found"}, status_code=404)
        try:
            site_store.write_file(pid, body["path"], body.get("content", ""))
            return JSONResponse({"ok": True})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    @app.post("/ide/api/create")
    async def create_file(req: Request):
        body = await req.json()
        pid = _pid(body.get("site"))
        if not pid:
            return JSONResponse({"error": "site not found"}, status_code=404)
        res = site_store.create_file(pid, body["path"], body.get("content", ""))
        ok = not res.startswith("ERROR")
        return JSONResponse({"ok": ok, "message": res}, status_code=200 if ok else 400)

    @app.post("/ide/api/delete")
    async def delete_file(req: Request):
        body = await req.json()
        pid = _pid(body.get("site"))
        if not pid:
            return JSONResponse({"error": "site not found"}, status_code=404)
        res = site_store.delete_file(pid, body["path"])
        ok = not res.startswith("ERROR")
        return JSONResponse({"ok": ok, "message": res}, status_code=200 if ok else 400)

    @app.post("/ide/api/rename")
    async def rename_file(req: Request):
        body = await req.json()
        pid = _pid(body.get("site"))
        if not pid:
            return JSONResponse({"error": "site not found"}, status_code=404)
        res = site_store.rename_file(pid, body["path"], body["new_path"])
        ok = not res.startswith("ERROR")
        return JSONResponse({"ok": ok, "message": res}, status_code=200 if ok else 400)

    @app.post("/ide/api/undo")
    async def undo(req: Request):
        body = await req.json()
        pid = _pid(body.get("site"))
        if not pid:
            return JSONResponse({"error": "site not found"}, status_code=404)
        return JSONResponse({"message": site_store.undo(pid)})

    @app.post("/ide/api/agent")
    async def run_agent_stream(req: Request):
        body = await req.json()
        site_id = body.get("site")
        pid = _pid(site_id) if site_id else None
        instruction = (body.get("instruction") or "").strip()
        if not instruction:
            return JSONResponse({"error": "empty instruction"}, status_code=400)

        events: "queue.Queue" = queue.Queue()

        def worker():
            try:
                if pid:
                    # DB -> temp dir, run the disk-based agent, then dir -> DB.
                    workdir = site_store.materialize(pid)
                    reply = agent.run_agent(workdir, instruction, on_event=lambda ev: events.put(ev))
                    site_store.sync(pid, workdir)
                else:
                    # General assistant mode when no website is created yet
                    import tempfile
                    with tempfile.TemporaryDirectory() as tmpdir:
                        reply = agent.run_agent(tmpdir, instruction, on_event=lambda ev: events.put(ev))
                events.put({"type": "done", "reply": reply})
            except Exception as e:
                events.put({"type": "done", "reply": f"Agent error: {e}", "error": True})
            finally:
                events.put(None)

        threading.Thread(target=worker, daemon=True).start()

        def sse():
            while True:
                ev = events.get()
                if ev is None:
                    break
                yield "data: " + json.dumps(ev) + "\n\n"

        return StreamingResponse(sse(), media_type="text/event-stream")

    @app.post("/ide/api/redeploy")
    async def redeploy(req: Request):
        body = await req.json()
        lead = _resolve(body.get("site"))
        if not lead:
            return JSONResponse({"error": "site not found"}, status_code=404)
        pid = lead["place_id"]
        try:
            # DB (source of truth, includes IDE + agent edits) -> temp dir -> deploy.
            # stable_key=pid keeps the SAME branch/URL on every redeploy.
            workdir = site_store.materialize(pid)
            live_url = deploy_site(
                workdir, name_hint=lead.get("name", ""), stable_key=pid,
            )
            db.update_lead(pid, live_url=live_url, status="published", error="")
            return JSONResponse({"ok": True, "live_url": live_url})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
