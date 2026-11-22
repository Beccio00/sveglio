#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# Remove sveglio and lid-guard.
#
#   ./uninstall.sh            keep your configuration in /etc/sveglio
#   ./uninstall.sh --purge    remove /etc/sveglio too
#
# Use the same PREFIX you installed with (default: /usr/local).
set -euo pipefail

PREFIX=${PREFIX:-/usr/local}
CONFDIR=/etc/sveglio

if [[ $EUID -eq 0 ]]; then
  as_root=()
else
  as_root=(sudo)
  systemctl --user stop sveglio.service 2>/dev/null || true
fi

# Stopping lid-guard releases every blocked device and turns the screen back on.
"${as_root[@]}" systemctl disable --now lid-guard.service 2>/dev/null || true
"${as_root[@]}" rm -f \
  "$PREFIX/bin/sveglio" \
  "$PREFIX/sbin/lid-guard" \
  "$PREFIX/lib/systemd/user/sveglio.service" \
  "$PREFIX/lib/systemd/system/lid-guard.service"
"${as_root[@]}" rm -rf "$PREFIX/libexec/sveglio"
if [[ ${1:-} == --purge ]]; then
  "${as_root[@]}" rm -rf "$CONFDIR"
fi
"${as_root[@]}" systemctl daemon-reload
if [[ $EUID -ne 0 ]]; then
  systemctl --user daemon-reload
fi
echo "sveglio removed. Users who had it on: it stops at their next logout."
