# Troubleshooting

Start with `"$ROOT/scripts/wac" doctor` and read which checks fail.

| Symptom | Cause / fix |
|---|---|
| `Not installed yet` | Run `scripts/install.sh`. |
| `Port 8765 is in use` | The app is probably already running: open http://127.0.0.1:8765. Otherwise `WAC_PORT=8770 scripts/launch.sh`. |
| Page says "frontend has not been built" | `cd frontend && npm ci && npm run build`. |
| "Missing session. Reload the app." | Reload the page (the session cookie is per server start). |
| People page empty | Face models were not installed when the photos were analyzed. Approve them, then click "Find people now" (banner on Overview / People) or People → "Re-scan faces". |
| Bride or groom missing / a group mixes several people | Re-group faces (People → "Re-group faces"); grouping never puts two faces from one photo in the same person. If still mixed, open the group and "Split into new person", or People → "Re-scan faces" (names, roles and corrections are kept). |
| Album settings changed and you want the recommended ones back | Album Builder → "Reset to our defaults" (keeps the album size), then Generate. |
| No moments / no similar-shot detection by visual content | CLIP model or the `ml` extra is missing (`doctor` shows it). pHash-based burst detection still works. |
| Closed eyes never flagged | MediaPipe model missing, or faces are small (eye state is only marked reliable for faces ≥ 90 px wide in the analysis image, facing the camera). |
| HEIC files show as errors | `pillow-heif` failed to install; reinstall, check `doctor` → "HEIC/HEIF support". |
| Photo folder "not available" | External drive disconnected or folder moved. Reconnect; projects remember the original path. |
| Analysis stopped / app was closed | Click "Analyze new photos"; work resumes where it stopped (per-photo progress is saved). |
| Ollama model fails with "unknown model architecture" | That model is not supported by the installed Ollama version; pick another model or update it with `ollama pull`. |
| Claude Code provider errors | Run "Test with a synthetic image". Check `claude --version`; flags may differ in very old/new versions. |
| Anthropic API: key rejected / rate limited | Re-enter the key; rate limits are retried automatically, repeated failures stop the run. |
| Spending limit reached | The run stops before exceeding it. Raise the limit in AI & Privacy to continue. |
| Slow analysis | Run `scripts/wac benchmark <folder>` to measure. CPU-only machines are much slower for embeddings. |

Logs: the server prints errors to the terminal running `launch.sh`. Job errors are also
shown in the app's job banner / Overview.

Resetting: AI & Privacy → "Delete local data" offers per-type deletion (faces, AI results,
embeddings, thumbnails) or deleting the whole project. Originals are never affected.
