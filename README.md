---
title: Lead To Website Automation
emoji: 🏭
colorFrom: indigo
colorTo: purple
sdk: gradio
sdk_version: 5.9.0
app_file: app.py
pinned: false
short_description: Finds leads, builds AI sites, publishes, drafts outreach
---

# 🏭 Lead → Website Automation

Runs 24/7: finds local businesses with no website, builds a premium single-file
site with GLM 5.2, publishes it to **Cloudflare Pages** (unlimited free), and drafts
a WhatsApp outreach message with a one-click wa.me link. Includes a **Cursor-style
AI IDE** (real Monaco editor) to edit each generated site with an autonomous agent.

## Hosting on Hugging Face (free)

This Space uses the **Gradio SDK (free tier)** — no paid Docker Space needed.
HF runs `python app.py`, which starts a FastAPI + uvicorn server on port 7860
serving **both**:

- `/`      — the Gradio dashboard (leads, 24/7 worker, discovery)
- `/ide`   — the Monaco (VS Code-style) AI IDE, embedded in the "AI IDE" tab

## Configure these Space secrets (Settings → Variables and secrets)

Required:

- `AGENTROUTER_BASE_URL`  (e.g. `https://agentrouter.org/v1`)
- `AGENTROUTER_API_KEY`
- `GOOGLE_PLACES_API_KEY`

Publishing (choose one via `DEPLOY_PROVIDER`, default `cloudflare`):

- **Cloudflare Pages (recommended, unlimited free):** `CLOUDFLARE_API_TOKEN`,
  `CLOUDFLARE_ACCOUNT_ID`, optional `CLOUDFLARE_PAGES_PROJECT` (default `lead-sites`).
- **Netlify:** set `DEPLOY_PROVIDER=netlify` and `NETLIFY_AUTH_TOKEN`.

### Persistence (important on free Spaces)

HF free Spaces have an **ephemeral disk** — the local `leads.db` and generated
`sites/` reset on every rebuild/sleep. Published sites live on Cloudflare so
they persist, but your **lead history** won't unless you set a Postgres URL:

- `DATABASE_URL` — a free Postgres from Supabase / Neon / Railway, e.g.
  `postgresql://user:pass@host:5432/dbname`. When set, leads are stored there
  instead of SQLite. Leave blank locally to use the SQLite file.

- **Website files persist too:** each generated site's files (`index.html`, etc.) are stored in the DB (a `site_files` table), so IDE edits survive restarts. Images are hotlinked URLs (not stored), keeping sites ~50 KB — a 500 MB free DB holds ~8,000+ sites.

Notes:

- HF containers don't ship Node, so the Cloudflare deploy uses the pure-Python
  REST upload path (the `blake3` dependency in `requirements.txt` makes its asset
  hashing correct — keep it installed).
- The dashboard shows a ⚠️ banner listing any missing secrets for your chosen
  provider before you run.
