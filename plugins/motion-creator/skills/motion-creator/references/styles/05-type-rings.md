# 05 Type Rings

**When:** a list of principles, services, tags or values. The text is the shape. Showreel mode.

## Input

- A list of 6 to 12 words.
- A headline of 2 to 5 words.
- Colours. Default: white on black, with a red dot.
- Length (default 7 seconds) and size (default 1080x1920).

## Direction

- Lines of text run across the screen, each line in the opposite direction to the one above.
- Then they bend and close into rings that rotate one inside the other, in opposite directions, with a red dot in the centre.
- 5 to 6 rings, the long words in the outer ones, all within the frame width.
- The headline large and readable, in two lines, with the red dot between them. Behind it a dark circle (`#141414`) that covers the two inner rings.
- At the end the rings are pulled in a spiral to the centre, and only the dot remains.
- Font `F.D`, with a separator dot (" · ") between words.
- **Forbidden:** rings in the colour and size of the headline until it gets swallowed by them, reversed letter order or mirrored letters, a hyphen between two words. Text that looks upside down in the lower half of a rotating ring is fine.

## Structure

- 0 to 1.5 seconds: lines running in alternating directions.
- To 2.5: the lines bend into arcs and close into rings.
- To 5: the rings rotate and the headline enters.
- To 6: spiral inward.
- To 7: the dot pulses and stays.

The times are scaled to the chosen length. The lines brake and stop on a word boundary before they bend. They are all above the dot and bend the same way, the innermost first, and rotation starts only once the ring is closed. In the spiral each ring opens into a coil and shrinks into the space the inner ring vacated, and the ends are cut only between words.

## Build

- One SVG (`svgBox(root, 0, 0, W, H)`). Each ring has its own `<path>` and a `<text>` with `<textPath href="#id">`.
- **Word distribution:** 5 to 6 rings, the long words in the outer ones. The outer radius within the frame width (about `0.44 * W`).
- **The path is recomputed every frame** from a curvature parameter `k` moving from 0 to 1 (`S(t - t0, 7, 1)`, innermost first). Path length is constant: `L = 2 * PI * R`. For very small `k`: a straight line of length L. Otherwise: an arc of radius `rho = R / k` spanning an angle of `2 * PI * k`, with its middle at the top. Sample 120 points and build a polyline `d`. All lines start above the dot and bend the same way, and the centre moves from the line's height to the frame centre with the same `k`.
- **Path direction:** clockwise, so letters stand upright at the top of the ring.
- **Hebrew on textPath:** with `direction="rtl"` the text **ends** at `startOffset` and stretches backwards. So the text is twice the circumference long, and `startOffset` moves between L and 2L. With `startOffset` 0 the text simply disappears. (Without any `direction`, Chromium also orders Hebrew correctly; if you choose that, `startOffset` is negative. Either way, render a still and check the words read correctly.)
- **A closed ring without a seam:** measure the text unit `U` (the ring's list with separators), and calibrate each ring's font size so `L / U` is a whole number n. The text itself is the unit repeated `2n + 1` times. Otherwise there is a gap or overlap at the seam.
- **The separator `·`** is in the font's Latin subset. `fonts.css` already loads both.
- **Scroll and brake:** in the lines stage, `startOffset = L + (((v * t) % U) + U) % U` (positive modulo, so a negative `v` also stays in range), and in the time before bending the scroll brakes on a spring and stops on a word boundary (round the target to a multiple of the word width with its separator). The ring's rotation (the same `startOffset` continuing) starts only when `k` reaches 1. `v` alternates positive and negative between rings.
- **Speed:** at most 8 px between one sub-frame and the next, otherwise you see copies. The sub-frames are spread over half a frame, so the distance between them is `v / (120 * SUB)` px, where `v` is in px per second along the path.
- **Opacity and size:** the rings at 0.4 opacity. Small inner rings get a smaller font (roughly proportional to the radius), otherwise the letters get crammed.
- **Headline:** a `#141414` circle in the centre (`box` with `borderRadius: '50%'`) covering the two inner rings. The headline in two lines above it, with the red dot between them. Every word with `rise`, and the dot with a small `slam`.
- **Spiral:** each ring opens into a coil (the radius along the path gradually decreases) and shrinks into the space the inner ring vacated, from the inside out. The text is cut at the ends only between words. The dot pulses at the end: `s = 1 + 0.08 * sin(2 * PI * 1.5 * t)`.
- **Sound:** `tick` as each ring closes, `hit` on the headline, one `whoosh` on the spiral, `pop` on the dot.
- **stills:** 0.7, 2.0, 2.6, 3.8, 5.5, 6.6 (scaled to the length).

## Pitfalls

- `direction="rtl"` with `startOffset` 0 makes the text vanish. The range is L to 2L.
- Text that doesn't fill the circumference exactly leaves a gap in the ring. That's why the unit repeats and the size is calibrated per ring.
- Inner rings with the same font as the outer ones get crammed.
- The headline must stand out: full colour and weight 900, the rings semi-transparent, and the dark circle behind it.
- Fonts load from local files and core.js waits for them before the first frame.

## Approval list

The list of stages with times, the word distribution across rings (which ring gets which words, outside in), and the headline in two lines.
