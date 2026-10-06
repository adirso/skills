# First-Time Setup

Claude installs, the user only approves.

**What goes where** (tell the user this honestly, before starting):
- The skill's libraries and settings file: one folder in the user's home, `~/.motion-creator` (on Windows `C:/Users/<name>/.motion-creator`).
- The browser that captures the frames (Chromium, about 150MB): in Playwright's cache folder. On Mac `~/Library/Caches/ms-playwright`, on Windows `%LOCALAPPDATA%\ms-playwright`, on Linux `~/.cache/ms-playwright`.
- Python, if it is not installed: installed system-wide. On Mac through Apple's Command Line Tools or Homebrew, on Windows through winget.

To uninstall: delete `~/.motion-creator` and the ms-playwright folder. Leave Python (other programs may use it).

## How to talk to the user

One step at a time: one sentence explaining what is happening now and why, one command, then show that it worked. No terms like venv, PATH or pip. Say "a separate environment", "the tool", "the browser that captures the frames".

Example opening:
> "Before the first animation I need to install a few free tools, once: Python, a browser that captures the frames, and a tool that joins them into a video. The libraries go into one folder called .motion-creator, the browser into its own cache folder, and if you don't have Python it will be installed on your computer. It takes a few minutes. Shall I start?"

Detect the operating system from the environment, don't ask.

## Step 1: Python (3.9 or later)

**Mac:** first check quietly, without triggering any window:
```bash
xcode-select -p >/dev/null 2>&1 && echo tools-yes || echo tools-no
ls /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/*/bin/python3 2>/dev/null
```
- **If Apple's tools are missing and there is no other Python:** do not run `python3 --version` directly. On a Mac without Python, `python3` is an Apple stub that opens a window saying "The python3 command requires the command line developer tools". Tell the user in advance:
  > "An Apple window is about to open asking to install the developer tools. Click Install (not Get Xcode), accept the license, and wait until it says the installation finished. It takes 5 to 15 minutes."

  Then `xcode-select --install`. When the user says it's done, continue. If Homebrew is present, `brew install python` is an alternative without the window.
- **Otherwise:** `python3 --version` (or the path that was found). 3.9 or later: continue.

**Windows** (Claude Code runs in Git Bash):
```bash
py --version || python --version
```
- A `python` that opens the Microsoft Store or returns nothing is an empty shortcut, not Python. Use `py`.
- Not present:
```bash
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --disable-interactivity
```
  After installing, `py` is recognised only in a new terminal. If it isn't, the full path is usually `"$LOCALAPPDATA/Programs/Python/Python312/python.exe"`.

## Step 2: A separate environment in one folder

**Mac:**
```bash
python3 -m venv ~/.motion-creator/venv
PY=~/.motion-creator/venv/bin/python
```

**Windows:**
```bash
py -m venv "$HOME/.motion-creator/venv"
PY="$HOME/.motion-creator/venv/Scripts/python.exe"
```

## Step 3: The libraries

```bash
"$PY" -m pip install --upgrade pip
"$PY" -m pip install playwright numpy pillow imageio-ffmpeg
```
- `playwright` drives the capturing browser, `numpy` for sound, `pillow` for the review sheets, `imageio-ffmpeg` brings a ready-made ffmpeg.

## Step 4: The browser that captures the frames

```bash
"$PY" -m playwright install chromium
```
About a 150MB download, one to three minutes. If it looks stuck, wait.

## Step 5: ffmpeg

```bash
ffmpeg -version
```
- Installed: `render.py` will use it.
- Not installed: nothing to install. `imageio-ffmpeg` from step 3 already brought one, and `render.py` finds it on its own. Verify:
```bash
"$PY" -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
```

## Step 6: A real test, and only then the settings file

Proof first, then the record. Build a small test project in a temporary folder and render one frame from it:

```bash
T="$HOME/.motion-creator/selftest"; rm -rf "$T"; mkdir -p "$T"
S="<path to the skill folder>/assets"
cp "$S/engine/core.js" "$S/template/index.html" "$S/template/scene.js" "$S/render.py" "$S/audio.py" "$T/"
cp -r "$S/fonts" "$T/fonts"
cd "$T" && "$PY" render.py stills 1.0
```
Look at `stills/t-01.000.png` (Read tool): the word "שלום" should appear in white on a dark background, in a heavy font. Did it work? Delete `$T` and write **`~/.motion-creator/state.json`** (in the home folder, not the skill folder: the skill folder is reset on reinstall, and in Cowork it may be read-only):

```json
{
  "setup_done": true,
  "os": "mac",
  "python": "/Users/<user>/.motion-creator/venv/bin/python",
  "ffmpeg": "system",
  "checked": "2026-09-27"
}
```
- `python`: full path, after expanding `~` and `$HOME`. On Windows with forward slashes: `C:/Users/<user>/.motion-creator/venv/Scripts/python.exe`.
- `ffmpeg`: `"system"` or `"imageio-ffmpeg"`.
- `checked`: today's date.

And to the user:
> "Everything is installed and working. From now on we go straight to the animation."

Then go straight to the style selection step.

## Cowork

Cowork runs the work in a Linux virtual machine. Same steps, with `python3` and:
```bash
"$PY" -m playwright install --with-deps chromium
```
If installation is blocked (no permission or no network), tell the user in one line that rendering needs Claude Code on their own computer, and point them to README.txt.

## Common problems

| Problem | Fix |
|---|---|
| `externally-managed-environment` | Install only inside the environment (`"$PY" -m pip`), never with the system pip |
| `playwright install` fails on the network | Try again. On a corporate network: `HTTPS_PROXY` |
| On Windows `py` is not recognised after install | Full path (step 1), or close and reopen Claude Code. Meanwhile you can record `"setup_done": false, "step": 2` in `~/.motion-creator/state.json` to resume from the same place |
| `Executable doesn't exist` during render | The browser was not installed in this environment: step 4 again |
| The frame comes out empty or without Hebrew | The project's `fonts` folder is missing, or the page crashed: `render.py` prints `PAGEERROR` |
| `~/.motion-creator/state.json` says installed but `python` doesn't exist | `setup_done: false` and back to step 1 |
| An Apple window opens midway on Mac | That's the step 1 window: Install, wait, and continue |
