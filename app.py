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


def on_single_click(query):
    try:
        n, used = discover(query or None)
        discover_msg = f"Added {n} new lead(s) for '{used}'."
        r = process_one_lead()
        if not r:
            msg = f"{discover_msg} No new leads were processed."
        else:
            msg = f"{discover_msg} Successfully built and deployed site for: {r.get('name')} (Live: {r.get('live_url')})."
        return msg, _leads_table(), _status_md()
    except Exception as e:
        import traceback
        return f"Single-Click error: {e}\n{traceback.format_exc()}", _leads_table(), _status_md()


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


# ---------- WhatsApp Simulator Callbacks ------------------------------

def _get_published_sites_choices():
    return [f"{l.get('name')} ({l.get('place_id')[:8]})" for l in db.all_leads() if l.get("site_dir")]


def on_refresh_sim_choices():
    choices = _get_published_sites_choices()
    return gr.update(choices=choices, value=choices[0] if choices else None)


def on_load_chat_history(selected_site):
    if not selected_site:
        return "No site selected."
    pid_prefix = selected_site.split("(")[-1].strip(")")
    for l in db.all_leads():
        if l.get("place_id")[:8] == pid_prefix:
            return l.get("message") or "No messages yet."
    return "Site not found."


def on_send_sim_message(selected_site, message_text):
    if not selected_site:
        return "No site selected.", "Please select a site first."
    if not message_text.strip():
        return "Empty message.", "Please enter a message."
    
    pid_prefix = selected_site.split("(")[-1].strip(")")
    place_id = None
    for l in db.all_leads():
        if l.get("place_id")[:8] == pid_prefix:
            place_id = l.get("place_id")
            break
            
    if not place_id:
        return "Site place_id not found.", "Error: site matching selection not found."
        
    try:
        import whatsapp_agent
        reply = whatsapp_agent.handle_customer_reply(place_id, message_text)
        updated_lead = db.get_lead(place_id)
        return updated_lead.get("message") or "", f"Done! Agency response: {reply}"
    except Exception as e:
        return f"Error: {e}", f"Execution failed: {e}"


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
    gr.Markdown("# 🏭 Lead → Website Automation\nFinds businesses with no website, builds one with Opus, publishes to Cloudflare Pages, drafts WhatsApp outreach.")

    with gr.Tab("Dashboard"):
        status = gr.Markdown(_status_md())
        with gr.Row():
            query_in = gr.Textbox(label="Search query (leave blank = AI picks one automatically)", placeholder="blank = AI auto-generates a fresh query", scale=3)
            discover_btn = gr.Button("🔎 Discover leads", scale=1)
            once_btn = gr.Button("⚙️ Build next site", scale=1)
            single_btn = gr.Button("⚡ Single-Click Run", variant="primary", scale=1)
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
        single_btn.click(on_single_click, [query_in], [action_msg, leads_tbl, status])
        start_btn.click(on_start, None, [action_msg, status])
        stop_btn.click(on_stop, None, [action_msg, status])
        refresh_btn.click(on_refresh, None, [leads_tbl, status])
        test_btn.click(on_test_connection, None, [action_msg])

    with gr.Tab("AI IDE (per site)"):
        gr.Markdown("### 🖥️ Cursor-style AI IDE — real Monaco editor, file tabs, live preview, diffs, and an autonomous agent.")
        gr.HTML(_IDE_IFRAME)

    with gr.Tab("WhatsApp Simulator"):
        gr.Markdown("### 💬 Simulate customer WhatsApp replies to trigger autonomous website updates")
        with gr.Row():
            sim_site = gr.Dropdown(label="Select Business / Site", choices=_get_published_sites_choices(), interactive=True)
            refresh_sim_btn = gr.Button("↻ Refresh Sites List")
        
        chat_history = gr.TextArea(label="WhatsApp Chat History", interactive=False, lines=10)
        
        with gr.Row():
            customer_msg = gr.Textbox(label="Customer Message", placeholder="e.g. Change the main color to luxurious gold and add a pricing list...")
            send_msg_btn = gr.Button("Send Simulated Message", variant="primary")
            
        sim_status = gr.Markdown()

        refresh_sim_btn.click(on_refresh_sim_choices, None, [sim_site])
        sim_site.change(on_load_chat_history, [sim_site], [chat_history])
        send_msg_btn.click(on_send_sim_message, [sim_site, customer_msg], [chat_history, sim_status])


# ---------- Serve: FastAPI (IDE routes) + Gradio ----------------------

from fastapi import Request
from fastapi.responses import JSONResponse

from fastapi.responses import HTMLResponse

app = FastAPI(title="Lead → Website Automation")

@app.get("/privacy", response_class=HTMLResponse)
async def serve_privacy():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Privacy Policy - WebPulse Agency</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 600px; margin: 40px auto; padding: 20px; line-height: 1.6; color: #1e1e2f; background-color: #fafafa; }
        h1 { border-bottom: 2px solid #eaeaea; padding-bottom: 10px; color: #111; }
        p { color: #555; }
    </style>
</head>
<body>
    <h1>Privacy Policy</h1>
    <p>Last updated: July 15, 2026</p>
    <p>WebPulse Agency operates the website automation platform. We respect your privacy and only collect or process data necessary to build, deploy, and update business websites on your behalf.</p>
    <p>We do not share your contact details or business details with external third parties except where required to serve website files (Cloudflare) or process AI decisions (AWS Bedrock).</p>
</body>
</html>"""


@app.get("/api/whatsapp/webhook")
async def verify_whatsapp_webhook(req: Request):
    params = req.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    import config
    if mode == "subscribe" and token == config.WHATSAPP_VERIFY_TOKEN:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content=challenge)
    return JSONResponse({"error": "Verification failed"}, status_code=403)


@app.post("/api/whatsapp/webhook")
async def whatsapp_webhook(req: Request):
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    # Ignore status updates, read notifications, etc.
    entry = body.get("entry", [])
    if not entry or not entry[0].get("changes"):
        return JSONResponse({"ok": True, "message": "Ignored status event"})
        
    change = entry[0]["changes"][0]["value"]
    messages = change.get("messages", [])
    if not messages:
        return JSONResponse({"ok": True, "message": "No incoming message found"})
        
    msg = messages[0]
    from_phone = msg.get("from") or ""
    
    if msg.get("type") != "text" or not msg.get("text"):
        return JSONResponse({"ok": True, "message": "Non-text message ignored"})
        
    message_text = msg["text"].get("body", "").strip()
    if not message_text:
        return JSONResponse({"ok": True, "message": "Empty message"})

    # Match phone number with DB leads
    place_id = None
    incoming_digits = "".join(filter(str.isdigit, from_phone))
    for lead in db.all_leads():
        lead_phone = lead.get("phone") or ""
        lead_digits = "".join(filter(str.isdigit, lead_phone))
        if lead_digits and (incoming_digits in lead_digits or lead_digits in incoming_digits):
            place_id = lead["place_id"]
            break
            
    if not place_id:
        return JSONResponse({"error": f"Lead with phone {from_phone} not found"}, status_code=404)
        
    import whatsapp_agent
    reply = whatsapp_agent.handle_customer_reply(place_id, message_text)
    return JSONResponse({"ok": True, "reply": reply})

register_ide_routes(app)              # /ide and /ide/api/* — must be before mount
app = gr.mount_gradio_app(app, ui, path="/")


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)