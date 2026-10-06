# 03 Particles

**When:** a brand, name or single word reveal. A short wow moment. Showreel mode.

## Input

- One word or brand name that will break apart.
- Colours. Default: white, red `#E54136` and blue `#2E3BFF` on black.
- Length: 6 to 12 seconds (default 9).
- Size: 1080x1920 (default), 1080x1080, 1920x1080.

## Direction

- The word appears sharp, holds, then breaks into thousands of particles sampled from its pixels.
- At the opening and the ending the word is real, solid text, and the particles leave from it and are absorbed into it at exactly the same points.
- The particles gather into a sphere, the sphere swirls into a spiral galaxy, and at the end everything is pulled back to rebuild the word, sharp and solid.
- Depth: near particles large and bright, far ones small and dim.
- A dark background with a subtle vignette. Font `F.D` at weight 900.
- **Forbidden:** uncontrolled random sparkles, particles flickering every frame, a hollow word, unreadable text at the opening and ending.

## Structure

The times are written for 9 seconds including the end hold. For another length, scale all times by the same ratio.
- 0 to 1.5: the word slams (at most from 115 percent of its size) and holds.
- To 2.5: a tremor, and a breakup starting from the right edge, in reading direction.
- To 4: a particle sphere rotating in three dimensions.
- To 6: a spiral galaxy with red and blue arms.
- To 7.5: acceleration, half a second of full light speed, and exit. The camera dives into the galaxy: every particle keeps its screen position at the moment of the dive, gets a random depth and flies forward.
- To 8.5: everything is pulled in and rebuilds the word.
- 8.5 to 9: half a second hold on the sharp word.

## Build

- One scene with `const g = canvas2d(root)`. Every seek starts with `g.clearRect` and redraws everything.
- **Sampling at build time:** a hidden canvas (`document.createElement('canvas')`) of size W x H. `ctx.direction = 'rtl'; ctx.textAlign = 'center'; ctx.font = '900 <size>px "Noto Sans Hebrew"'`, size from `fit()`. `fillText`, then `getImageData` and sample 4000 to 8000 filled pixels with `rng(seed)`.
- **Homes per particle** (arrays computed once): `word` (the sampled pixel), `sphere` (a point on a Fibonacci sphere of radius R), `galaxy` (arm `i % 2`, radius `R * sqrt(u)`, angle `r * twist + arm * PI` and a small scatter), colour (white in the word, red or blue by arm), and a personal delay `hash(i) * 0.3`.
- **Match the shapes by position,** so particles don't cross each other: word to sphere by screen position (sort both lists in the same order), sphere to galaxy by angle. In the pull back, each particle gets the word point that lies ahead of it in the rotation direction, so they all swirl the same way.
- **Position:** a function of time moving between homes: `p = lerp(home1, home2, E.io3(seg(t - delay_i, a, b)))`. No accumulating simulation.
- **Breakup from the right:** each particle's delay grows the further left its x is: `delay = (W - x) / W * 0.6 + hash(i) * 0.15`.
- **3D:** the rotation angle is a function of time. `x' = x cos a + z sin a`, `z' = -x sin a + z cos a`, then `s = f / (f + z')`, screen position `cx + x' * s`, size `r0 * s`, brightness by `s`.
- **Galaxy:** the arms trail behind the rotation direction, and the inner part spins faster: the angle of a particle at radius r is `a0 + w(r) * t` with `w` decreasing with r.
- **Dive (light speed):** at the dive moment `td`, compute each particle's screen position at `td` (from the same formula), give it a depth `z0` from `hash(i)`, and from there `z` decreases over time and the screen position opens out from the centre by `f / z`. Still a function of time.
- **Glow:** `g.globalCompositeOperation = 'lighter'` while drawing particles, and `'source-over'` afterwards. No `shadowBlur` per particle (slow), no CSS filter.
- **A fast particle** is drawn as a short streak between its position at t and its position just before (`t - 1 / 120`), not as a dot. Otherwise motion blur shows 4 separate dots. This is critical at light speed.
- **The sharp word:** at the opening and ending draw the word itself on the canvas (`fillText`, same font and size as the sampling), so particles leave from it and are absorbed into it at exactly the same points. During the breakup it fades right to left as the particles start to move. In the assembly, it fades in as the particles arrive.
- **Vignette:** one radial gradient drawn in the background (allowed here, it isn't a UI component).
- **Sound:** `hit` on the slam, `rise` before the sphere, one `whoosh` on the dive, `impact` on the assembly, `sparkle` on the sharp word.
- **stills:** one per stage (0.8, 2.2, 3.5, 5.2, 7.2, 8.2, 8.8, scaled to the length).

## Pitfalls

- `Math.random` only at build time, through `rng(seed)`, otherwise every frame renders differently and parallel rendering breaks.
- Sampling must happen after the font has loaded from the local file. Inside `scene()` that is already guaranteed (core.js waits for `document.fonts.load`).
- Canvas needs `direction = 'rtl'` for Hebrew to come out right.
- The word is drawn in canvas, so `render.py check` doesn't see it: readability at the opening and ending is checked by eye on the stills.
- 8000 particles with `arc()` is fine. `fillRect` is faster for small particles.

## Approval list

The list of stages with times, colours, and what happens to the word in each stage.
