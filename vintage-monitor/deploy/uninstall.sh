#!/usr/bin/env bash
# Removes the Vintage Monitor service.
#   sudo ./uninstall.sh           keeps the secrets file and database
#   sudo ./uninstall.sh --purge   also deletes them and the service user
# The code in /opt/vintage-monitor is left alone either way.
set -euo pipefail

SERVICE=vintage-monitor
die() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || die "run this with sudo:  sudo $0"

systemctl disable --now "$SERVICE" 2>/dev/null || true
rm -f "/etc/systemd/system/$SERVICE.service" /usr/local/bin/vmonitor
systemctl daemon-reload 2>/dev/null || true
echo "Service removed."

if [ "${1:-}" = "--purge" ]; then
  rm -rf /etc/vintage-monitor /var/lib/vintage-monitor
  if id vmonitor >/dev/null 2>&1; then userdel vmonitor; fi
  echo "Secrets file, database and service user deleted."
else
  echo "Kept /etc/vintage-monitor (secrets) and /var/lib/vintage-monitor (database)."
  echo "Use --purge to delete them too."
fi
