#!/usr/bin/env bash
# One-time preparation of a fresh Ubuntu/Debian server for f1laps.
# Run as root:  bash server-setup.sh
# Creates a "deploy" user that GitHub Actions logs in as, installs Docker,
# and prepares /opt/f1laps.
set -euo pipefail

DEPLOY_USER=${DEPLOY_USER:-deploy}
APP_DIR=/opt/f1laps

if ! command -v docker >/dev/null 2>&1; then
  echo ">> Installing Docker"
  curl -fsSL https://get.docker.com | sh
fi

if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  echo ">> Creating user $DEPLOY_USER"
  useradd --create-home --shell /bin/bash "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"

mkdir -p "$APP_DIR" "/home/$DEPLOY_USER/.ssh"
chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"
chmod 700 "/home/$DEPLOY_USER/.ssh"
touch "/home/$DEPLOY_USER/.ssh/authorized_keys"
chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"

if [ ! -f "$APP_DIR/.env" ]; then
  cat > "$APP_DIR/.env" <<'ENV'
SITE_ADDRESS=:80
F1LAPS_SEASONS=2025,2026
F1LAPS_REFRESH_DAYS=fri,sat,sun
F1LAPS_REFRESH_TIME=23:30
F1LAPS_REFRESH_TZ=UTC
F1LAPS_LOG_LEVEL=INFO
ENV
  chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR/.env"
fi

if command -v ufw >/dev/null 2>&1; then
  ufw allow OpenSSH >/dev/null || true
  ufw allow 80/tcp >/dev/null || true
  ufw allow 443 >/dev/null || true
fi

cat <<MSG

Done. Next steps:
  1. Add the public half of the deploy key to /home/$DEPLOY_USER/.ssh/authorized_keys
  2. Edit $APP_DIR/.env (domain, time zone, seasons)
  3. In GitHub -> Settings -> Secrets and variables -> Actions add:
       DEPLOY_HOST  (this server's hostname or IP)
       DEPLOY_USER  ($DEPLOY_USER)
       DEPLOY_SSH_KEY  (the private key, PEM/OpenSSH format)
       DEPLOY_PORT  (optional, default 22)
  4. Push to main (or run the "Deploy" workflow manually).
MSG
