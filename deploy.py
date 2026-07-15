"""Deploy dispatcher: publish a site folder to Cloudflare Pages.

Cloudflare Pages is the only host for generated client sites: unlimited sites,
requests, and bandwidth on the free plan -- no per-project caps, which is what
a 24/7 site factory needs.

The rest of the app calls deploy(site_dir, name_hint) and doesn't care how it
is published.
"""
from cloudflare_deploy import deploy as _deploy


def deploy(site_dir: str, name_hint: str = "", stable_key: str = "") -> str:
    return _deploy(site_dir, name_hint, stable_key)
