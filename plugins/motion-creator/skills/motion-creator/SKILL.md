---
name: motion-creator
description: >
  Motion Creator: an animation studio that builds studio-grade motion graphics from scratch, in code, with Hebrew
  right-to-left text on screen, and exports MP4 (and GIF on request). It always asks for the style first: 10 ready
  styles (a UI that morphs, huge headlines on bold colour, a word that breaks into particles, a 3D world of cubes,
  rings of text, a hand-drawn character, a children's book illustration explaining a process, glowing neon branches,
  a sketch that turns 3D, an animated logo from the logo file) or a custom style. Then it asks the style's questions,
  shows a scene list for approval, builds, reviews itself on stills, and renders with motion blur.
  Trigger on: "make an animation", "create an animation", "animate this text", "animation in code", "motion graphics",
  "motion studio", "reels animation", "kinetic typography", "animated intro", "animated logo",
  "logo reveal", "תיצור לי אנימציה", "תעשה לי אנימציה", "אנימציה בקוד", "סטודיו אנימציה", "מושן גרפיקס",
  "אנימציה לרילס", "אנימציית טקסט", "פתיח מונפש", "לוגו מונפש".
  Builds code-rendered motion graphics (HTML + Playwright + ffmpeg), Hebrew RTL on screen, and always asks for the style first.
  Not for editing real footage, adding captions to an existing video, or HyperFrames compositions.
display_name: "Motion Creator"
category: design
version: "1.0.0"
tags: [motion, animation, video, reels]
platform: [claude-code, cowork]
status: active
dependencies: []
---

# Motion Creator

The skill builds an animation where every frame is computed from time inside an HTML page. A headless browser captures it frame by frame, and ffmpeg joins the images into a video with real motion blur. The result: a motion-studio-grade MP4, with correct Hebrew on screen.

**How to talk to the user:** plain, short language, in the user's language. No terms like seek, spring or tmix unless the user used them. One question (or one round of questions) at a time, with a default for every question, so the user can answer "default".

**The skill folder** (`<SKILL>` below) is the folder this file is in.

## 0. Model check

The skill needs Claude Opus 5.5 or later. A weaker model produces stiff motion that breaks. If your model (shown in the conversation context) is weaker, say in one line:
> "This skill only works well with Claude Opus 5.5 or later. Switch models (in Claude Code: the /model command, in Cowork: the model picker) and ask again."

If the user asks to continue anyway, continue.

## 1. First-time setup

Setup state is stored in **`~/.motion-creator/state.json`** (in the user's home folder, so it survives reinstalling the skill). `<SKILL>/state.json` is only an empty default, and is never written to.
- `~/.motion-creator/state.json` exists with `"setup_done": true`: verify the path in `python` still exists (`"<python>" --version`) and go on to step 2. From now on `PY` is that path.
- Missing, or `false`: follow `references/setup.md`. Claude installs, the user only approves. One step at a time, Mac or Windows according to the environment. At the end, only after a real test, write `~/.motion-creator/state.json`.

## 2. Choosing a style

If the user already described what they want, match a style and confirm it in one sentence. Otherwise show the menu as is:

> Which style?
> 1. A UI that morphs, to demo an app or product
> 2. Huge headlines on a bold colour background, for openers and strong messages
> 3. A word that breaks into particles, to present a brand or name
> 4. A 3D world of cubes, for an energetic background with a headline
> 5. Rings of text, for lists and principles
> 6. A hand-drawn character, for light-hearted messages
> 7. A children's book illustration explaining a process, for educational content
> 8. Glowing neon branches, for dramatic moments
> 9. A sketch that turns into 3D, to explain how something works
> 10. An animated logo from your logo file, for a video opener or closer
> 11. Your own style: describe it in words, or send an image or link as an example

| Choice | File |
|---|---|
| 1 | `references/styles/01-ui-morph.md` |
| 2 | `references/styles/02-bold-type.md` |
| 3 | `references/styles/03-particles.md` |
| 4 | `references/styles/04-cubes-3d.md` |
| 5 | `references/styles/05-type-rings.md` |
| 6 | `references/styles/06-doodle.md` |
| 7 | `references/styles/07-flat-explainer.md` |
| 8 | `references/styles/08-neon-organic.md` |
| 9 | `references/styles/09-sketch-to-3d.md` |
| 10 | `references/styles/10-logo-reveal.md` |

## 3. Style questions

1. Read the style file, plus `references/principles.md` and `references/hebrew-rtl.md` (once per conversation).
2. Ask all the style's "Input" questions in one message, each with its default.
3. Add a question about sound: no sound, effects only (default), or effects plus your own song. A song only from a file the user brings and is allowed to use; the recommendation is Mixkit, free even for commercial use (`references/sound.md`).
4. Whatever the user left open gets the default. Don't ask again.

**Style 11 (custom):** ask what the text or message is, what happens on screen, colours, length and size, and ask for an example if there is one. Pick the closest style file as a technical base, and write a short brief in the same structure (direction, structure, build, pitfalls). The brief is shown together with the approval list.

## 4. Approval list, before any line of code

Show what is written under "Approval list" in the style file: a table of states on the beat grid, or of scenes with times, with the exact text that will appear on screen, the colours and the sound. Under the table: size, length, and whether it loops.

Everything shown to the user is written in plain language that describes what is seen on screen. Internal terms from the style files (mask, plate, pulse, colour field, anticipation) are not passed on to the user literally: "the headline on a soft dark patch", not "the headline on a plate". A professional term with no plain equivalent stays as is, with half a sentence explaining it.

**Wait for explicit approval.** Don't write code, create a folder or render before a "yes" or "approved". Fix the list according to feedback and show it again.

## 5. Build

1. **A new project folder** in the user's working directory (in Cowork: the chosen folder): `motion-<short English name>/`, e.g. `motion-reels-intro/`. If one already exists, add a number.
2. **Copy from the skill:**
   - `<SKILL>/assets/engine/core.js` → `core.js`
   - `<SKILL>/assets/template/index.html` → `index.html`
   - `<SKILL>/assets/template/scene.js` → `scene.js`
   - `<SKILL>/assets/render.py` → `render.py`
   - `<SKILL>/assets/audio.py` → `audio.py`
   - the folder `<SKILL>/assets/fonts/` → `fonts/`
3. **CONFIG** in `index.html`: size, length, fps, background, loop, and a song if there is one (the file is copied into the project folder; `audio.py beat` measures the tempo, `references/sound.md`).
4. **Read the header of `core.js`**: the whole API is there (springs, text, camera, scenes, sound).
5. **Write `scene.js`** according to the style file. Rules that must not be broken:
   - Every style is computed from `t` inside the function that `scene()` returns. No timers, no CSS transitions, no `Math.random` during seek, no state kept between frames.
   - Motion on springs (`S`, `track`, `slam`, `rise`), not linear easing on a visible element.
   - Hebrew according to `references/hebrew-rtl.md`: RTL, words enter whole (no masks), no hyphen between words, a font with Hebrew.
   - Text in the safe area, at a size readable on a phone.
   - `sfx(t, kind)` on the peak moments, at build time.
6. **Logos, images and faces:** only what the user provided. Never use someone else's logo or trademark.

## 6. Self-review round

All commands run from the project folder with `"$PY"`. Details in `references/render-pipeline.md`.

1. `"$PY" render.py check`: fix **every** line it prints (page errors, text clipped or outside the safe area, words touching, a hyphen between words, a label too short to read, a frozen picture). Run again until "check passed". The check can't see text drawn in canvas: check that by eye in item 3.
2. `"$PY" render.py strip 0 <DUR> 10`: look at every sheet (Read tool). Check flow, pace, that there's no dead moment, that words enter in reading order, and that nothing is left over from a previous state.
3. `"$PY" render.py stills <times>`: one frame per beat or per stage (the recommended times are in the style file), and look at every image at full size. Check:
   - every word is readable, spelled exactly, right to left, with punctuation on the correct side;
   - no hyphen joining two words and no em dash;
   - no word clipped, overlapping or touching its neighbour;
   - the colours come from the approved palette, and nothing from the style's "forbidden" list;
   - minimum size and palette colours (check doesn't test these);
   - the test in `references/principles.md` section 10.
4. Fix, and run again from item 1. **At least two rounds.** If the review reveals that part of the approved plan itself doesn't work (e.g. an ending that comes out too small in the frame), fix it with the smallest change that solves it, and tell the user in one line what changed and why when you show them the draft. A big change (a different scene, different text) goes back for approval. Continue until everything passes and the result looks like the work of a leading studio, not a template. In a conversation where a subagent is available, you can give it the images and the checklist and ask for an independent review.
5. `"$PY" render.py preview`: a half-size draft with sound (`out/preview.mp4`). Give the user the full path and ask if they have feedback before the final render. Feedback: back to item 1.

## 7. Final render

1. `"$PY" render.py full` (default `SUB=4`), and `SUB=8 "$PY" render.py full` for particles and neon glow (styles 03 and 08). Produces `out/final.mp4` at the CONFIG size, 60fps, with motion blur and sound. `SCALE=0.5` renders it at half size (e.g. when the user wants a small file, or when the computer is slow). It takes a few minutes: run with a long timeout (up to 10 minutes) or in the background.
   In a style with flashes (neon, colour cuts): `"$PY" render.py flashcheck` before the final render, and fix if it fails.
2. GIF (if the user wants one, e.g. for a website): `"$PY" render.py gif` → `out/final.gif` (if there is no final yet, from the draft: `out/preview.gif`). The default targets a web page: 4 seconds, 360 px for vertical and 400 for square, 12fps, 64 colours, target up to 1.2MB. Another segment: `start=2 len=3.5`. Too big: the command prints what to try (render-pipeline.md).
3. Verify the files exist and have a sensible size (`ls -la out/`), and report briefly: the full path to the MP4 (and the GIF), the length and the size. Last line: "Want to change anything? Tell me what and I'll update and render again."

## Iron rules

1. No code before the user approves the scene list.
2. Never say "ready" without looking at the stills and without the file existing on disk.
3. No hyphen between two words, and no em dash, in any on-screen text.
4. No sound files in the skill, and no song the user didn't bring.
5. `core.js`, `render.py` and `audio.py` in the project are copies. Fix a bug in them only if it is really there, and tell the user what was fixed.

## The files

| File | What's in it |
|---|---|
| `references/principles.md` | The standard: springs, function of time, motion blur, restraint vs showreel, camera, loop, safe areas, the quality test |
| `references/hebrew-rtl.md` | Fonts with Hebrew, direction, word entrances without masks, hyphens, canvas and SVG |
| `references/setup.md` | First-time setup, Mac, Windows and Cowork |
| `references/render-pipeline.md` | Project structure, all render commands, timings, three.js, troubleshooting |
| `references/sound.md` | Effect types, the user's song, tempo measurement |
| `references/styles/*.md` | The 10 styles: input, direction, structure, build, pitfalls, approval list |
| `assets/engine/core.js` | The engine, with the API in its header |
| `assets/template/` | `index.html` (CONFIG) and an example `scene.js` |
| `assets/render.py`, `assets/audio.py` | Rendering, review and sound |
| `assets/fonts/` | Google Fonts under the OFL license (`OFL.txt`) |
| `assets/examples/08-neon-organic.js` | A complete, tested scene for style 8, a starting point |
| `state.json` | An empty default. The real state is stored in `~/.motion-creator/state.json` |
