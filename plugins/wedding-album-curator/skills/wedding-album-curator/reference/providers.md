# AI providers

The core analysis is **always local** and needs no account: face detection and grouping,
technical quality, near-duplicates, CLIP moment classification and preference learning.
A provider adds optional *semantic* analysis per photo (moment, emotional significance,
short caption). Results are cached per photo content hash + provider + model + prompt
version + settings, so switching providers keeps earlier results. The app never switches
from local to cloud on its own.

## Local AI — Ollama (recommended for privacy)

1. Install Ollama from https://ollama.com and start it.
2. In the app: AI & Privacy → "Local AI". The app lists recommended models for the
   detected memory (qwen3-vl 2b/4b/8b/30b-a3b instruct variants) and downloads one only
   after the user clicks approve. Any installed Ollama model with vision support can be chosen.
3. Only `localhost` Ollama URLs are accepted.

Small models (e.g. moondream) run in a few seconds per photo but their descriptions and
"issues" are unreliable — treat them as hints. Some older Ollama models may fail to load on
newer Ollama versions; the app shows Ollama's own error message.

## Claude via Claude Code (experimental)

- Uses the documented headless mode: `claude -p --input-format stream-json
  --output-format stream-json --tools "" --strict-mcp-config --no-session-persistence
  --json-schema …`. Each photo (downscaled to 1024 px) is sent as a base64 image.
  All Claude Code tools are disabled, so Claude cannot read or change files.
- The app never reads Claude Code's credentials; the `claude` binary authenticates itself.
- Usage counts against the user's Claude Code plan limits or configured API billing. The
  app cannot see the remaining allowance. Any cost the CLI reports is shown as "cli_reported".
- One process per photo is slow; intended for the shortlisted album photos.
- Requires explicit consent to the warning shown in the app. Use "Test with a synthetic
  image" after Claude Code updates (flags can change between versions).

## Claude API (pay per use)

- The user enters their own Anthropic API key in the app (stored in the OS keychain when
  available, otherwise a user-only file) or sets `ANTHROPIC_API_KEY`. The key never reaches
  the browser.
- Models offered: Claude Opus 5.5 (default), Sonnet 5.5, Haiku 5.5. Prices are list prices
  recorded on 2026-11-03 (verify at https://www.anthropic.com/pricing).
- Before running, the app shows an estimate (typical and worst case) based on image size
  (≈1 token per 28×28 px patch) plus prompt and output allowances. Actual cost is computed
  from the token usage returned with each response.
- **Spending limit:** enforced by the app before each request (requests run one at a time
  when a limit is set, and each is checked against its worst-case cost). It is not a limit
  in Anthropic's billing system.
- Requires explicit consent and an explicit "I confirm uploading" checkbox per run.
- Retries on rate limits honor `retry-after`.
