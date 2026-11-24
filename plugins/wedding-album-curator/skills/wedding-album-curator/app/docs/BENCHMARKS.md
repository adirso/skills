# Measured benchmarks

Machine: Apple M4 Pro (14 CPU cores, 20-core GPU), 48 GB unified memory, macOS, Python
3.12, PyTorch 2.15 (MPS), OpenCV 5.1. Measured on 2026-11-23. Reproduce with
`scripts/wac benchmark <folder>` (it never modifies the folder).

## Full pipeline, 300 × 24-megapixel JPEGs (6000×4000)

Synthetic scenes plus public-domain portraits upscaled to camera resolution (0.95 GB).

| Stage | Time | Throughput |
|---|---|---|
| Decode + preview/thumbnail + hashes + quality + faces + eye state | 13.9 s | **21.6 photos/s** |
| CLIP embeddings (MPS, includes model load) | 9.2 s | ~33 photos/s |
| Duplicates, similar groups, people, moments | 0.12 s | — |
| Album selection (target 100) | 0.014 s | — |

Extrapolated (not measured) for 8,000 photos on this machine: ≈ 6 min per-photo analysis +
≈ 4 min embeddings. Real camera JPEGs with more detail may decode somewhat slower.

## Components at wedding scale (in-memory, synthetic data)

| Workload | Time |
|---|---|
| Selection engine: 8,000 candidates → 500 (512-d embeddings, people, groups) | 0.5 s |
| Face clustering: 40,000 descriptors (400 synthetic identities) | 7.8 s |

The clustering run recovered all 400 synthetic identities, but synthetic identities are
far cleaner than real faces — treat this as a speed figure, not an accuracy claim.

## Face identity on real photos (public-domain NASA portraits)

- 7 of 7 faces detected in the crew group photo (~100 ms per 1280 px image).
- Same person in a solo portrait vs. their face in the group photo: cosine similarity
  0.84 and 0.82; best wrong match 0.27.
- 60 upscaled 6000 px copies (20 bursts each of 3 photos): 180 faces → 7 people (correct)
  after the centroid-merge fix; 9 people before it.

## Local VLM (Ollama, optional)

- `moondream` (1.7 GB): 3.2 s per photo; output quality poor (wrong caption, false
  closed-eye flags) — illustrates why VLM output is advisory only.
- `llama3.2-vision`: failed to load on the installed Ollama version ("unknown model
  architecture: 'mllama'") — the app surfaces this message.
