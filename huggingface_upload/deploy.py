"""Deploy dispatcher: publish a site folder via the configured provider.

Set DEPLOY_PROVIDER in .env to choose:
  - "cloudflare" (default) -> Cloudflare Pages (unlimited free, no project caps)
  - "netlify"              -> Netlify (kept for compatibility)

The rest of the app calls deploy(site_dir, name_hint) and doesn't care which
backend is used.
"""
import config


def deploy(site_dir: str, name_hint: str = "") -> str:
    provider = (config.DEPLOY_PROVIDER or "cloudflare").lower()
    if provider == "netlify":
        from netlify_deploy import deploy as _d
        return _d(site_dir, name_hint)
    # default
    from cloudflare_deploy import deploy as _d
    return _d(site_dir, name_hint)
