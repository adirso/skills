# Wedding Album Curator

A local-first application (and Claude Code skill) that helps a couple go from 3,000–8,000
wedding photos to an album of ~500 — calmly, with recommendations that explain themselves
and never take the decision away from them.

- **Private by default** — photos, faces and analysis stay on your computer. Originals are
  never modified. No telemetry. Cloud analysis is optional, opt-in, and consent-gated.
- **Discovers people** — local face detection and conservative grouping; you name people,
  mark the bride and groom, set importance, merge/split groups.
- **Finds problems** — blur, exposure, noise, composition, closed eyes, faces cut off or
  turned away, exact duplicates and burst/near-duplicate shots — as separate signals.
- **Compares** near-identical shots side by side with a recommended pick and reasons.
- **Builds the album** — a diversity-aware engine balances quality, the couple, important
  people, key moments and visual variety; respects your locks and rejections; reports
  shortfalls instead of padding.
- **Learns your taste** from favorites and comparisons (transparent linear model on CLIP
  embeddings; resettable).
- **Exports** byte-identical originals with a verified manifest.
- English and Hebrew (full RTL), dark theme by default.

## Quick start

```bash
scripts/install.sh --with-skill   # Python backend + frontend build (+ links the Claude Code skill)
scripts/launch.sh                 # opens http://127.0.0.1:8765
```

Requirements: Python 3.11/3.12 (or [uv](https://docs.astral.sh/uv/)), Node.js 20+.
The installer does **not** download AI models — the app asks for approval first (≈650 MB
total; see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#models)). No real photos at hand?
`scripts/wac sample-dataset ~/WAC-sample` creates a synthetic demo folder.

Other commands: `scripts/wac doctor | hardware | models | benchmark <folder>`,
`scripts/stop.sh`, `scripts/update.sh`, `scripts/test.sh`.

### With Claude Code

After `install.sh --with-skill`, ask Claude Code things like *"launch the wedding album
app"*, *"check if my computer can run local AI for the wedding album"*, or *"why are no
people showing up?"*. The skill lives in [`skills/wedding-album-curator`](skills/wedding-album-curator/SKILL.md).

## Using the app

1. **Onboarding** — name the project, pick the folder (native folder picker or path), choose
   the AI method, review hardware and approve model downloads, read the privacy notes, start.
2. **Overview** — progress, counts, next steps, measured speed.
3. **People** — mark the bride and groom (required), name people, set importance, fix groups.
4. **Compare** — keep the best of each similar-shot group (couple-only mode available).
5. **Review Queue** — closed eyes, couple issues, blur, exposure, composition, duplicates,
   uncertain faces/moments. Nothing is deleted.
6. **Album Builder** — target size (default 500), moment allocation, weights; generate,
   lock, replace, regenerate (locks are kept).
7. **Export** — copy approved originals to a new folder (optionally by moment) with a
   CSV/JSON manifest; missing source files are reported.
8. **AI & Privacy** — provider, consent, API key, spending limit, estimates, usage, and
   deletion of face data / AI results / embeddings / thumbnails / the project.

Keyboard in the viewer: ←/→ navigate · P select · X reject · U undecided · F favorite ·
1–5 rate · Z zoom · Esc close (arrows follow reading direction in Hebrew).

## AI options

| Option | Needs | Data leaves the computer? | Cost |
|---|---|---|---|
| Local analysis only (default) | nothing | no | free |
| Local AI via Ollama | Ollama + a vision model | no | free |
| Claude via Claude Code (experimental) | Claude Code CLI | yes, downscaled photos | counts against your Claude Code plan/billing |
| Claude API | your Anthropic API key | yes, downscaled photos | pay per token; estimate + app-enforced limit |

Details and caveats: [skills/wedding-album-curator/reference/providers.md](skills/wedding-album-curator/reference/providers.md).

## Status: what works and what does not

Working and tested: ingestion (JPEG/PNG/WebP/TIFF/HEIC), incremental & resumable analysis,
thumbnails, quality signals, face detection/grouping/corrections, eye-state, near-duplicate
groups, CLIP moments, album engine, compare, review queues, preference learning, export,
provider abstraction with caching/consent/budget, Ollama provider (verified live with a
local model), EN/HE UI.

Known limitations:

- **Claude Code and Anthropic API providers are not live-tested** in development (to avoid
  spending the developer's usage). They are covered by tests against a fake CLI / mocked
  client. Use "Test with a synthetic image" in the app before a real run.
- **Face grouping is probabilistic.** It was verified on real public-domain portraits
  (same person matched across photos at 0.82–0.84 similarity vs ≤ 0.27 for others), but not
  on a real wedding set. Expect to merge a few groups (profiles, sunglasses, kids).
- **Closed-eye detection** is only marked reliable for reasonably large, frontal faces.
- **Moment classification** is zero-shot CLIP + time smoothing; it is a starting point the
  user corrects. Wedding traditions vary; categories are editable per photo.
- **Composition** is a heuristic (subject placement and faces cut off), not an aesthetic judgment.
- RAW formats (CR3/NEF/ARW…) are not supported; export the photographer's JPEGs.
- Backend-generated explanation text (album reasons, review reasons) is English only;
  the UI chrome is fully translated.
- Native Windows is untested (WSL2 expected to work).

## Repository layout

```
backend/    FastAPI app, analysis pipeline, providers, tests (Python package `wac`)
frontend/   React + TypeScript + Vite + Tailwind UI
skills/     Claude Code skill (SKILL.md, reference docs, locate script)
scripts/    install / launch / stop / update / test / wac CLI wrapper
docs/       architecture, decisions, risks, benchmarks
```

## Tests

`scripts/test.sh` — 51 backend tests (ingestion, safety, duplicates, metadata, clustering
corrections, selection, locks/rejections, allocations, provider switching, cache
invalidation, consent, budgets, export correctness, interrupted-run recovery, API
security) plus a frontend type-check. Set `WAC_TEST_MODELS_DIR` to a folder with the
downloaded models to also run real face-model tests. Test fixtures are public-domain NASA
portraits; no wedding photos are included.
