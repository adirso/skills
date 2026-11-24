#!/usr/bin/env bash
# Install (or update) the app bundled with this skill into a stable folder, then run its
# installer. Used when the skill came from a plugin marketplace: the plugin folder is
# replaced on every plugin update, so the app (and its Python environment) live outside it.
#
#   bootstrap.sh [--core]      target: $WAC_HOME, default ~/wedding-album-curator
#
# Never touches user data (projects, models) — those live in the per-user data folder.
set -euo pipefail
here="$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "${BASH_SOURCE[0]}")"
skill_dir="$(cd "$(dirname "$here")/.." && pwd)"
bundle="$skill_dir/app"
target="${WAC_HOME:-$HOME/wedding-album-curator}"

if [ ! -f "$bundle/scripts/install.sh" ]; then
  # development checkout: the skill lives inside the app repository itself
  root="$(cd "$skill_dir/../.." && pwd)"
  if [ -f "$root/scripts/install.sh" ]; then exec "$root/scripts/install.sh" "$@"; fi
  echo "No bundled app found in $bundle" >&2; exit 1
fi

if [ -e "$target" ] && [ ! -f "$target/.wac-bundle" ] && [ ! -f "$target/scripts/launch.sh" ]; then
  echo "$target exists and is not a Wedding Album Curator folder; set WAC_HOME to another path." >&2
  exit 1
fi
mkdir -p "$target"
# copy the app code; keep the existing Python env, node_modules and build output
rsync -a --delete \
  --exclude '.venv/' --exclude 'node_modules/' --exclude 'frontend/dist/' --exclude '__pycache__/' \
  "$bundle/" "$target/"
cp "$skill_dir/VERSION" "$target/.wac-bundle" 2>/dev/null || date > "$target/.wac-bundle"
echo "App code copied to $target"
exec "$target/scripts/install.sh" "$@"
