#!/usr/bin/env bash
# Update dependencies and rebuild. If this is a git checkout with a remote, pulls first.
# Your projects, analysis results and models (in the app data folder) are not touched.
source "$(dirname "$0")/_common.sh"
if git -C "$WAC_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 && [ -n "$(git -C "$WAC_ROOT" remote)" ]; then
  info "Pulling latest changes"
  git -C "$WAC_ROOT" pull --ff-only
fi
"$WAC_ROOT/scripts/install.sh" "$@"
