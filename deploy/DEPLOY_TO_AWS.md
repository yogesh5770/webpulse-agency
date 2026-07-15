# Deploy to AWS EC2 + Neon Postgres

This runs the whole factory — Gradio dashboard **and** the 24/7 worker — on one
always-on EC2 instance, with leads and generated site files stored in **Neon**
serverless Postgres. Generated client sites publish to **Cloudflare Pages**.

```
                 ┌─────────────────────────────────────┐
   You  ─HTTPS─▶ │  EC2  (Ubuntu, t3.small)             │
                 │   Caddy :443  ──▶  Gradio app.py :7860│
                 │      • dashboard (frontend)          │
                 │      • 24/7 worker (backend thread)  │
                 └───────────────┬──────────────────────┘
                                 │ psycopg2 (SSL)
                                 ▼
                 ┌─────────────────────────────────────┐
                 │  Neon serverless Postgres            │
                 │   leads + generated site files       │
                 └─────────────────────────────────────┘
                                 │ deploy()
                                 ▼
                 Cloudflare Pages  →  <business>.lead-sites.pages.dev
```

Why Neon over RDS: free tier, no VPC/security-group wiring, connects over the
public internet with SSL, and scales to zero when idle. The app opens a fresh
connection per operation, which suits Neon's autosuspend perfectly.

## 1. Create the Neon database
1. Sign up at neon.tech → **Create project** (pick a region near your EC2).
2. Name the database `leads`.
3. Copy the **pooled** connection string from the dashboard (Connection Details
   → "Pooled connection"). It looks like:
   ```
   postgresql://<user>:<pass>@ep-xxxx-pooler.<region>.aws.neon.tech/leads?sslmode=require
   ```
   That whole string is your `DATABASE_URL`. Keep `sslmode=require`.

No inbound firewall rules needed — Neon is reachable over the public internet
and secured by SSL + credentials.

## 2. Launch EC2
1. EC2 → Launch instance → **Ubuntu 22.04**, `t3.small` (worker runs 24/7).
2. Security group inbound: **443** and **80** from anywhere (Caddy/HTTPS),
   **22** from your IP only.
3. Attach at least **20 GB** EBS (git checkpoints + temp site builds).

## 3. Install the app
SSH in, copy the project to the box (or set `REPO_URL`), then:
```bash
cd /opt/leadfactory        # or wherever you copied the files
export REPO_URL=<your-git-url>   # optional; skip if files already copied
bash deploy/setup_ec2.sh
```
This installs Python + Caddy, creates a venv, installs deps, installs the
systemd service, and starts it.

## 4. Configure secrets
```bash
sudo nano /opt/leadfactory/.env
```
Fill in:
- `AGENTROUTER_BASE_URL`, `AGENTROUTER_API_KEY`, `AGENTROUTER_MODEL`
- `GOOGLE_PLACES_API_KEY`
- `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_PAGES_PROJECT`
- `DATABASE_URL` → your Neon pooled connection string from step 1
- `WHATSAPP_FROM_NUMBER`

Then restart:
```bash
sudo systemctl restart leadfactory
```

## 5. HTTPS with your domain
Point an A record at the EC2 public IP, then:
```bash
sudo nano /etc/caddy/Caddyfile
```
```
your-domain.com {
    reverse_proxy localhost:7860
}
```
```bash
sudo systemctl reload caddy
```
Caddy fetches a TLS cert automatically. Dashboard is now at `https://your-domain.com`.

## Operations
| Task | Command |
|------|---------|
| Live logs | `journalctl -u leadfactory -f` |
| Restart | `sudo systemctl restart leadfactory` |
| Stop | `sudo systemctl stop leadfactory` |
| Status | `systemctl status leadfactory` |
| Update code | copy/pull new files → `sudo systemctl restart leadfactory` |

## Notes
- **Gradio has no auth by default.** Anyone with the URL can use the dashboard.
  Put Caddy basic-auth in front, or restrict the security group, before exposing
  it publicly. (Flagging this — the dashboard controls your API spend.)
- The worker starts only when you click **▶️ Start 24/7 worker** in the
  dashboard; it is not auto-started on boot.
