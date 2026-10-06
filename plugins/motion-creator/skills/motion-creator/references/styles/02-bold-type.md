# 02 Bold Type

**When:** an opener, a strong message, an announcement. A motion studio showreel. Showreel mode (principles.md section 4).

## Input

Ask in one message, with defaults:
- The message: 3 to 6 words, or a short sentence.
- Length: 8 to 15 seconds (default 8). If the user asks for a shorter opener (4 to 6 seconds), the same structure compressed.
- Size: 1080x1920 for Reels (default), or 1080x1080.
- A palette of 3 to 4 strong colours. Default: red `#E54136`, electric blue `#2E3BFF`, yellow `#F7C22F` and cream `#EFEAE2`, on black `#0E0E10`.

## Direction

- Huge typography that fills the frame, and the background switches with a hard cut between full colours, on the beat. One or two words per frame.
- Every word enters a different way, alternating between:
  - slams down from large (`slam`, up to 1.25x);
  - expands from condensed to wide (the width axis together with letter spacing);
  - slides in from the side with motion blur;
  - revealed with a design-tool selection box: a thin frame, 8 handles, and a small mono dimension label ("W 612 H 188").
- One font: `F.D` (Noto Sans Hebrew) at weight 900, with the width axis. Small technical labels in English in `F.MONO`.
- The camera never stops for a moment: a slight push, a rotation of a degree or two, and a short shake (`shake`) on every hit.
- **Forbidden:** an old-fashioned or serif Hebrew font, hollow outlined words, a hyphen between two words, soft gradients, a frame frozen for more than a third of a second, more than three full-screen flashes per second.

## Structure

A half-second grid, and a cut on every grid step. No music, or on the beat if the user provided a song (`bpm` and `beat()` from `audio.py beat`).

A thin light bar crosses a black screen and opens into a colour field → the first word slams → cut to the next colour, and the next word expands to the screen width → a selection box snaps to a word, rotates and locks → the words join into one line with a red dot → ending with the whole message in the centre, on a cream background.

- **The grid:** `const G = n => 0.3 + 0.5 * n`. The light bar takes the first 0.3 seconds, and the first word lands exactly on the cut to colour (`G(0)`). With a song: `G = n => beat(n)`, and the bar before the first beat.
- **More grid steps than words:** every word gets a second grid step: a cut to another colour and its condensed version (`wdth` 62.5, tight spacing).
- **The join and the ending** take at least the last 1.7 seconds, so the full message is on screen for at least 1.5 seconds. In the join and the end frame all words may appear together. In the end frame there is a small event on every grid step (the dot pulses, a line closes), and the camera keeps pushing.
- **The selection box** rotates a few degrees, returns to 0 and locks, with a LOCKED label in mono.
- **Line or stack:** "one line" in square. In vertical format a single line of the whole message comes out too small in a tall frame, so the words stack into several lines, **all lines at the same font size**, with the red dot after the last word.
- Example, 4 seconds and 3 words: light bar 0 to 0.3, word 1 at 0.3, word 2 at 0.8, word 3 with selection box at 1.3 to 2.3, join at 2.3, ending on cream at 2.8 to 4.0.

## Build

- `CONFIG`: `W: 1080, H: 1920, DUR: <length>, bg: '#0E0E10'`, and with the default palette `palette: {WHITE: '#EFEAE2'}`, so the only light colour is the palette's cream.
- **Camera:** `const cam = grp(root, W/2, H/2)`, with all content inside it, centred around 0,0 (i.e. `x: 0` is the frame centre). In every shot: `s` from 1 to 1.04 over the shot, `r` within one degree each way, plus `shake`.
- **Vertical position in Reels:** a hero word sits a little above the middle (the word's centre at about `-0.1 * H` relative to the camera centre), so it is entirely in the upper half. In the lower half Instagram's buttons shorten the safe area on the right (principles.md section 8).
- **Colour fields:** a full-size `div` per shot, outside the camera, shown only in its time window (`on(el, t >= a && t < b)`). A hard cut, no fade.
- **Text colour:** only from the approved palette. On black: cream. On red: ink. On blue: cream. On yellow: ink. On cream: ink. The red dot never on a red or blue background.
- **Opening:** a 4 px tall bar crosses the screen on a fast spring (`x` from `-W` to 0), then `sy` from 1 to full height (`S(u, 40, 1)`). The bar is already visible at frame 0, so the opening isn't a black screen.
- **Word size:** `fit(word, {font: F.D, weight: 900}, 840 * W / 1080)`, and no more than 520. That is about 840 px: the safe area (920) minus room for the push and shake. In a stack, all lines at the same size: the size of the widest line. A very long word: `wdth` 75 before shrinking.
- **Slam:** `const from = Math.min(1.25, (W - 40) / (wordWidth * 1.04)); const k = slam(t, t0, from); tf(g, {s: k.s, o: k.o})`. The spring goes slightly below 1 and returns. Together with `shake(t, [[t0, 14]])` on the camera and `sfx(t0, 'hit')`. That way even the largest frame of the slam stays inside the frame and doesn't touch its neighbour. A little anticipation helps: 0.08 seconds before the slam, the colour field is pushed in by 1 or 2 percent.
- **Expand:** Noto Sans Hebrew's width axis changes only about 16 percent, so animate three things together: `const k = S(t - t0, 26, 0.68); const c = clamp(k, 0, 1); g.inner.style.fontStretch = lerp(62.5, 100, c) + '%'; g.inner.style.letterSpacing = lerp(-0.04, 0.03, c) + 'em'; tf(g, {sx: lerp(0.6, 1, k), o: t >= t0 ? 1 : 0})`. Compute the size from the final state (`wdth` 100, `ls` 0.03). The font in `fonts/` already includes the axis (measured: 825 vs 975 px).
- **Slide:** the word may start outside the frame, on the right (the reading direction), provided it crosses the edge fast, in a frame or two: `const X = t => (1 - S(t - t0, 30, 0.8)) * W`, and `tf(g, {x: X(t), mb: [vel(X, t), 0]})`. In such fast motion tmix shows separate copies, and `mb` adds a small directional blur based on velocity. A slow slide through the frame edge leaves a single letter on screen (the edge acts like a mask), so either fast from outside, or a short distance from inside the frame with rising opacity.
- **Selection box:** an SVG with a rectangle (`stroke` 3), 8 handle squares (14 px, cream fill, blue stroke), and a mono label below. The box enters 15 percent larger and rotated 6 degrees, returns to 0 and snaps to the word's dimensions on a spring (`wn` 22, `z` 0.7), then the label changes to LOCKED. The word itself enters with `rise` during the lock. `sfx(t, 'tick')` on the lock. A cursor grabbing a handle and enlarging the box adds a lot (`cursor(parent, 62, C.INK, C.WHITE)`).
- **Join:** the targets are computed in advance (line or stack, with `x: 0` since content is inside the camera). Each word moves from its position and size to the target on a `track`, or re-enters with a short `rise` right to left. A red dot (circle) to the left of the last word, entering with a small `slam` and `sfx(t, 'pop')`.
- **Ending:** cream background, the message in ink, the dot in red. A slow camera push until the last frame, and a small event on every grid step (a dot pulse, a thin line closing underneath).
- **Sound:** `hit` on every slam and important cut, `tick` on the selection box, at most one `whoosh`, `impact` on the ending.
- **stills:** one in the middle of every grid step (`G(n) + 0.25`), plus one 0.05 seconds after every slam (its biggest moment).

## Pitfalls

- Never reveal a Hebrew word from behind a cut line (mask), because the top of the letters looks like lines and dashes. Every word enters whole: with a short upward move and opacity rising from 0 to 1, a slam, an expand, or a fast slide.
- Condensed to wide only works with a locally loaded variable font with a width axis, and even then the axis alone is barely visible: letter spacing does most of the work.
- In Reels text stays in the safe area: 250 px from the top, 350 from the bottom, 80 from each side, and 140 from the right in the lower half (Instagram's buttons). A brief slam moment outside the area is allowed, outside the frame is not.
- `render.py check` checks in pixels, across all frames, that no word touches its neighbour or leaves the safe area.
- More than three flashes per second: a colour cut every half second is two per second. Don't add white flashes on top. `render.py flashcheck` measures it (a cut from dark to light counts as a flash).
- The mono dimension label is decoration, not text to read. It is exempt from the minimum size.

## Approval list

A table of the grid: time | on-screen text (including small labels and the dot) | background colour | text colour | entrance type | sound. Under the table: line or stack at the end.
