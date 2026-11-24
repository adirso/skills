# How Wedding Album Curator works

## 1. Analysis (local, incremental, restart-safe)

1. **Scan** the folder recursively (JPEG, PNG, WebP, TIFF, HEIC/HEIF). Symlinks are not
   followed. Changed files (size/mtime) are re-analyzed; removed files are marked missing.
2. **Per photo** (one decode): EXIF date/camera, orientation fix, thumbnail + preview,
   SHA-256, perceptual hash, face detection + 128-d face descriptors, eye-blink scores,
   and separate quality signals: sharpness (best 10% of tiles, so bokeh is not punished),
   exposure/clipping, contrast, noise (Immerkær), colorfulness, composition.
3. **Embeddings** (CLIP) on previews.
4. **Organize**: exact duplicates (same SHA-256), similar-shot groups (pHash or CLIP
   similarity within 90 s of capture time), people clustering, moment classification
   (CLIP prompts, gently smoothed within timeline segments).

Pause/resume/stop at any time. Each photo's results are written immediately.

## 2. People

Faces are clustered conservatively (Chinese Whispers over a k-NN graph, cosine ≥ 0.45),
with a "once per photo" rule: two faces in the same photo are never the same person, and a
group that has several faces in the same photos is split with a stricter threshold.
"Re-group faces" re-runs grouping in seconds; "Re-scan faces" re-detects every face in the
background (a few minutes) and carries names, roles and corrections over by face position.
The user must mark the bride and groom; nothing is inferred from appearance. Corrections
are durable: merges, splits ("split into new person"), "not this person" (never
re-assigned there), confirm, mark uncertain, ignore. Importance levels and weights are
editable, including custom levels.

## 3. Compare & review

- **Compare** shows each group of near-identical shots side by side with a recommended
  pick and reasons (couple's eyes open, sharper, better exposed…). Keeping one locks it;
  rejecting the others is optional. A "bride & groom only" mode is available.
- **Review queue**: couple issues (closed eyes, looking away, face cut off, possibly
  hidden), closed eyes, blurry, exposure, weak composition, exact duplicates, uncertain
  face matches, uncertain moments. Nothing is deleted; "Looks fine" dismisses an item.

## 4. Album engine

Base score = weighted, explainable components: technical quality, face quality of
important people, importance of people present, moment significance, learned preference,
explicit ratings. Greedy diversity-aware selection then adjusts for: near-duplicates
already chosen, visual similarity to chosen photos, soft moment allocations (default
10/20/20/20/30%; each slider shows the resulting photo count and how many photos that
moment has; "Reset to our defaults" restores them, keeping the album size), coverage of important people, and a bride/groom share target.
Locked (user-selected) photos are always kept; rejected photos are never chosen; a
shortfall is reported rather than padded. One negative signal never excludes a photo.

## 5. Preferences

Favorites, ratings ≥4, selections and comparison winners are positives; rejections,
ratings ≤2 and comparison losers are negatives. With ≥6 of each, a small logistic
regression on CLIP embeddings is fitted locally; with ≥3 favorites, similarity to the
favorites is used. No neural network is trained. "Reset learned preferences" stops using
earlier feedback (explicit choices are kept).

## 6. Export

Copies approved photos (recommendations not rejected + user selections, or selections
only) byte-for-byte into a new/empty folder outside the source, optionally into moment
subfolders, verifies each copy's SHA-256, and writes `album_manifest.json`/`.csv`.
Missing source files are listed, not silently skipped.
