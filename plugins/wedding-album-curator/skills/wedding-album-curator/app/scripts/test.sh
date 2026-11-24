#!/usr/bin/env bash
# Run the automated tests. Set WAC_TEST_MODELS_DIR to a folder with downloaded models to include real-model tests.
source "$(dirname "$0")/_common.sh"
cd "$WAC_ROOT/backend"
"$WAC_VENV/bin/pip" show pytest >/dev/null 2>&1 || (command -v uv >/dev/null && VIRTUAL_ENV="$WAC_VENV" uv pip install -e ".[dev]" || "$WAC_VENV/bin/pip" install -e ".[dev]")
"$WAC_VENV/bin/python" -m pytest -q "$@"
(cd "$WAC_ROOT/frontend" && npm run typecheck)
