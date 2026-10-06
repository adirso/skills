# 01 UI Morph

**When:** a demo of an app, product or feature. A clean, Dribbble-level loop. Restraint mode (principles.md section 4).

## Input

Ask in one message, with defaults:
- 8 to 14 UI states the shape will morph into. Default: a "שליחה" (Send) button, loader, checkmark, dynamic island, player, volume slider, toggle, tabs, chart, search window, toast notification.
- Black and white, or one accent colour.
- A royalty-free song around 120 BPM (e.g. from Mixkit, free for commercial use), or no song and only UI sounds on a 120 grid.
- Size: 1440x1440 (default), 1080x1920 for stories, 1080x1080.

## Direction

- One shape that is never cut. Every state is the same element changing size, corner radius and colour, and the content inside it swaps with a short blur.
- The cursor performs every user action, with real clicks and drags. System responses (loader, checkmark, notification) happen on their own, without the cursor. While typing the cursor disappears.
- A light warm grey background (`#E8E5E0`), components in black (`#0B0B0B`) and white, one font: Rubik (`F.RUBIK`).
- All UI text in Hebrew, right to left.
- Springs everywhere, with at most a small overshoot (`z` 0.82 to 0.9).
- The camera zooms so every state fills the frame.
- The last frame equals the first, so the video loops.
- **Forbidden:** bouncy easing, particle explosions, glow, gradients on UI components, icons with mismatched stroke widths, dead time, a hyphen between two words, a template look.

## Structure

7 bars, something happens on every beat. The tempo is what was measured in the song (`audio.py beat`), and the video length is derived from it: 7 bars of 4 beats. At 120 BPM that's 14 seconds.

"שליחה" button → loader → checkmark → dynamic island → player where play turns into pause → drag the progress bar → it becomes a volume slider that stretches when dragged past the maximum → a toggle flips on the beat → the toggle knob becomes a liquid tab indicator → the tabs open into a self-drawing chart, with a hover tooltip → everything shrinks into a ⌘K search window → typing in Hebrew to filter → enter → a toast pops up → back to the button.

States the user didn't ask for are removed, and the transitions between them are rebuilt so each state is born from the previous one.

## Build

- `CONFIG`: `W: 1440, H: 1440, loop: true, bpm: <measured>, beat0: 0, bg: '#E8E5E0'`, and `DUR = 28 * 60 / bpm`. With a song: `music: {file, start: <downbeat>}` (sound.md).
- **The shape:** one `div` with `overflow:hidden`. `const shape = track([w, h, radius, dy], [[beat(n), [...]], ...])` holds all the states. Colour: `track(0, ...)` between 0 (black) and 1 (white), and mix the RGB yourself.
- **Shadow:** not a large soft `box-shadow` (in Chrome it comes out with seams). Instead, a copy of the shape behind it, in a transparent dark colour, with `blur` of 30 to 40 and offset slightly down. The same `track` moves both.
- **Content:** a group (`grp`) for each state inside the shape, with its own `vis(t, a, b)` window. Entrance: `blur` from 8 to 0 plus opacity, about 0.15 seconds. Exit is faster. New content enters only once the shape is already close to its size.
- **Camera:** `world` = a `grp` containing the whole scene, `track([zoom, x, y], ...)` with `wn` 8 and `z` 0.96. The zoom is chosen so the state takes about 60 to 70 percent of the frame width. When the shape grows the camera pulls out **before** it (the camera keyframe is slightly earlier), and when the shape shrinks the camera moves in **after** it. Otherwise the shape gets clipped at the frame edge.
- **Balanced positions:** each state's centre is close to the world centre, so the last state returns to the first without a big camera move.
- **Cursor:** `cursor()` in a layer above the world. Position is `track([x, y], ...)` in world coordinates, passed through the camera every frame. Press: `track(1, ...)` that drops to 0.86 and returns (`wn` 38, `z` 1). Every click on a beat, with `sfx(beat(n), 'click')`. While typing: the cursor's `o` drops to 0, and returns after enter.
- **Edges on different springs:** for the tab indicator and the toggle knob, two separate `track`s for the left and right edge: the leading one `wn` 24, the trailing one `wn` 11.
- **Dragging:** while the cursor is pressed, the value is computed from the cursor position (`clamp((cur(t)[0] - x0) / width, 0, 1)`). On release, a spring from the value where it stopped. Stretch past the maximum: `230 * (1 - 1 / (1 + over / 380))` (rubber band).
- **Chart:** a self-drawing line (`stroke-dasharray` + `stroke-dashoffset` from a track). The time axis runs right to left: the first day on the right. The player's media buttons (back, play, forward) stay in their usual order.
- **Typing:** `typed(t, t0, n, cps)`, one character every eighth of a beat, `sfx(..., 'key', 0.5)` per character. The field's blinking caret is to the left of the text.
- **Sounds:** every UI sound (click, soft typing) is synthesised in `audio.py`, and `audio.py` shifts it to the nearest peak in the song. On a beat with no peak, a silent visual change without a sound.
- **Icons:** `icon(parent, P.play, ...)` with the same `stroke` for all (2 on a 24 grid).
- **stills:** one per beat, after the motion has settled: `beat(n + 0.7)`.

## Pitfalls

- Never `will-change` on anything the camera scales, otherwise the text gets blurry.
- Text that swaps inside a shape-changing container needs its own entrance and exit timing, otherwise it gets run over or sticks out of the shape.
- In Hebrew everything is right to left, except progress bars and media, which fill left to right (wrapped in `dir="ltr"`).
- The last frame equals the first, including cursor position and velocity: the cursor's last keyframe at least a second before the end, so it settles.
- Every `track` returns to its starting value (in a loop the console warns).
- Fonts load from local files and core.js waits for them before the first frame. A font not in `fonts/` is silently replaced by another font.
- An album cover or profile picture: only an image the user gave. Otherwise a clean colour square.

## Approval list

Table: beat | time | the state | what the cursor does (or "the system") | sound. After it, a line on the measured tempo, the length derived from it, the colour and the song.
