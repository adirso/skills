#!/usr/bin/env bash
# Start Wedding Album Curator on http://127.0.0.1:$WAC_PORT (default 8765) and open the browser.
# Usage: scripts/launch.sh [--no-open]
source "$(dirname "$0")/_common.sh"
[ -x "$WAC_BIN" ] || fail "Not installed yet. Run scripts/install.sh first."
URL="http://127.0.0.1:$WAC_PORT"
if curl -fsS -o /dev/null "$URL/api/session" 2>/dev/null; then
  info "Already running at $URL"
  [ "${1:-}" = "--no-open" ] || (command -v open >/dev/null && open "$URL" || xdg-open "$URL" 2>/dev/null || true)
  exit 0
fi
OPEN="--open"; [ "${1:-}" = "--no-open" ] && OPEN=""
exec "$WAC_BIN" serve --port "$WAC_PORT" $OPEN
