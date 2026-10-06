# 04 Cubes 3D

**When:** an energetic background for a headline, an opener, a transition. Showreel mode.

## Input

- A short headline, 2 to 5 words, that appears above the world.
- Colours. Default: light grey cubes, with a few red and blue cubes.
- Length: 6 to 12 seconds (default 8).
- Size: 1080x1920 (default), 1080x1080, 1920x1080.

## Direction

- A field of about 16 by 22 square columns, rising and falling in a wave that travels across the field.
- An angled camera, slowly orbiting the field. A long lens: a vertical field of view of 30 to 35 degrees, so the angle doesn't distort.
- A red ball bouncing from column to column, with squash and stretch and a shadow on the cubes.
- Simple lighting: a bright top face, two darker side faces, and distant cubes fading into the background.
- A grey to white background with a subtle gradient, and the fog fades exactly to the background colour.
- The Hebrew headline large and readable above the field, with a soft shadow behind it (`F.D` 900). The field sits in the lower two thirds of the frame.
- **Forbidden:** realistic textures, reflections, the ball or cubes passing over the headline, a hyphen between two words.

## Structure

- A top-down view.
- The camera dives to a 35-degree angle.
- The wave travels across the field.
- The ball stands on a column from the first frame, and bounces 3 or 4 times.
- The headline enters word by word. The important word enters last, larger and in the ball's red, on the last landing, and at that moment the whole field jumps together.
- The camera slowly pulls back until the end.

## Build

- `canvas2d(root)` and your own projection. three.js is possible (render-pipeline.md), provided every frame is rendered manually from seek.
- **Background:** a subtle vertical gradient from light grey to white (allowed here, it isn't a UI component). The fog mixes each face toward the background colour **at the same screen height**, so distant cubes disappear into it without a line.
- **Camera:** `yaw(t)` slow linear, `pitch` from 90 (top-down) to 35 on `S(t - t0, 5, 1)`, and a pull back at the end on a spring. Every camera move is a closed-form spring. Projection: rotate by yaw and pitch, then `s = f / z` with `f = (H / 2) / tan(fov / 2)` and a vertical `fov` of 30 to 35 degrees.
- **Framing:** the field centred in the lower two thirds (projection centre at about `0.6 * H`), and the headline in the upper third.
- **Column:** `h(i, j, t) = base + A * (0.5 + 0.5 * sin(k * (i * cos(dir) + j * sin(dir)) - w * t))`, plus the shared jump: `jump * (S(t - tj, 18, 0.45) - S(t - tj - 0.25, 14, 0.7))`.
- **Drawing:** each column has three visible faces (top and two facing the camera). Face colour: top 100 percent, one side 78, the other side 62.
- **Sort every frame** by horizontal distance from the camera, far to near. The ball goes into the same list as an item.
- **Ball:** a list of landings `[[t, i, j], ...]`, and the first landing is the first frame (the ball stands on a column). Between two landings: x and y on a straight line, and the height a closed parabola `h0 + (h1 - h0) * u + 4 * H * u * (1 - u)`, where `u = seg(t, ta, tb)` and `h0`, `h1` are the column heights **at the moment** of takeoff and landing. Stretch along the direction of motion by velocity. Squash on landing by impact velocity (`S` with `z` 0.4), with the bottom of the ball staying on the face. Shadow: a soft dark transparent ellipse on the top face below it, falling straight down, and smaller the higher the ball is.
- **Headline:** `txt` in a DOM layer above the canvas, with a soft dark `textShadow` (`0 10px 40px rgba(0,0,0,.35)`). Words enter one at a time with `rise`, in order right to left (`row`). The important word last, 15 to 25 percent larger, in the ball's red, with a small `slam` on the last landing, together with the field jump and `shake`.
- **Headline above everything:** measure every frame the highest point of the field on screen (including the wave peak, the shared jump and the ball's bounce peak), and make sure it is below the bottom of the headline. Report the values with `report('fieldTop', y)` and `report('titleBottom', y)` (render.py check and stills print them), not in the console. If not: lower the field, reduce A, or choose other landings.
- **Sound:** `thud` on every landing, `hit` on the headline words, `impact` on the shared jump, one `whoosh` on the camera dive.
- **stills:** one per stage, plus one at every landing.

## Pitfalls

- Without depth sorting, faces draw in the wrong order and it becomes a mess.
- The ball's path must avoid the headline area.
- Every Hebrew word enters whole, with a short upward move and rising opacity, not from behind a cut line (mask).
- A landing point computed from a fixed column height makes the ball float or sink, because the column is in the wave. Always the height at the moment of landing.
- Fonts load from local files and core.js waits for them before the first frame.
- 350 columns with 3 faces every frame is fast in canvas. One `ctx.beginPath` per face, no `shadowBlur`.

## Approval list

The list of stages with times, the headline (and which word is the important one), colours, and the number of ball bounces.
