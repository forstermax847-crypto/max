#!/usr/bin/env bash
# Pulls the latest code and searches from GitHub and restarts the monitor,
# but only if the tests pass and the config is valid. If anything is wrong,
# the server goes back to the previous version and the monitor keeps running.
#
#   sudo /opt/vintage-monitor/vintage-monitor/deploy/update.sh
set -euo pipefail

REPO_DIR=/opt/vintage-monitor
APP_DIR="$REPO_DIR/vintage-monitor"
SERVICE=vintage-monitor

die() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || die "run this with sudo:  sudo $0"
[ -d "$REPO_DIR/.git" ] || die "$REPO_DIR is not a git checkout."

cd "$REPO_DIR"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  die "files in $REPO_DIR were edited on the server. Change things on GitHub instead (or ask Claude)."
fi
before="$(git rev-parse HEAD)"
git pull --ff-only
after="$(git rev-parse HEAD)"
if [ "$before" = "$after" ]; then
  echo "Already up to date."
  exit 0
fi
echo "Updated $(git rev-parse --short "$before") -> $(git rev-parse --short "$after")"

rollback() {
  echo
  echo "Going back to the previous version ($(git -C "$REPO_DIR" rev-parse --short "$before"))."
  git -C "$REPO_DIR" reset --hard --quiet "$before"
  echo "The monitor was NOT restarted and is still running the previous version."
  echo "Fix the problem on GitHub, then run this script again."
  exit 1
}

cd "$APP_DIR"
if ! PYTHONDONTWRITEBYTECODE=1 python3 -m vintage_monitor validate --config "$APP_DIR/config.toml"; then
  echo "config.toml has a mistake (shown above)."
  rollback
fi
if ! PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t . -q; then
  echo "The built-in tests failed with the new code."
  rollback
fi

install -m 644 "$APP_DIR/deploy/$SERVICE.service" "/etc/systemd/system/$SERVICE.service"
install -m 755 "$APP_DIR/deploy/vmonitor" /usr/local/bin/vmonitor
systemctl daemon-reload
systemctl restart "$SERVICE"
sleep 3
if systemctl is-active --quiet "$SERVICE"; then
  echo "Restarted. A startup message should appear in Discord."
else
  echo "The service didn't stay running after the update. Recent log:"
  journalctl -u "$SERVICE" -n 20 --no-pager || true
  exit 1
fi
