#!/usr/bin/env bash
# Print the Wedding Album Curator app root. Search order:
#   1. $WAC_HOME
#   2. the repository containing this skill (when the skill folder is a symlink into the repo)
#   3. ~/wedding-album-curator, ~/Development/wedding-album-curator
set -euo pipefail
is_root() { [ -f "$1/scripts/launch.sh" ] && [ -f "$1/backend/pyproject.toml" ]; }
if [ -n "${WAC_HOME:-}" ] && is_root "$WAC_HOME"; then echo "$WAC_HOME"; exit 0; fi
here="$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "${BASH_SOURCE[0]}")"
cand="$(cd "$(dirname "$here")/../../.." && pwd)"
if is_root "$cand"; then echo "$cand"; exit 0; fi
for c in "$HOME/wedding-album-curator" "$HOME/Development/wedding-album-curator"; do
  if is_root "$c"; then echo "$c"; exit 0; fi
done
echo "Wedding Album Curator not found. Set WAC_HOME to the app folder, or see reference/install.md." >&2
exit 1
