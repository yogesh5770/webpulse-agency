#!/usr/bin/env bash
# ============================================================
# One-time setup for the Lead->Website app on a fresh Ubuntu EC2 box.
# Run as the 'ubuntu' user:  bash setup_ec2.sh
# ============================================================
set -euo pipefail

APP_DIR=/opt/leadfactory
REPO_URL="${REPO_URL:-}"   # optional: set to git clone; else copy files yourself

echo "==> Installing system packages (python, git, caddy for HTTPS)"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git curl

# Caddy gives us automatic HTTPS in front of Gradio (port 7860).
if ! command -v caddy >/dev/null 2>&1; then
  sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list
  sudo apt-get update -y
  sudo apt-get install -y caddy
fi

echo "==> Creating app dir at $APP_DIR"
sudo mkdir -p "$APP_DIR"
sudo chown "$USER":"$USER" "$APP_DIR"

if [ -n "$REPO_URL" ]; then
  echo "==> Cloning $REPO_URL"
  git clone "$REPO_URL" "$APP_DIR"
else
  echo "==> REPO_URL not set — make sure you've copied the app files into $APP_DIR"
fi

cd "$APP_DIR"

echo "==> Python venv + deps"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

if [ ! -f "$APP_DIR/.env" ]; then
  echo "==> No .env found — copying template. EDIT IT with your real secrets!"
  cp .env.example .env
  chmod 600 .env
fi

echo "==> Installing systemd service"
sudo cp deploy/leadfactory.service /etc/systemd/system/leadfactory.service
sudo systemctl daemon-reload
sudo systemctl enable leadfactory
sudo systemctl restart leadfactory

echo "==> Done. Next steps:"
echo "   1. Edit $APP_DIR/.env with your real keys, then: sudo systemctl restart leadfactory"
echo "   2. Point Caddy at your domain (edit /etc/caddy/Caddyfile):"
echo "        your-domain.com {"
echo "            reverse_proxy localhost:7860"
echo "        }"
echo "      then: sudo systemctl reload caddy"
echo "   3. Watch logs:  journalctl -u leadfactory -f"
