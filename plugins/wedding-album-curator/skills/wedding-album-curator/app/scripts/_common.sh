# Shared helpers for Wedding Album Curator scripts (sourced, not executed).
set -euo pipefail
WAC_ROOT="$(cd "$(dirname "$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "${BASH_SOURCE[0]}")")/.." && pwd)"
WAC_VENV="$WAC_ROOT/backend/.venv"
WAC_BIN="$WAC_VENV/bin/wac"
WAC_PORT="${WAC_PORT:-8765}"
info() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }
