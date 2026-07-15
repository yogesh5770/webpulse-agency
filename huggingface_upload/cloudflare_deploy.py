"""Publish a static site folder to Cloudflare Pages.

Why Cloudflare Pages: unlimited sites, requests, and bandwidth on the free
plan -- no sudden project caps, which is what a 24/7 site factory needs.

Strategy to give EACH business its own stable URL without hitting any
per-project limit: deploy every site into ONE Pages project but on a UNIQUE
branch (one branch per business). Cloudflare gives each branch its own alias:

    https://<branch>.<project>.pages.dev

Two deploy paths, tried in order:
  1. Wrangler CLI (`npx wrangler pages deploy`) -- Cloudflare's officially
     supported direct-upload path; handles asset hashing/manifest/JWT for us.
     Used when Node/npx is available.
  2. Pure REST direct-upload -- no Node needed. Hashes files (blake3 if the
     `blake3` package is installed, else sha256 fallback), uploads via the
     Pages assets API, and creates a deployment. Used when wrangler isn't
     available.

Returns the live pages.dev URL.
"""
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess

import requests

import config

_API = "https://api.cloudflare.com/client/v4"


def _acct_headers() -> dict:
    if not config.CLOUDFLARE_API_TOKEN:
        raise RuntimeError("CLOUDFLARE_API_TOKEN is not set.")
    return {"Authorization": f"Bearer {config.CLOUDFLARE_API_TOKEN}"}


def _slug_branch(name_hint: str, site_dir: str) -> str:
    """A stable, DNS-safe branch/alias per business (<=28 chars + suffix).

    We append a short hash of the site_dir so two businesses with the same
    name still get distinct URLs, and re-deploys of the SAME site reuse the
    same branch (stable URL)."""
    base = re.sub(r"[^a-z0-9]+", "-", (name_hint or "site").lower()).strip("-")[:28] or "site"
    suffix = hashlib.sha1(site_dir.encode()).hexdigest()[:6]
    return f"{base}-{suffix}".strip("-")


def _project_url(branch: str) -> str:
    return f"https://{branch}.{config.CLOUDFLARE_PAGES_PROJECT}.pages.dev"


# ---- project bootstrap (REST) ---------------------------------------

def _ensure_project() -> None:
    """Create the Pages project once if it doesn't exist. Idempotent."""
    acct = config.CLOUDFLARE_ACCOUNT_ID
    proj = config.CLOUDFLARE_PAGES_PROJECT
    if not acct:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID is not set.")
    r = requests.get(
        f"{_API}/accounts/{acct}/pages/projects/{proj}",
        headers=_acct_headers(), timeout=30,
    )
    if r.status_code == 200:
        return
    # Create it (production_branch 'main'; we deploy businesses to other branches).
    create = requests.post(
        f"{_API}/accounts/{acct}/pages/projects",
        headers={**_acct_headers(), "Content-Type": "application/json"},
        json={"name": proj, "production_branch": "main"},
        timeout=30,
    )
    if create.status_code not in (200, 201):
        # 409/already-exists is fine (race); otherwise surface it.
        if "already" not in create.text.lower():
            raise RuntimeError(f"Could not create Pages project: {create.status_code} {create.text[:300]}")


# ---- path 1: wrangler CLI -------------------------------------------

def _have_wrangler() -> bool:
    return shutil.which("npx") is not None or shutil.which("wrangler") is not None


def _deploy_wrangler(site_dir: str, branch: str) -> str:
    exe = ["wrangler"] if shutil.which("wrangler") else ["npx", "--yes", "wrangler"]
    env = {
        **os.environ,
        "CLOUDFLARE_API_TOKEN": config.CLOUDFLARE_API_TOKEN,
        "CLOUDFLARE_ACCOUNT_ID": config.CLOUDFLARE_ACCOUNT_ID,
    }
    cmd = exe + [
        "pages", "deploy", site_dir,
        "--project-name", config.CLOUDFLARE_PAGES_PROJECT,
        "--branch", branch,
        "--commit-dirty=true",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"wrangler deploy failed: {proc.stderr[-400:] or proc.stdout[-400:]}")
    # wrangler prints the alias URL; capture it if present, else compute it.
    m = re.search(r"https://[^\s]+\.pages\.dev", proc.stdout)
    return m.group(0) if m else _project_url(branch)


# ---- path 2: pure REST direct upload --------------------------------

def _hash_file(data: bytes, ext: str) -> str:
    """Cloudflare hashes = blake3(content + ext) truncated to 32 hex chars.
    Use blake3 when available; fall back to sha256 (still unique per file, so
    dedup is weaker but uploads remain correct)."""
    try:
        import blake3  # type: ignore
        h = blake3.blake3(data + ext.encode()).hexdigest()
    except Exception:
        h = hashlib.sha256(data + ext.encode()).hexdigest()
    return h[:32]


def _iter_files(site_dir: str):
    for root, _dirs, files in os.walk(site_dir):
        if ".git" in root:
            continue
        for fn in files:
            full = os.path.join(root, fn)
            rel = "/" + os.path.relpath(full, site_dir).replace(os.sep, "/")
            yield full, rel


def _deploy_rest(site_dir: str, branch: str) -> str:
    acct = config.CLOUDFLARE_ACCOUNT_ID
    proj = config.CLOUDFLARE_PAGES_PROJECT

    # Build manifest: {path: hash} and remember each file's bytes + ext.
    manifest, blobs = {}, {}
    for full, rel in _iter_files(site_dir):
        with open(full, "rb") as f:
            data = f.read()
        ext = os.path.splitext(full)[1].lstrip(".")
        h = _hash_file(data, ext)
        manifest[rel] = h
        blobs[h] = (data, ext)

    # 1) Get an upload token (JWT) for this project.
    tok = requests.get(
        f"{_API}/accounts/{acct}/pages/projects/{proj}/upload-token",
        headers=_acct_headers(), timeout=30,
    )
    tok.raise_for_status()
    jwt = tok.json()["result"]["jwt"]
    jwt_h = {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}

    # 2) Ask which hashes are missing (dedup).
    chk = requests.post(
        f"{_API}/pages/assets/check-missing",
        headers=jwt_h, json={"hashes": list(blobs.keys())}, timeout=60,
    )
    chk.raise_for_status()
    missing = set(chk.json()["result"])

    # 3) Upload missing files (base64), batched.
    payload = []
    for h in missing:
        data, ext = blobs[h]
        payload.append({
            "key": h,
            "value": base64.b64encode(data).decode(),
            "metadata": {"contentType": _content_type(ext)},
            "base64": True,
        })
    if payload:
        up = requests.post(
            f"{_API}/pages/assets/upload",
            headers=jwt_h, json=payload, timeout=180,
        )
        up.raise_for_status()

    # 4) Create the deployment on this branch (multipart form).
    files = {
        "manifest": (None, json.dumps(manifest)),
        "branch": (None, branch),
    }
    dep = requests.post(
        f"{_API}/accounts/{acct}/pages/projects/{proj}/deployments",
        headers=_acct_headers(), files=files, timeout=180,
    )
    dep.raise_for_status()
    res = dep.json()["result"]
    return res.get("url") or _project_url(branch)


def _content_type(ext: str) -> str:
    return {
        "html": "text/html", "css": "text/css", "js": "application/javascript",
        "json": "application/json", "svg": "image/svg+xml", "png": "image/png",
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
        "gif": "image/gif", "ico": "image/x-icon", "txt": "text/plain",
    }.get(ext.lower(), "application/octet-stream")


# ---- public entrypoint ----------------------------------------------

def deploy(site_dir: str, name_hint: str = "") -> str:
    """Publish `site_dir` to Cloudflare Pages; return the live URL."""
    if not config.CLOUDFLARE_PAGES_PROJECT:
        raise RuntimeError("CLOUDFLARE_PAGES_PROJECT is not set.")
    _ensure_project()
    branch = _slug_branch(name_hint, site_dir)
    if _have_wrangler():
        return _deploy_wrangler(site_dir, branch)
    return _deploy_rest(site_dir, branch)
