# 🚀 Deploy this app to a Hugging Face Space

Everything is ready to push. I could **not** push from my side (my sandbox
can't reach huggingface.co, and pushing needs *your* HF account). Do this once
on your own computer — it takes ~2 minutes.

Your `.env`, `leads.db`, and `sites/` are git-ignored, so **no secrets get
uploaded**. You'll set secrets in the Space UI instead (step 4).

---

## Option A — Web UI + upload (easiest, no git)

1. Go to https://huggingface.co/new-space
2. **Owner**: you · **Space name**: e.g. `lead-automation`
3. **SDK**: choose **Gradio** (free). **Hardware**: **CPU basic (free)** is fine.
4. Click **Create Space**.
5. On the Space page → **Files** tab → **Add file → Upload files**.
   Drag in EVERY file from this folder **except**: `.env`, `leads.db`,
   the `sites/` folder, and `.git/`. (Uploading `.env.example` is fine.)
6. Go to **Settings → Variables and secrets** and add your secrets (step 4 below).
   The Space will build and start automatically.

## Option B — Git push (from this folder)

Open a terminal in this folder and run:

```bash
# 1. Log in (paste a token from https://huggingface.co/settings/tokens — needs "write")
pip install -U huggingface_hub
huggingface-cli login

# 2. Create the Space (Gradio SDK). Replace <you>/<space-name>.
huggingface-cli repo create <space-name> --type space --space_sdk gradio -y

# 3. Push
git init
git add -A
git commit -m "deploy lead-automation"
git branch -M main
git remote add origin https://huggingface.co/spaces/<you>/<space-name>
git push -u origin main
```

If `git push` asks for a password, use your HF **access token** (not your
account password).

> Note: this repo's `.gitignore` already excludes `.env`, `leads.db`, and
> `sites/`. Do not remove those lines.

---

## Required secrets (Settings → Variables and secrets)

Add these as **Secrets** (not public variables):

| Secret | Value |
|---|---|
| `AGENTROUTER_BASE_URL` | `https://agentrouter.org/v1` |
| `AGENTROUTER_API_KEY` | your AgentRouter key |
| `GOOGLE_PLACES_API_KEY` | your Google Places key |
| `CLOUDFLARE_API_TOKEN` | Cloudflare → My Profile → API Tokens (perm: Account · Cloudflare Pages · Edit) |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare dashboard sidebar / URL |
| `DATABASE_URL` | your Neon pooled connection string (keep `?sslmode=require`) |

Optional: `CLOUDFLARE_PAGES_PROJECT` (default `lead-sites`),
`WHATSAPP_FROM_NUMBER`, `LEAD_REGION`, `WORKER_INTERVAL_SECONDS`.

The dashboard shows a ⚠️ banner if any required secret is missing, and a
**Storage:** line confirming it's using Postgres.

---

## After it boots
- Open the Space → **Dashboard** tab → click **🔌 Test AgentRouter** (should go green).
- Click **⚙️ Build next site** once to smoke-test the full pipeline.
- Open the **AI IDE** tab to edit any generated site (Monaco editor).
