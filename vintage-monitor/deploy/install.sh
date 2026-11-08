#!/usr/bin/env bash
# Installs Vintage Monitor as a background service on Ubuntu 24.04.
# Run from the cloned repo:  sudo /opt/vintage-monitor/vintage-monitor/deploy/install.sh
# Safe to run again; it never overwrites an existing secrets file.
set -euo pipefail

REPO_DIR=/opt/vintage-monitor
APP_DIR="$REPO_DIR/vintage-monitor"
ETC_DIR=/etc/vintage-monitor
ENV_FILE="$ETC_DIR/.env"
STATE_DIR=/var/lib/vintage-monitor
SERVICE_USER=vmonitor
SERVICE=vintage-monitor
UNIT="/etc/systemd/system/$SERVICE.service"
WRAPPER=/usr/local/bin/vmonitor

die() { echo "ERROR: $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run this with sudo:  sudo $0"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ "$here" = "$APP_DIR" ] || die "the project must be at $APP_DIR, but it is at $here (see README)."
command -v python3 >/dev/null || die "python3 is not installed."
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || die "Python 3.11 or newer is needed; this server has $(python3 --version 2>&1)."
command -v systemctl >/dev/null || die "systemd not found; this script is for Ubuntu."

echo "1/5 Service user"
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$SERVICE_USER"
  echo "    created user $SERVICE_USER"
else
  echo "    user $SERVICE_USER already exists"
fi

echo "2/5 Secrets file"
install -d -m 750 -o root -g "$SERVICE_USER" "$ETC_DIR"
if [ ! -f "$ENV_FILE" ]; then
  install -m 640 -o root -g "$SERVICE_USER" "$APP_DIR/.env.example" "$ENV_FILE"
  echo "    created $ENV_FILE from the template"
else
  echo "    $ENV_FILE already exists (left as it is)"
fi
chown root:"$SERVICE_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"

echo "3/5 Data folder"
install -d -m 750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$STATE_DIR"

echo "4/5 Checking the code and config"
cd "$APP_DIR"
if ! PYTHONDONTWRITEBYTECODE=1 python3 -m vintage_monitor validate --config "$APP_DIR/config.toml" >/dev/null; then
  die "config.toml has a mistake (shown above); not installing."
fi
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t . -q 2>&1 | tail -n 3 \
  || die "the built-in tests failed; not installing."

echo "5/5 Background service"
install -m 644 "$APP_DIR/deploy/$SERVICE.service" "$UNIT"
install -m 755 "$APP_DIR/deploy/vmonitor" "$WRAPPER"
systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null 2>&1

if grep -q 'PASTE_' "$ENV_FILE"; then
  systemctl stop "$SERVICE" 2>/dev/null || true
  cat <<EOF

Installed, but NOT started: the secrets file still has placeholders.
  1. sudo nano $ENV_FILE        (replace each PASTE_... value, save with Ctrl+O, exit with Ctrl+X)
  2. vmonitor test-alert        (should make your phone buzz)
  3. vmonitor check             (should list real eBay listings)
  4. sudo systemctl restart $SERVICE
EOF
else
  systemctl restart "$SERVICE"
  sleep 3
  if systemctl is-active --quiet "$SERVICE"; then
    echo
    echo "Installed and running. A startup message should appear in Discord."
    echo "Check any time with:  vmonitor status"
  else
    echo
    echo "Installed, but the service didn't stay running. Recent log:"
    journalctl -u "$SERVICE" -n 20 --no-pager || true
    exit 1
  fi
fi
