# Hebrew on Screen

Most bugs in Hebrew animation repeat themselves. The rules here were tested in Chromium rendering, which is the browser that captures the frames.

## Fonts (all in the `fonts/` folder, loaded automatically)

| Font | `F.` | Hebrew | When |
|---|---|---|---|
| Noto Sans Hebrew | `F.D` | yes | Headlines and heroes, weight 900. Width axis `wdth` from 62.5 to 100 (changes only about 16 percent, see below) |
| Rubik | `F.RUBIK` | yes | UI text, labels, 400 to 700 |
| Heebo | `F.HEEBO` | yes | UI text, alternative |
| Amatic SC | `F.HAND` | yes | Handwriting, speech bubbles, 400 or 700 |
| Archivo | `F.LAT` | **no** | English headlines only |
| JetBrains Mono | `F.MONO` | **no** | Small technical labels in English and numbers ("W 612", "ROT 12°") |

- Hebrew text in `F.MONO` or `F.LAT` falls back to a system default font. Always use a font with Hebrew for Hebrew.
- No old-fashioned looking fonts (classic serif), and no hollow outlined words.
- **Noto Sans Hebrew's width axis is small:** from 62.5 to 100 the word changes only about 16 percent (measured: 825 vs 975 px). For a visible expansion, animate `letter-spacing` along with it (e.g. from `-0.04em` to `0.03em`) and a bit of `sx`. Before relying on a font axis, verify it exists: `measure(s, {wdth: 62.5}).w` and `measure(s, {wdth: 100}).w` must differ.
- A new font: download the woff2 from Google Fonts (OFL license), add an `@font-face` to `fonts/fonts.css` and add it to `FONT_LOADS` in core.js. Otherwise it does not load before capture.

## Direction

- `txt()` is RTL by default. Do not pass `dir: 'ltr'` to Hebrew text: punctuation ("!", ",") will jump to the wrong side.
- Numbers and English inside a Hebrew sentence sort themselves out when the base is RTL. A label that is all English or numbers gets `dir: 'ltr'`.
- Layout: the first word is on the right. `row(parent, ['תנועה', 'שעוצרת', 'גלילה'], {x, y, size})` lays words out right to left, each in its own group, so every word can enter at its own time.
- Lists, menus, tabs, chat bubbles, charts (the first day on the right) and UI: everything right to left.
- **The exception:** progress bars, sliders, media timelines and loading bars fill left to right, as in any player.
- Typing: characters appear in reading order, and the blinking caret is on the left side of the text (where it grows).
- Line breaks: never let the browser break a line. Every line is a separate `txt` (`.tx` is `nowrap`).

## Word entrances

- **No masks.** A Hebrew word revealed through a mask edge (clip, wipe, an opening window) looks mid-reveal like lines and dashes, or like a different word. **The frame edge is a mask too:** a word sliding in from off-screen leaves a single letter visible for a moment. Slide only a short distance, from inside the frame, with rising opacity.
- Correct entrance: `rise(t, t0)` a short rise with opacity coming up over 60 ms. Or `slam(t, t0, 1.25)` a slam down from large.
- Slam up to 1.25x at most (1.15 in the particle word), and at most one word in three enters with a slam. The rest rise, expand (`wdth` 62.5 to 100) or slide in from the side.
- Letter by letter (`letters`): each letter enters whole, starting from the rightmost letter (the first in reading order) moving left.

## Hyphens

- **No hyphen between two words**, in any on-screen text, including labels and UI. Write "העתק הדבק" with a space and no mark between them.
- No em dash or en dash either. Use a comma, a period or a new line instead.
- A prefix letter with a hyphen before a number or an English word ("ב-2026") is correct Hebrew, but on screen it is better to phrase without it.
- `render.py check` looks for a hyphen between Hebrew letters in all DOM and SVG text.

## Canvas

- `ctx.direction = 'rtl'` before every Hebrew `fillText`. Without it punctuation moves to the right side.
- With `rtl`, `textAlign = 'right'` or `'start'` pin the **right** edge to the point. `'center'` is always safe.
- `ctx.font = '900 200px "Noto Sans Hebrew"'` before `measureText`. Fonts are already loaded when the scene builds (core.js waits for them), so sampling a word's pixels at build time uses the right font.

## SVG

- `<text>` with `text-anchor="middle"` is the safe choice. With `direction="rtl"`, `start` is the right side.
- **textPath (text on a path), tested in Chromium:** with `direction="rtl"`, the text **ends** at `startOffset` and stretches backwards, toward the start of the path. With `startOffset="0"` it simply disappears. So for a closed ring: text twice the circumference long, and `startOffset` moving between one and two circumferences (styles/05-type-rings.md). Without any `direction`, Chromium also orders the Hebrew correctly, and then `startOffset` is the start of the text. Either way, render a still and check the words read correctly.
- `vector-effect="non-scaling-stroke"` keeps the stroke width constant when zooming, but it is **not inherited**: put it on every `path` individually, not on the group. And it breaks a self-drawing line (`stroke-dashoffset` is then measured in screen pixels). For self-drawing lines: no non-scaling-stroke, and `stroke-width` computed every frame as the desired width divided by the zoom.
- Text inside a heavily scaled SVG distorts. Labels that must stay sharp sit in an HTML layer on top, with their position computed from the camera.

## Check before showing

1. Every word in the right order, right to left, in the exact spelling the user gave.
2. No hyphen between words and no em dash.
3. No letter clipped at a frame edge or by a mask.
4. Progress bars fill left to right, everything else right to left.
5. Punctuation on the correct side (period and exclamation mark on the left side of the last word).
