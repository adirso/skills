# Architecture, decisions and risks

## Overview

```
Browser (React SPA)  ──HTTP, same origin──▶  FastAPI (127.0.0.1:8765)
                                               ├─ Project registry (projects.json)
                                               ├─ Per-project SQLite (WAL) + thumbnail cache
                                               ├─ JobManager (1 worker thread / project)
                                               │    └─ pipeline: scan → per-photo → embed → organize
                                               ├─ Selection engine, review, compare, export
                                               └─ VisionProvider: none | ollama | claude_code | anthropic_api
```

No Redis, Docker or external database: one process, SQLite per project, a thread pool for
per-photo work. The same process serves the built frontend.

### Data model (per project, `project.db`)

`photos` (path, size/mtime, sha256, phash, EXIF, status, stage flags, duplicate_of,
group_id, segment_id) · `quality` (separate signals + details) · `faces` (box, landmarks,
128-d descriptor, sharpness, frontal, eye-blink, person_id, assignment auto/user/ignored,
excluded persons, confidence, uncertain) · `persons` (name, role, importance, hidden) ·
`embeddings` (CLIP) · `events` (category, confidence, source clip/vlm/user) ·
`user_state` (decision, favorite, rating, reviewed) · `compare_decisions` ·
`selection` + `selection_runs` · `ai_cache` (content hash, provider, model, prompt
version, config hash) · `usage_log` · `jobs` · `settings`.

### Restart safety

Each per-photo stage has a flag set in the same transaction as its results. A crash or
cancel leaves completed photos done; the next run processes only the rest. Jobs left
`running` are marked `interrupted` at startup.

## Key decisions

| Area | Choice | Why / alternatives rejected |
|---|---|---|
| Face detection | OpenCV Zoo **YuNet** (MIT) | Tiny, fast, CPU, ships landmarks. RetinaFace/InsightFace models are non-commercial. |
| Face descriptors | OpenCV Zoo **SFace** (Apache-2.0) | Commercial-friendly; InsightFace `buffalo_l` (ArcFace) is more accurate but its pretrained weights are non-commercial. |
| Eye state | **MediaPipe Face Landmarker** blendshapes (Apache-2.0) | Direct `eyeBlinkLeft/Right` scores; Haar eye cascades are unreliable. |
| Embeddings | **OpenCLIP ViT-B/32, LAION-2B** (MIT) on MPS/CUDA/CPU | Good similarity + zero-shot moments; small enough for laptops. |
| Clustering | k-NN graph + Chinese Whispers + centroid merge, with a "once per photo" cannot-link constraint | Scales to 40k faces in seconds, no fixed cluster count; agglomerative is O(n²) memory. |
| Quality | Classical CV (Laplacian tiles, clipping, Immerkær noise, Hasler–Süsstrunk, spectral-residual saliency) | Objective, explainable, fast; learned aesthetic models were avoided (opaque, "attractiveness" risk). |
| Local VLM | **Ollama** (optional) | Easiest cross-platform runtime with model management and JSON-schema output; recommended models are Apache-2.0 Qwen3-VL. |
| Claude Code | `claude -p` stream-json with base64 images, tools disabled | Documented headless mode; no credential reuse. |
| Claude API | Official `anthropic` SDK, structured outputs, effort `low`, server-side refusal fallback for Opus/Sonnet 5.5 | Per guidance in Anthropic's API reference. |
| Folder access | Backend-assisted: native picker (osascript / PowerShell / zenity) or typed path, validated server-side | Browser folder pickers cannot give a persistent path for incremental re-scans. |
| Frontend | React 19, Vite 8, Tailwind 4, TanStack Query + Virtual | Virtualized grid handles 8k+ tiles; logical CSS properties give real RTL. |

### Models

| Id | File | Size | SHA-256 (pinned) | License |
|---|---|---|---|---|
| yunet | face_detection_yunet_2023mar.onnx | 232,589 B | 8f2383e4…d2552fa4 | MIT |
| sface | face_recognition_sface_2021dec.onnx | 38,696,353 B | 0ba9fbfa…87c34e79 | Apache-2.0 |
| face_landmarker | face_landmarker.task (float16 v1) | 3,758,596 B | 64184e22…4e0bc9ff | Apache-2.0 |
| clip_vit_b32 | open_clip_model.safetensors | 605,143,316 B | ac4f8c4b…352656e6 | MIT |

Full hashes are in `backend/wac/models_registry.py`. Downloads happen only through an
explicit approval (UI button or `wac models --download … ` with confirmation).

## Security & privacy

- Binds to 127.0.0.1; refuses other hosts unless an undocumented override flag is passed.
- Host-header allow-list (DNS rebinding), Origin check, per-launch HttpOnly
  SameSite=Strict session cookie for all `/api` calls.
- Photos are served by database id only; relative paths are re-validated (`safe_join`).
  The scanner does not follow symlinks. Export refuses destinations inside the source
  folder or non-empty folders.
- Untrusted images: Pillow decompression-bomb limit (200 MP, warnings are errors), max
  file size, defensive EXIF parsing (dates sanity-checked), all decode errors captured
  per photo. Model JSON output is validated and clamped.
- Cloud: consent recorded per provider and tied to the warning text version; checked by
  the backend before any upload; API key kept server-side (keychain/0600 file).

## Technical risks (and mitigations)

| Risk | Mitigation |
|---|---|
| Face grouping errors (twins, kids, profiles, lighting) | Conservative thresholds; durable user corrections; uncertain queue. |
| Bursts hide cross-photo identity links | Centroid-merge pass (found in benchmarking; regression test added). |
| Wrong camera clocks / multiple cameras | Time only smooths classification and bounds burst detection; never overrides content. |
| Small local VLMs hallucinate | VLM output is advisory (moment label only when confident; user always wins). |
| Claude Code CLI flags change | Isolated in one module; "Test connection" button; documented as experimental. |
| Large libraries / slow disks | Incremental scan, JPEG draft decoding, bounded thread pool, chunked writes, virtualized UI. |
| PyTorch install size | `--core` install option; app degrades gracefully without CLIP. |
