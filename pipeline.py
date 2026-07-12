"""End-to-end pipeline for ONE lead and the 24/7 worker loop.

process_one_lead: enrich is already done at discovery; here we generate the
site, deploy to Netlify, draft the WhatsApp message, and record everything.

worker_loop: runs forever, claiming one 'new' lead at a time (dedup-safe),
so the system keeps building sites around the clock, one by one.
"""
import threading
import time
import traceback

import config
import db
from leads_places import find_leads
from lead_queries import next_query
from site_generator import generate_site
import site_store
from deploy import deploy
from outreach import draft_message, wa_link

# Simple in-process worker control so the dashboard can start/stop it.
_worker_thread: threading.Thread | None = None
_stop_flag = threading.Event()
_status = {"running": False, "last": "", "processed": 0}


def discover(query: str | None = None, max_results: int | None = None) -> tuple[int, str]:
    """Find leads and add the new (non-duplicate) ones. When no query is given,
    an AI-generated fresh query is used so discovery keeps finding new areas.
    Returns (added_count, query_used)."""
    if not query:
        query = next_query()  # AI-driven (or fallback rotation)
    max_results = max_results or config.LEAD_MAX_RESULTS
    leads = find_leads(query, max_results)
    added = 0
    for lead in leads:
        if db.add_lead(lead):  # False when the business already exists (dedup)
            added += 1
    return added, query


def process_one_lead() -> dict | None:
    """Take the next 'new' lead through the full pipeline."""
    lead = db.next_new_lead()
    if lead is None:
        return None
    pid = lead["place_id"]
    try:
        site_marker = generate_site(lead)          # "db://<place_id>" — files stored in DB
        # Deploy needs real files: materialize the DB folder into a temp dir.
        deploy_dir = site_store.materialize(pid)
        live_url = deploy(deploy_dir, name_hint=lead.get("name", ""))
        message = draft_message(lead, live_url)
        db.update_lead(
            pid,
            status="published",
            site_dir=site_marker,
            live_url=live_url,
            message=message,
            error="",
        )
        return db.get_lead(pid)
    except Exception as e:
        db.update_lead(pid, status="failed", error=f"{e}\n{traceback.format_exc()[:800]}")
        return db.get_lead(pid)


def _loop():
    _status["running"] = True
    while not _stop_flag.is_set():
        try:
            result = process_one_lead()
            if result is None:
                # No leads waiting -> AI-generate a fresh query, discover, idle.
                added, q = discover()
                _status["last"] = f"Discovered {added} lead(s) for '{q}'"
                _stop_flag.wait(config.WORKER_INTERVAL_SECONDS)
                continue
            _status["processed"] += 1
            _status["last"] = f"{result.get('status')}: {result.get('name')}"
        except Exception as e:
            _status["last"] = f"loop error: {e}"
        _stop_flag.wait(config.WORKER_INTERVAL_SECONDS)
    _status["running"] = False


def start_worker() -> str:
    global _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        return "Worker already running."
    _stop_flag.clear()
    _worker_thread = threading.Thread(target=_loop, daemon=True)
    _worker_thread.start()
    return "Worker started."


def stop_worker() -> str:
    _stop_flag.set()
    return "Worker stopping..."


def worker_status() -> dict:
    return dict(_status)
