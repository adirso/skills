#!/usr/bin/env bash
# Stop a running Wedding Album Curator server started from this installation.
source "$(dirname "$0")/_common.sh"
PIDS=$(pgrep -f "$WAC_VENV/bin/.*wac serve" || true)
[ -n "$PIDS" ] || { info "Not running."; exit 0; }
kill $PIDS && info "Stopped (pid $PIDS). Running jobs resume where they left off next time."
