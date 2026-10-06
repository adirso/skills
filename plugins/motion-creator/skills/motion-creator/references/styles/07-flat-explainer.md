# 07 Flat Explainer

**When:** educational content. How something works, what happens inside, a step-by-step process. Restraint mode.

## Input

- The process, e.g. how a seed sprouts or how a message travels from a server to a phone.
- 3 to 5 stages.
- Palette: a paper background, one dark line colour and 5 fill colours, with a light and a dark shade of each. Default, warm children's book colours: paper `#F4E9D8`, line `#2E2A36`, and fills (light / dark): warm red `#F08A70` / `#C9523A`, orange `#F7B77A` / `#D9853B`, yellow `#F6D37A` / `#D6A93A`, teal `#5DB8AC` / `#2A7F74`, blue `#8FB5D9` / `#4F7FAE`.
- Length (10 to 20 seconds, default 14) and size (default 1080x1920).

## Direction

- Flat illustration like a quality children's book: simple shapes with rounded corners, one dark outline colour, a subtle grain texture.
- A cutaway that shows what happens inside.
- Each stage gets a short Hebrew label that appears next to what is happening, with a thin leader line (`F.RUBIK` at weight 700).
- Continuous transitions: the camera moves into the object, zooming into the cutaway, instead of cutting to a new scene.
- **Forbidden:** realistic shadows, strong gradients, labels that hide the illustration, a hyphen between two words.

## Structure

- Stage 1 from the outside.
- The cutaway opens as a round window in the wall, from the point the camera moves into, and stays open until the end.
- Zoom into the cutaway.
- Stages 2 to 4 happen inside the cutaway, each with its own label.
- If the last stage happens outside the object, the camera follows it out.
- Zoom out to the result.
- Ending with a title: the name of the process in 2 to 4 words, `F.RUBIK` at weight 800, above the result.

Every label on screen at least 1.3 seconds, and the ending title at least 1.5 seconds. If it doesn't fit in the chosen length, lengthen the video and say so in the approval list.

## Build

- One full-size SVG, with the whole illustration inside `<g id="cam">`. **The camera** is a `transform` on that group: `translate(W/2 H/2) scale(z) translate(-cx -cy)`, where `[z, cx, cy]` are a `track` with `wn` 6 to 8 and `z` 0.95 to 1.
- **The cutaway:** a round `clipPath` on the outer wall layer (or a mask on the wall), whose radius grows on a spring from the point the camera moves into and stays open until the end. Under it is the inner layer. (This is a mask on illustration, not on text, so it is allowed.)
- **Growth and drawing:** a self-drawing line: `stroke-dasharray = len`, `stroke-dashoffset = len * (1 - k)` (the length from `getTotalLength()` at build time). Growth from a base point: a `transform` with `scale` around the base point (`transform-origin` with `transform-box: fill-box` or a manual calculation).
- **Constant stroke width:** `vector-effect="non-scaling-stroke"` on **every `path` individually** (it is not inherited from the group), otherwise lines thicken when zooming and look like a marker. Exception: a self-drawing line. On it non-scaling-stroke breaks the dash (Chrome then measures it in screen pixels), so go without it, with `stroke-width` computed every frame as the desired width divided by the zoom.
- **Labels in an HTML layer** above the SVG, not inside the camera. Their position is computed from the anchor point in the world through the same camera transform: `sx = W/2 + (x - cx) * z`. The leader line: a small SVG in the label layer, from the anchor point to the label.
- **Label:** `txt` in `F.RUBIK` 700, 56 to 72 px, on a paper-coloured plate with rounded corners. Enters with `rise` when the stage starts and exits when it ends, staying at least 1.3 seconds. Place it on the empty side of the frame.
- **Label check:** each label is checked on its first and last frame: whole inside the frame, and not hiding something that has grown in the meantime. `render.py check` checks the frame; hiding is checked on the stills.
- **Grain:** one static noise layer over the whole screen, **outside** the camera group (`feTurbulence` at 6 to 10 percent opacity, defined once). A grain filter inside the zooming group is very slow and the grain swells into blobs.
- **Ending title:** `F.RUBIK` 800 in the line colour, above the result, entering with `rise` word by word, and held at least 1.5 seconds before the end.
- **Sound:** `pop` on every label, one `whoosh` on the zoom in, `tick` on small stages, `chime` or `success` on the result.
- **stills:** one in the middle of every stage, one in the middle of every zoom, and one on the first and last frame of every label.

## Pitfalls

- At strong zoom, text inside SVG distorts. Labels always go in an HTML layer above the scene.
- `vector-effect` is not inherited: on every `path`, not on a group. And not on self-drawing lines.
- A zoom without a spring looks like a slideshow. A soft `track` with a slow start.
- Fonts load from local files and core.js waits for them before the first frame.

## Approval list

The stages with the exact labels and times, where the camera is in every stage, and the ending title.
