"""Publish a static site folder to Netlify via the file-digest deploy API.

For a plain static site we can create a site and deploy a zip in two
calls -- no build step, no CLI. Returns the live URL.
"""
import io
import os
import zipfile

import requests

import config

_API = "https://api.netlify.com/api/v1"


def _headers() -> dict:
    if not config.NETLIFY_AUTH_TOKEN:
        raise RuntimeError("NETLIFY_AUTH_TOKEN is not set.")
    return {"Authorization": f"Bearer {config.NETLIFY_AUTH_TOKEN}"}


def _zip_dir(site_dir: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(site_dir):
            for fn in files:
                full = os.path.join(root, fn)
                arc = os.path.relpath(full, site_dir)
                zf.write(full, arc)
    return buf.getvalue()


def deploy(site_dir: str, name_hint: str = "") -> str:
    """Create a Netlify site and deploy the folder. Returns the live URL."""
    # 1) Create a site (let Netlify assign a random subdomain).
    create = requests.post(f"{_API}/sites", headers=_headers(), json={}, timeout=60)
    create.raise_for_status()
    site = create.json()
    site_id = site["id"]

    # 2) Deploy the zipped folder.
    zip_bytes = _zip_dir(site_dir)
    headers = {**_headers(), "Content-Type": "application/zip"}
    dep = requests.post(
        f"{_API}/sites/{site_id}/deploys",
        headers=headers,
        data=zip_bytes,
        timeout=120,
    )
    dep.raise_for_status()
    data = dep.json()
    return data.get("ssl_url") or data.get("url") or site.get("ssl_url") or site.get("url")
