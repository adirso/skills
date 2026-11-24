---
name: wedding-album-curator
description: Install, launch, configure, diagnose and update Wedding Album Curator — a local-first app that helps couples pick ~500 album photos from thousands of wedding photos (face grouping, quality checks, similar-shot comparison, explainable album selection, export). Use when the user asks to install/start/stop/update the wedding album app, check hardware compatibility, set up local AI (Ollama) or Claude providers, troubleshoot it, or explain how analysis, selection or export works.
---

# Wedding Album Curator

A local web app (FastAPI + React) that runs on `http://127.0.0.1:8765`. Photos stay on the
user's computer; originals are never modified. The user makes every final decision.

## Locate the installation

Run `scripts/locate.sh` (in this skill folder). It prints the app root, or exits non-zero if
the app is not installed. All commands below are relative to that root (`$ROOT`).

If it is not installed and this skill came from the plugin marketplace, the app is bundled
in this skill's `app/` folder: `scripts/bootstrap.sh` copies it to `~/wedding-album-curator`
(or `$WAC_HOME`) and runs the installer. Tell the user first that the installer downloads
Python packages (about 3 GB with PyTorch; `--core` is much smaller) and ask before running it.

## Workflows

| User wants to… | Do this |
|---|---|
| Install | Follow [reference/install.md](reference/install.md). From the plugin: `scripts/bootstrap.sh` (in this skill folder). From a repository checkout: `$ROOT/scripts/install.sh` (add `--with-skill` to link this skill). |
| Launch | Run `$ROOT/scripts/launch.sh` **in the background** (it is a long-running server), then tell the user to open http://127.0.0.1:8765. Stop with `$ROOT/scripts/stop.sh`. |
| Check hardware | `$ROOT/scripts/wac hardware` — summarize CPU/RAM/GPU and the recommended local models. |
| Download local models | Show sizes/licenses with `$ROOT/scripts/wac models`, **ask the user to approve**, then `$ROOT/scripts/wac models --download all --yes`. |
| Configure AI providers | See [reference/providers.md](reference/providers.md). Provider choice, consent and API keys are set in the app (AI & Privacy). |
| Diagnose problems | `$ROOT/scripts/wac doctor`, then [reference/troubleshooting.md](reference/troubleshooting.md). |
| Update | Plugin install: update the plugin, then run `scripts/bootstrap.sh` again. Repository checkout: `$ROOT/scripts/update.sh`. User data and models are preserved either way. |
| Explain how it works | [reference/workflows.md](reference/workflows.md) (analysis, people, compare, album engine, export). |
| Try it without real photos | `$ROOT/scripts/wac sample-dataset ~/WAC-sample`, then create a project on that folder. |
| Measure speed | `$ROOT/scripts/wac benchmark <folder>` (read-only; reports measured timings). |
| Run tests | `$ROOT/scripts/test.sh` |

## Rules

- Never download models, pull Ollama models, or enable a cloud provider without the user's explicit approval.
- Never send the user's photos anywhere yourself. Do not read or display the user's photos unless asked.
- Never copy, move, rename or delete files in the user's photo folder.
- Do not invent prices, usage balances or performance numbers; quote the app's estimates and measured results.
- The Anthropic API key is entered by the user in the app (or `ANTHROPIC_API_KEY`); never ask them to paste it into chat.
- The server binds to localhost only; do not add `--host 0.0.0.0`.
