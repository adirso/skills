# Motion Principles

This file is the standard. Every style builds on it, and every animation is checked against it before it is shown.

## 1. Everything is a pure function of time

- `seek(t)` computes every style, every point and every pixel from `t` alone.
- Forbidden: CSS transitions, CSS animations, `requestAnimationFrame`, `setTimeout`, `Date`, `Math.random` during seek, and any variable carried from frame to frame.
- Randomness: `rng(seed)` at build time (once, inside `scene`), or `hash(i)` during seek. That way every render comes out identical, and any frame can be rendered on its own and in parallel.
- `render.py check` verifies this: it captures some frames twice, after jumping to other times, and makes sure they match.

## 2. Springs, not easing

- `S(tau, wn, z)` is the closed-form step response of a spring. It starts at 0 and settles at 1.
- `wn` (stiffness): 8 to 12 for large, soft moves (camera), 13 to 20 for UI, 24 to 40 for slams and sharp entrances.
- `z` (damping): 1 for no overshoot, 0.8 to 0.9 for a tiny overshoot (the UI default), 0.55 to 0.65 for a slam with a short wobble (typography).
- A value that changes target several times: `track(v0, [[t, value], ...])`. It is a sum of one spring per change, so it stays a function of time. Values can be arrays (`[w, h, radius]`) that move together.
- Linear is allowed only for constant motion that has no start and end inside the frame (a slow camera orbit, a continuous scroll). Every entrance, exit and state change is a spring.
- Edges on different springs: on an indicator, a slider, or a toggle knob, the leading edge is on a fast spring and the trailing edge on a slow one. That creates a liquid stretch without faking it.
- Direct manipulation: while dragging, the value is computed from the cursor position, not from a spring. On release it springs back from wherever it is.

## 3. Real motion blur

- The final render captures 4 to 8 sub-frames per frame (a 180-degree shutter) and blends them with ffmpeg `tmix`. Fast motion smears on its own, exactly like a camera.
- So never fake blur on fast motion. `tf(el, {blur})` is reserved for swapping content inside a container (6 to 10 px of blur for a few frames) and for depth of field.
- **How many sub-frames:** `SUB=4` is the default for all styles. `SUB=8` only for particles and neon glow (styles 03 and 08), where small points move fast. A fast slide of a whole word gets directional blur (below), not a higher SUB.
- **Very fast motion** (a slide of hundreds of pixels per frame): averaging sub-frames alone produces separate ghost copies. Add directional blur derived from the velocity: `tf(el, {x: X(t), mb: [vel(X, t), 0]})`. `vel` computes the velocity from the closed-form function, and core.js scales the blur to the render's shutter. The velocity is in the element's own pixels: if the camera is zoomed, divide by its zoom.

## 4. Two modes: restraint or showreel

**Restraint** (UI morph, children's book illustration, sketch):
- One background, one accent colour or black and white, one font.
- One object that changes shape instead of cuts. Content swaps inside it with a short blur, and every piece of text has its own entrance and exit.
- Forbidden: glow, gradients on UI components, particles, icons with mismatched stroke widths, anything that looks like a template.

**Showreel** (bold type, particles, cubes, rings, neon):
- Hard cuts on the grid to full colour backgrounds, typography that fills the frame.
- The camera never stops: push, drift, a degree or two of rotation, a short shake (`shake`) on every hit.
- No frame frozen for more than a third of a second.
- At most three full-screen flashes per second, and never a full-screen red flicker. `render.py flashcheck` measures this: a jump of more than 2 percent in mean brightness between two frames is a flash.

## 5. Camera

- The camera is a group (`grp`) that contains the whole scene. `tf(cam, {x, y, s, r})` moves everything together.
- Zoom so that every state fills the frame. A small state in the middle of an empty screen looks like a mistake.
- Never `will-change` or `translateZ` on anything the camera scales, otherwise the browser captures it as a bitmap and the text comes out blurry.
- Camera movement is a `track` with low `wn` (6 to 10) and `z` close to 1.

## 6. Timing and grid

- Every animation sits on a grid: the beats of a song (default 120 BPM, i.e. a beat every half second), or a fixed half-second grid.
- `beat(n)` gives the time of beat n from `CONFIG.bpm` and `CONFIG.beat0`.
- Something happens on every beat. No dead time.
- Fast entrances: 0.1 to 0.25 seconds. Several elements entering together get a 30 to 60 ms offset between them (stagger), in reading order.
- Exits are faster than entrances.
- **Minimum reading time:** a label or sentence (more than one word) stays on screen at least 1.3 seconds. The headline or message at the end is held at least 1.5 seconds before the last frame. (Exception: in the particle word the word builds in front of the eye during assembly, and the sharp hold at the end is half a second.) Single words on a grid rhythm can be shorter, as long as the full message returns at the end. `render.py check` flags both cases.

## 7. Perfect loop

- `CONFIG.loop = true`: time wraps at DUR, and `track` and `vis` close the loop on their own.
- Every `track` must return to its starting value (the console warns if not).
- The last frame equals the first, including cursor position and velocity. Check: `stills 0 <DUR-0.02>` should look almost identical.
- Music in a loop is cut to whole bars (audio.py crossfades the tail into the head).

## 8. Safe areas

**Reels and Stories (1080x1920):** text stays inside:
- 250 px from the top;
- 350 from the bottom;
- 80 from each side;
- 140 from the right in the lower half (Instagram's buttons).

Backgrounds and graphics may go to the edge. `render.py check` tests the pixels of every word against the area, including on its first and last frame.

**Room to move:** a word that fills the width fills about 840 of the 920 px of the safe area, so there is room for a camera push and a shake. And a slam that starts large must stay inside the frame: `from = Math.min(1.25, (W - 40) / (wordWidth * 1.04))` (the 1.04 is the camera push). A label the camera moves under is checked on its first and last frame, because camera motion can push it out.

**Square and widescreen:** 6% margin on every side for text.

## 9. Typography and colour

- Minimum size for text that must be read on a phone: 90 px in a 1080-wide video. Hero words 220 to 520. Exempt: small technical labels that are decoration (mono, "W 612 H 188") and UI text inside a UI demo, which reads as part of the interface and not as a message.
- `fit(s, o, width)` computes a size that fills a given width. Use it for every hero word.
- Colour pairs that work (from palette `C`): on `INK` white with a red accent; on `RED` ink; on `BLUE` white with a yellow accent; on `YELLOW` ink with a red accent; on `PAPER` ink with a red accent.
- Every colour on screen, including text, cursor and labels, comes from the approved palette. If the user's palette has no white, `C.WHITE` takes its light colour (`CONFIG.palette`).
- Contrast: text over a busy background gets a soft dark patch behind it, or the background dims while the text is on screen.

## 10. Studio quality: the test

Before showing anything, every answer must be yes:
1. There is one clear idea at every moment, and the eye knows where to look.
2. Every move starts and ends on a spring, with a little anticipation before a big move.
3. Nothing is frozen for more than a third of a second, and nothing shakes without a reason. Exception: the end hold on a logo or message (`CONFIG.hold`).
4. Every word is readable at phone size, in the right order, without clipping or overlap.
5. The colours come from the approved palette, with no shades added along the way.
6. Nothing from the style's forbidden list.
7. It looks like studio work, not a template or a slideshow.

## 11. Performance

- Up to 1500 DOM elements per scene. Beyond that, switch to canvas (`canvas2d`) and redraw everything on every seek.
- Images and heavy geometry are computed once at build time. Seek only positions.
- **Grain and noise** (paper, film grain): one static layer above everything, which neither moves nor scales. Exception: in the logo reveal the grain sits under the logo, so its colours stay exact. Never an SVG filter inside a group the camera scales: it is very slow, and the grain swells into blobs.
