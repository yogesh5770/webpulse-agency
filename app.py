"""App entrypoint: Gradio dashboard + embedded Monaco (VS Code-style) AI IDE.

The Dashboard tab (leads, 24/7 worker, discovery) stays native Gradio. The
"AI IDE" tab embeds a real VS Code-style editor (Monaco) served by FastAPI at
/ide, so the IDE has a true Cursor/VS Code feel with file tabs, a live agent
activity stream, diffs, and quick-open.

We mount everything on one FastAPI app:
  - IDE routes (registered first) at /ide and /ide/api/*
  - Gradio at /
and serve with uvicorn.
"""
import gradio as gr
from fastapi import FastAPI

import config
import db
from pipeline import discover, process_one_lead, start_worker, stop_worker, worker_status
from agent_router import test_connection
from ide_api import register_ide_routes

db.init_db()


# ---------- Dashboard callbacks --------------------------------------

def _published_count():
    return [l for l in db.all_leads() if l.get('site_dir')]


def _leads_table():
    rows = []
    for l in db.all_leads():
        rows.append([
            l.get("name", ""), l.get("category", ""), l.get("phone", ""),
            l.get("status", ""), l.get("live_url", "") or "",
        ])
    return rows


def _status_md():
    counts = db.counts_by_status()
    ws = worker_status()
    missing = config.missing_keys()
    lines = [
        f"**Worker running:** {ws['running']}  |  **Processed this session:** {ws['processed']}",
        f"**Last:** {ws['last'] or '-'}",
        "**Leads by status:** " + (", ".join(f"{k}={v}" for k, v in counts.items()) or "none"),
        f"**Storage:** {db.backend_name()} — {db.site_storage_bytes()/1024:.0f} KB of site files across {len(_published_count())} site(s)",
    ]
    if missing:
        lines.append(f"⚠️ **Missing secrets:** {', '.join(missing)} — set them before running.")
    return "\n\n".join(lines)


def on_discover(query):
    try:
        n, used = discover(query or None)
        return f"Added {n} new lead(s) for '{used}'.", _leads_table(), _status_md()
    except Exception as e:
        return f"Discovery error: {e}", _leads_table(), _status_md()


def on_process_once():
    r = process_one_lead()
    msg = "No new leads to process." if not r else f"{r.get('status')}: {r.get('name')}"
    return msg, _leads_table(), _status_md()


def on_start():
    return start_worker(), _status_md()


def on_stop():
    return stop_worker(), _status_md()


def on_refresh():
    return _leads_table(), _status_md()


def on_test_connection():
    ok, msg = test_connection()
    return msg


# ---------- UI --------------------------------------------------------

_IDE_IFRAME = """
<div style="height:82vh;border:1px solid #313244;border-radius:10px;overflow:hidden">
  <iframe src="/ide" style="width:100%;height:100%;border:0" title="AI IDE"></iframe>
</div>
<p style="color:#7f849c;font-size:12px;margin-top:6px">
  Real VS Code-style editor (Monaco). If the list is empty, generate a site first
  from the Dashboard tab, then click <b>↻ Reload sites</b> inside the IDE.
</p>
"""

with gr.Blocks(title="Lead → Website Automation") as ui:
    gr.Markdown("# 🏭 Lead → Website Automation\nFinds businesses with no website, builds one with Opus, publishes to Netlify, drafts WhatsApp outreach.")

    with gr.Tab("Dashboard"):
        status = gr.Markdown(_status_md())
        with gr.Row():
            query_in = gr.Textbox(label="Search query (leave blank = AI picks one automatically)", placeholder="blank = AI auto-generates a fresh query", scale=3)
            discover_btn = gr.Button("🔎 Discover leads", scale=1)
            once_btn = gr.Button("⚙️ Build next site", scale=1)
        with gr.Row():
            start_btn = gr.Button("▶️ Start 24/7 worker", variant="primary")
            stop_btn = gr.Button("⏹️ Stop worker")
            refresh_btn = gr.Button("🔄 Refresh")
            test_btn = gr.Button("🔌 Test AgentRouter")
        action_msg = gr.Markdown()
        leads_tbl = gr.Dataframe(
            headers=["Name", "Category", "Phone", "Status", "Live URL"],
            value=_leads_table(), interactive=False, wrap=True,
        )

        discover_btn.click(on_discover, [query_in], [action_msg, leads_tbl, status])
        once_btn.click(on_process_once, None, [action_msg, leads_tbl, status])
        start_btn.click(on_start, None, [action_msg, status])
        stop_btn.click(on_stop, None, [action_msg, status])
        refresh_btn.click(on_refresh, None, [leads_tbl, status])
        test_btn.click(on_test_connection, None, [action_msg])

    with gr.Tab("AI IDE (per site)"):
        gr.Markdown("### 🖥️ Cursor-style AI IDE — real Monaco editor, file tabs, live preview, diffs, and an autonomous agent.")
        gr.HTML(_IDE_IFRAME)


# ---------- Serve: FastAPI (IDE routes) + Gradio ----------------------

app = FastAPI(title="Lead → Website Automation")
register_ide_routes(app)              # /ide and /ide/api/* — must be before mount
app = gr.mount_gradio_app(app, ui, path="/")


# The host platform (Render, or Hugging Face's free Gradio SDK) runs this
# file with `python app.py`, so the __main__ block below starts the server on
# the port the platform expects. This serves BOTH the Gradio dashboard (/)
# and the Monaco IDE routes (/ide) on a single server -- no separate process
# needed. Render sets $PORT dynamically; HF Spaces expects the fixed 7860.
# Single server for the whole app. We intentionally name the Blocks object `ui`
# (not `demo`/`app`) so Hugging Face's Gradio auto-launcher does NOT start a
# second server -- our uvicorn below is the only one.
if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)