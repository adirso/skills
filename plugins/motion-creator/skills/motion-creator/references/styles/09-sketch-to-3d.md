# 09 Sketch to 3D

**When:** explaining how a product or object works, showing a product, revealing a structure. Restraint mode.

## Input

- The object, e.g. a phone stand, a coffee machine or your product.
- 2 to 4 of its parts, with Hebrew names.
- What it does: one action.
- Length (10 to 15 seconds, default 12) and size (default 1080x1080).

## Direction

- Starts as a technical pencil drawing on white paper: lines drawn one after another, dimension lines with numbers, and Hebrew labels.
- Then hatching, the shapes fill with material (wood, metal), a shadow falls on the floor, and the camera rotates a little to reveal depth.
- At the end the object performs its action.
- Labels in `F.RUBIK`, dimension lines and numbers in `F.MONO`.
- **Forbidden:** a direct jump from sketch to 3D without intermediate stages, photographic textures, a hyphen between two words.

## Structure

- A blank page and a pencil. The pencil follows the line being drawn in a smooth motion, without jumps.
- A low camera, 8 to 12 degrees above the floor, so the shadow on the floor is visible.
- The outlines are drawn.
- Dimension lines and labels.
- Hatching.
- Material and colour fill.
- Camera rotation.
- The action.
- Hold (at least 1.5 seconds).

## Build

- **three.js in this skill:** the classic `three.min.js` build in the project folder (render-pipeline.md), with a plain `<script>` before `scene.js`. It works even when the page is opened from a file. (The module build of three.js is blocked in Chrome when the page is opened from a file, so outside the skill it needs a local http server.)
- `const renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true, preserveDrawingBuffer: true})`, `setPixelRatio(1)`, `setSize(W, H)`. The paper background in the scene's CSS (`bg: '#FAF8F3'`), and the canvas transparent.
- **seek starts by setting every transform from t** (position, rotation, opacity of every part and of the camera), and only then `renderer.render(scene3, camera)` at the end. No `requestAnimationFrame` and no stored state.
- **The object** from primitives: `BoxGeometry`, `CylinderGeometry`, `SphereGeometry`, `TorusGeometry`, `LatheGeometry` for turned shapes. Every part is a separate `Group` (for the action and for the labels).
- **Pencil lines:** edge lines (`new THREE.EdgesGeometry(geo, 25)`). WebGL lines are one pixel wide, so build a strip (two triangles) from every edge, 2.5 px thick on screen, and split every edge into short segments so the line grows gradually: the number of visible segments is `Math.floor(count * k)`, where `k = seg(t, a, b)`, part after part. For a sphere, a round outline that always faces the camera (a ring in the screen plane) instead of edges.
- **Hidden lines:** the solid body writes depth even while it is still transparent (`depthWrite: true`, and in the sketch stage `colorWrite: false`), so lines behind the object aren't visible. Otherwise you get a transparent wireframe.
- **Hatching:** a `ShaderMaterial` of diagonal stripes in screen space, whose density depends on how lit the face is (`dot(normal, light)`), and a second layer of cross-hatching in the dark areas. Its opacity rises from 0.
- **Material:** `MeshToonMaterial` with a `gradientMap` of 4 or 5 shades (wood `#C8955C`, metal `#9AA3AD`), whose opacity rises from 0 to 1 **after** the lines finish. The ink lines stay above the fill. Real metal (`metalness`) without an environment map comes out black, so metal is a grey shade in toon shading. Lighting: `HemisphereLight` + `DirectionalLight`.
- **Shadow:** a soft circle on the floor (a plane with a radial-gradient `CanvasTexture`), its opacity rising with the material. Simpler and more deterministic than a shadow map.
- **Camera:** low, 8 to 12 degrees above the floor, and an almost frontal view during the sketch. Then a 25 to 35 degree rotation on a slow `track` (`wn` 4 to 6).
- **The pencil:** a small pencil icon or drawing in an HTML layer, its tip on the last point of the line currently being drawn (projected to the screen), with smoothing: the average of the projection at several nearby times (`t`, `t - 0.03`, `t - 0.06`), so it doesn't jump between segments.
- **Labels and dimension lines in an HTML layer** above the canvas. 3D anchor point → `v.clone().project(camera)` → `sx = (v.x + 1) / 2 * W`, `sy = (1 - v.y) / 2 * H`. For each label compute a screen position before the camera rotation and one after it, and it moves between them on a spring (`track`), so it doesn't jump when the camera moves. Transform with two decimal places. Labels outside the object's silhouette, with a leader line.
- **Dimension lines:** at most 3, at the object's edges, not crossing each other. Numbers in `F.MONO`.
- **The action:** a closed-form function of time (rotation, opening, throwing), and at the end a small wobble: `amp * (1 - S(t - te, 14, 0.35))`. Around the release moment, slow motion of about 0.3: the action time passes through a curve that slows it around the release, otherwise a thrown ball or part leaves the frame in an instant.
- **Reading times:** every label on screen at least 1.3 seconds, and the end hold at least 1.5 seconds.
- **Sound:** `tick` as each part finishes drawing, `pop` on every label, one `whoosh` on the rotation, `thud` or `hit` on the action, `ding` at the end.
- **stills:** one per stage.

## Pitfalls

- three.js needs `preserveDrawingBuffer: true` and an explicit render after every seek. Otherwise the screenshot comes out empty.
- Labels computed from projection jump when the camera moves. Smooth them on a spring between the position before the rotation and the position after it.
- A label that crosses a line or leaves the frame: move the anchor or the side of the leader line.
- `EdgesGeometry` with too low a threshold angle draws all the triangles of a cylinder. 20 to 30 degrees.
- Fonts load from local files and core.js waits for them before the first frame.

## Approval list

The list of stages with times, the parts that will get labels (with exact names), the dimension lines, and the action at the end.
