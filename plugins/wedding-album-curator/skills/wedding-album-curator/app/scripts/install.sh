#!/usr/bin/env bash
# Install Wedding Album Curator: Python backend (+ local ML extras) and the web frontend.
# Usage: scripts/install.sh [--core] [--with-skill]
#   --core        skip PyTorch/OpenCLIP/MediaPipe (no similarity embeddings, moments or eye detection)
#   --with-skill  link the Claude Code skill into ~/.claude/skills/wedding-album-curator
# Models are NOT downloaded here; approve them in the app or with `scripts/wac models --download all`.
source "$(dirname "$0")/_common.sh"
EXTRAS="ml,cloud"; SKILL=0
for a in "$@"; do case "$a" in --core) EXTRAS="cloud";; --with-skill) SKILL=1;; -h|--help) sed -n '2,7p' "$0"; exit 0;; *) fail "unknown option $a";; esac; done

info "Checking prerequisites"
command -v node >/dev/null || fail "Node.js 20+ is required (https://nodejs.org)."
NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]'); [ "$NODE_MAJOR" -ge 20 ] || fail "Node.js 20+ required, found $(node -v)."
if command -v uv >/dev/null; then
  info "Creating Python 3.12 environment with uv"
  [ -d "$WAC_VENV" ] || uv venv --python 3.12 "$WAC_VENV"
  (cd "$WAC_ROOT/backend" && VIRTUAL_ENV="$WAC_VENV" uv pip install -e ".[${EXTRAS}]")
else
  PY=""
  for c in python3.12 python3.11; do command -v $c >/dev/null && PY=$c && break; done
  [ -n "$PY" ] || fail "Python 3.11 or 3.12 is required (or install uv: https://docs.astral.sh/uv/)."
  info "Creating Python environment with $PY"
  [ -d "$WAC_VENV" ] || $PY -m venv "$WAC_VENV"
  "$WAC_VENV/bin/pip" install --upgrade pip >/dev/null
  (cd "$WAC_ROOT/backend" && "$WAC_VENV/bin/pip" install -e ".[${EXTRAS}]")
fi

info "Building the frontend"
(cd "$WAC_ROOT/frontend" && npm ci --no-audit --no-fund && npm run build)

if [ "$SKILL" = 1 ]; then
  mkdir -p "$HOME/.claude/skills"
  ln -sfn "$WAC_ROOT/skills/wedding-album-curator" "$HOME/.claude/skills/wedding-album-curator"
  info "Linked Claude Code skill to ~/.claude/skills/wedding-album-curator"
fi

info "Checking the installation"
"$WAC_BIN" doctor || true
echo
info "Done. Start the app with: scripts/launch.sh"
info "Local models are downloaded only after you approve them (in the app, or: scripts/wac models --download all)."
