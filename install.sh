#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# Install (or upgrade) sveglio and lid-guard.
#
#   ./install.sh                  install under /usr/local, asking for sudo when needed
#   PREFIX=/usr ./install.sh      install under /usr instead (e.g. for a package)
#
# PREFIX must be /usr/local or /usr: those are the prefixes systemd looks into for units.
# An existing /etc/sveglio/lid-guard.conf is never overwritten.
set -euo pipefail

PREFIX=${PREFIX:-/usr/local}
BINDIR=$PREFIX/bin
SBINDIR=$PREFIX/sbin
LIBEXECDIR=$PREFIX/libexec/sveglio
UNITDIR=$PREFIX/lib/systemd
CONFDIR=/etc/sveglio

cd "$(dirname "$(readlink -f "$0")")"

die() {
  echo "install.sh: $*" >&2
  exit 1
}

for cmd in systemctl systemd-inhibit loginctl busctl; do
  command -v "$cmd" >/dev/null || die "$cmd not found: sveglio needs systemd"
done
[[ -x /usr/bin/python3 ]] || die "/usr/bin/python3 not found: sveglio needs Python 3.10+"
/usr/bin/python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' ||
  die "Python 3.10 or newer is required"

if [[ $EUID -eq 0 ]]; then
  as_root=()
else
  as_root=(sudo)
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
for unit in sveglio.service lid-guard.service; do
  sed -e "s|@SBINDIR@|$SBINDIR|g" -e "s|@LIBEXECDIR@|$LIBEXECDIR|g" "systemd/$unit" >"$tmp/$unit"
done

echo "Installing sveglio into $PREFIX"
"${as_root[@]}" install -Dm755 src/sveglio "$BINDIR/sveglio"
"${as_root[@]}" install -Dm755 src/sveglio_watch.py "$LIBEXECDIR/sveglio-watch"
"${as_root[@]}" install -Dm755 src/lid_guard.py "$SBINDIR/lid-guard"
"${as_root[@]}" install -Dm644 "$tmp/sveglio.service" "$UNITDIR/user/sveglio.service"
"${as_root[@]}" install -Dm644 "$tmp/lid-guard.service" "$UNITDIR/system/lid-guard.service"
if [[ ! -e $CONFDIR/lid-guard.conf ]]; then
  "${as_root[@]}" install -Dm644 config/lid-guard.conf "$CONFDIR/lid-guard.conf"
fi

"${as_root[@]}" systemctl daemon-reload
"${as_root[@]}" systemctl enable lid-guard.service
"${as_root[@]}" systemctl restart lid-guard.service

echo
if [[ $EUID -ne 0 ]]; then
  systemctl --user daemon-reload
  "$BINDIR/sveglio" status
  echo
fi
echo "Done. Other users who are logged in now: run 'systemctl --user daemon-reload' once."
