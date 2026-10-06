# Render Pipeline

## How it works

1. `index.html` loads the fonts, `core.js` and `scene.js`, and defines `window.CONFIG` (size, length, fps, loop, music).
2. `window.ready` waits for the fonts, builds every scene once, and then `seek(t)` computes the frame.
3. `render.py` splits the frames across several browsers in parallel. Each one opens the page in Chromium via Playwright, calls `seek(t)` for every sub-frame, captures, and streams the images straight into ffmpeg. No images on disk and no huge intermediate files.
4. ffmpeg averages the sub-frames (`tmix`), keeps one frame from each group (`select`) and fixes the timestamps (`setpts`), so the output is 60fps and not 240. Each browser encodes its chunk to H.264 (crf 16), the chunks are joined without re-encoding (stream copy), and the sound from `audio.py` goes in at the same stage.

All settings live in `CONFIG` inside `index.html`. `render.py` and `audio.py` read them from there, so there is nothing to update anywhere else.

## Project structure

```
motion-<name>/
  index.html      CONFIG + file loading (from the template)
  core.js         the engine (from the skill, don't edit)
  scene.js        the animation itself (you write it)
  logo.js         style 10 only: the logo file wrapped as a string (window.LOGO)
  render.py       render and review (from the skill)
  audio.py        sound (from the skill)
  fonts/          the fonts (from the skill)
  music.mp3       only if the user provided a song
  stills/         review images (created automatically)
  out/            preview.mp4, final.mp4, final.gif, audio.wav, cues.json
```

A long animation with several scenes: you can split it into `scene-1.js`, `scene-2.js` and add a `<script>` for each in `index.html`. Wrap each file in `(() => { ... })();` so names don't collide.

## The commands

| Command | Output | When |
|---|---|---|
| `render.py check` | A list of problems: page errors, text cut by the frame, text pixels outside the safe area (including on each word's first and last frame), words touching or nearly touching, a hyphen between words, a label that doesn't stay long enough to read, a frozen picture (except the last `CONFIG.hold` seconds) | After every change |
| `render.py strip 0 4 10` | `stills/strip-*.jpg`: a sheet with a frame every tenth of a second | To see the flow |
| `render.py stills 0.5 1.2 2.0` | `stills/t-*.png` at full size + `stills/sheet.jpg` | To check readability and details |
| `render.py preview` | `out/preview.mp4`: half size, 30fps, no motion blur, with sound | A draft for the user |
| `render.py full` | `out/final.mp4`: CONFIG size (or `SCALE`), CONFIG fps, motion blur | Final render |
| `render.py flashcheck` | Mean brightness of every frame: any jump over 2 percent is a flash, and more than three per second fails | Any style with flashes (neon, colour cuts) |
| `render.py gif` | `out/final.gif` (or `preview.gif` if there is no final): a 4 second segment, 360 px (400 for square), 12fps, 64 colours | For websites and sharing |

`$PY` here is the path saved in `~/.motion-creator/state.json`, e.g. `"$PY" render.py check`.

Environment variables:
- `SUB`: sub-frames per frame in full. 4 by default, 8 for particles and neon glow (styles 03 and 08).
- `SCALE=0.5`: render full at half size, still with motion blur and 60fps. For a quality draft or when the computer is slow. (preview is always half size, 30fps and with no sub-frames.)
- `WORKERS=N`: how many browsers in parallel (default: number of cores minus 1, up to 6). On a machine with little memory: `WORKERS=2`.
- `T0=2 T1=4`: render only a segment.
- `NOAUDIO=1`: silent video.

## Timings

- `strip`: seconds to half a minute. `check`: up to a minute or two, because it captures several images per sample to isolate each word's pixels.
- `preview` of 10 seconds: under a minute.
- `full` of 10 seconds at `SUB=4`: a few minutes, and at `SUB=8` about twice that. Run with a long timeout (up to 10 minutes) or in the background, and check the file at the end.

## Motion blur

Every frame is the average of `SUB` captures within half the frame duration (a 180-degree shutter), centred on the frame time. Fast motion smears, slow motion stays sharp. So never fake blur on fast motion in code.

The exception: a very fast slide (hundreds of pixels per frame). There the average alone shows several separate copies of the same element. `tf(el, {x: X(t), mb: [vel(X, t), 0]})` adds directional blur based on the velocity. `render.py` tells the page how many sub-frames it captures (`window.RENDER`), and core.js adjusts the amount: in the preview it replaces all the motion blur, in the full render it only fills the gaps.

`check` doesn't see text drawn inside canvas or WebGL (particles, neon, three.js). There the check is by eye, on the stills.

## Measurements from the scene: report()

When the scene needs to state a number (when growth ends, the highest point of a field, the width of a corridor), call `report('name', value)` (at build time or inside seek). The value is stored in `window.REPORT`, and `check`, `stills` and `flashcheck` print it as a `report name: value` line. Don't use `console.log` (not printed) or `console.warn` (`check` counts it as a problem).

## GIF for websites

`render.py gif` cuts a segment from the MP4 (final if there is one, otherwise preview). The defaults target a web page: 4 seconds from the start, 360 px wide (400 for square), 12fps, 64 colours, and a target of up to 1.2MB. Options: `start=2.5 len=3.5 width=360 fps=12 colors=64 soft`.

If the file comes out larger than 1.2MB, in this order:
1. A shorter segment (`len=3`);
2. `colors=48 soft` (48 colours and a light blur before the palette);
3. A clean GIF version: a copy of the project without grain and without camera motion, because noise and constant motion are what bloat a GIF.

## Loop

With `CONFIG.loop = true`, time wraps at DUR, the last rendered frame is DUR minus one frame, and sound tails that run past the end wrap back to the start. The video loops without a jump.

## three.js (for 3D styles that need it)

Download it once into the project folder and add it before `scene.js`:
```bash
curl -L -o three.min.js https://cdn.jsdelivr.net/npm/three@0.158.0/build/three.min.js
```
```html
<script src="three.min.js"></script>
```
- `new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true })`, and at the end of every seek an explicit call to `renderer.render(scene3, camera)`. Without it the capture comes out empty.
- No `requestAnimationFrame` and no `renderer.setAnimationLoop`. Every frame is rendered only from seek.
- `renderer.setPixelRatio(1)` and size W x H.
- WebGL in headless Chromium runs in software, so a high triangle count slows it down. Up to a few tens of thousands is fine.

## Troubleshooting

| Problem | Cause and fix |
|---|---|
| `PAGEERROR` or `console:` in the output | An error in scene.js. Fix it before anything else |
| `scene main build failed` | An exception at build time. The line appears in the output |
| Empty frame | `seek` throws, or three.js without `preserveDrawingBuffer` |
| Text in the wrong font | A weight or font that didn't load. `F.MONO` and `F.LAT` have no Hebrew |
| The render crashes midway | Out of memory: `WORKERS=2`. `ffmpeg failed on chunk`: usually out of disk space |
| `ffmpeg not found` | setup.md step 5 |
| No sound | `out/cues.json` is empty: no `sfx()` calls at build time, or `NOAUDIO` is set |
