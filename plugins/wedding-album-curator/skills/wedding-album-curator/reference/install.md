# Installing Wedding Album Curator

## Requirements

- macOS (Apple Silicon or Intel), Linux, or Windows via WSL2 (native Windows is untested).
- Python 3.11 or 3.12 — or [uv](https://docs.astral.sh/uv/), which fetches Python 3.12 automatically.
- Node.js 20+ (only needed to build the frontend).
- ~3 GB disk for Python packages (PyTorch), ~650 MB for local models, plus thumbnail cache
  (roughly 0.5 MB per photo → ~4 GB for 8,000 photos).

## Steps

1. **Installed the skill from the `adirso-skills` plugin marketplace?** The app is bundled
   with it. Run `scripts/bootstrap.sh` from this skill folder: it copies the app to
   `~/wedding-album-curator` (or `$WAC_HOME`) and runs the installer (accepts `--core`).
   Done; skip to step 3.

   Otherwise, get the app folder (clone or copy the repository). Set `WAC_HOME` if it is
   not in a standard place.
2. Run:

   ```bash
   "$ROOT/scripts/install.sh" --with-skill
   ```

   - `--core` skips PyTorch/OpenCLIP/MediaPipe (smaller install). Without them there is no
     visual-similarity search, no moment classification, no closed-eye detection and no
     preference learning. Faces and quality checks still work.
   - `--with-skill` links this skill into `~/.claude/skills/`.

3. Local models are **not** downloaded by the installer. Either approve them in the app
   (onboarding → "This computer"), or after asking the user:

   ```bash
   "$ROOT/scripts/wac" models               # list: name, size, license
   "$ROOT/scripts/wac" models --download all --yes
   ```

   | Model | Size | License | Used for |
   |---|---|---|---|
   | YuNet face detector | 0.2 MB | MIT | finding faces |
   | SFace | 39 MB | Apache-2.0 | grouping recurring people |
   | MediaPipe Face Landmarker | 3.8 MB | Apache-2.0 | closed-eye detection |
   | OpenCLIP ViT-B/32 (LAION-2B) | 605 MB | MIT | similarity, moments, preferences |

   Every file is verified against a pinned SHA-256.

4. Verify: `"$ROOT/scripts/wac" doctor`.

## Where data lives

- App data (projects, caches, models): macOS `~/Library/Application Support/WeddingAlbumCurator`,
  Linux `~/.local/share/WeddingAlbumCurator`. Override with `WAC_DATA_DIR`.
- Original photos are read in place and never written.
