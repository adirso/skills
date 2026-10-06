# 06 Doodle

**When:** a light, cute, humorous message. A character that says one sentence. A loop.

## Input

- The character: a short description, e.g. "an orange cube with little legs".
- What it does: 2 to 4 actions (default: walks in, jumps, waves).
- One sentence it says in Hebrew.
- Length (6 to 12 seconds, default 8) and size (default 1080x1080).

## Direction

- Hand drawing on paper: black, imperfect pencil lines, a single-colour fill with pencil texture, a light paper background with subtle grain.
- The lines wobble slightly 10 times a second, like hand-drawn animation (boil).
- Classic animation principles: anticipation before a jump, squash and stretch on landing, follow-through in the hands and ears.
- A handwritten speech bubble: `F.HAND` (Amatic SC) at weight 700, size 160 at least. `fonts.css` loads both the Hebrew and the Latin subset, for punctuation. Small motion lines next to every action.
- If the character has no hands, add small hands for waving. If it has no ears, one soft part (a tip, a tail, hair) lags behind the motion.
- **Forbidden:** perfect vector lines, gradients, a hyphen between two words. Shadow allowed only as a pencil scribble under the feet.

## Structure

The character walks in from the right → stops on one side of the frame and looks at the camera → anticipation and a jump → landing with a squash → the speech bubble is written word by word → a reaction (blink and wave) → walks out to the left. The first and last frames are empty paper, so the loop is seamless.

The bubble is up top, on the other side of the character, and the full sentence stays on screen for at least 1.5 seconds.

## Build

- `CONFIG`: `loop: true`, `bg: '#F4EFE6'` (paper).
- One SVG. **The character is built from parts**, each part in its own `<g>` whose origin is at the pivot point (shoulder, hip, ear base): `transform="translate(jx jy) rotate(a)"`, with the path drawn relative to the pivot. That way a limb rotates and doesn't detach.
- **Rig:** the body (`x`, `y`, `sx`, `sy`, `r`) from one `track`. Walking: `x` on a track (enters from outside the frame on the right, exits outside the frame on the left), legs rotate by `sin(2 * PI * steps * u)`, the body rises and falls twice per step.
- **Jump:** anticipation (`sy` 0.82, `sx` 1.12, 0.2 seconds) → closed arc `y = -4 * Hj * u * (1 - u)` → stretch by velocity (`sy = 1 + 0.25 * |vy| / vmax`) → squash on landing with `S(t - tl, 16, 0.4)`. The transition from anticipation to stretch lasts at least 8 frames (0.13 seconds), otherwise motion blur shows copies.
- **Follow-through:** a spring driven by the motion curve and recomputed every frame: the angle of the ears (or the soft part) and hands is derived from the body's velocity, computed by finite difference of the closed-form function (`vel(y, t)`), with a delay (`y(t - 0.06)`). No stored state.
- **Line boil:** each anchor point in the path is offset by `(hash(i * 7.1 + step * 13.3) - 0.5) * 3`, where `step = Math.floor(t * 10) % Math.round(DUR * 10)` (modulo the number of steps in the loop, so the boil at the end connects to the start). The boil jumps in steps, the motion itself is smooth. Rebuild `d` on every seek.
- **Texture:** one SVG pencil filter (`feTurbulence` with a fixed seed + a small `feDisplacementMap`), defined once and never changed, sitting on the group that moves with the character, so the texture moves with it and doesn't "swim". Paper grain is a static layer over the whole screen. There is no zoom in this style; if you add a zoom, the filter is not inside the scaled group (principles.md section 11).
- **Outlines:** black `stroke` 5 to 7, `stroke-linecap="round"`, a single-colour fill. Shadow: a short pencil scribble under the feet, without fill.
- **Speech bubble:** the shape is drawn on (`stroke-dasharray` + `stroke-dashoffset`), then the words enter one at a time with `rise`. Each word in a separate `<text>` with `direction="rtl"` and `text-anchor="middle"`, positioned manually right to left (measure each word with `getComputedTextLength()` at build time). The tail points at the mouth.
- **Motion lines:** 2 or 3 short lines that appear for 0.2 seconds next to every action.
- **Blink:** the eyes' `sy` drops to 0.1 for 0.08 seconds.
- **Sound:** `pop` on the bubble, `boing` on the jump, `thud` on landing, a soft `tick` for every word in the bubble.
- **stills:** one per action, plus one at the jump peak, one at landing, and one when the full sentence is in the bubble.

## Pitfalls

- The boil must jump in tenth-of-a-second steps, not change every frame, otherwise it looks like noise.
- Limbs rotating around the wrong pivot detach from the body. Check a still in every extreme pose.
- The speech bubble is right to left, and its tail points at the mouth.
- The character doesn't leave the frame midway (not even at the jump peak), only on entrance and exit.
- Fonts load from local files and core.js waits for them before the first frame.

## Approval list

A sketch in words of the character (shape, colour, eyes, limbs), and the list of actions with times, including when each word in the bubble appears.
