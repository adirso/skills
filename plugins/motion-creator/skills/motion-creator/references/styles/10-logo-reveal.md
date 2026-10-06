# 10 Logo Reveal

**When:** the opener or closer of a business video, from the user's own logo file. Restraint mode: the logo is the star, and it stays identical to the original.

## Input

- The logo file. SVG is best, but a PNG with a transparent background also works. Copy it into the project folder.
  - Read the file's `<title>` and metadata. If they name a well-known brand, ask once whether the logo belongs to the user (SKILL.md §5, item 6).
- A Hebrew slogan of 2 to 6 words, or no slogan.
- Light or dark background. Default:
  - A logo with black text gets a light background, and a logo with white text gets a dark background, in a subtle shade taken from the logo.
  - An all-black logo gets a neutral light grey, `#F6F6F4` to `#E2E2DE`.
- Length (4 to 8 seconds, default 6) and size (default 1080x1080; also 1080x1920 or 1920x1080).

**Before the approval list** count what's in the file, without opening a browser:

```python
import re; s = open('logo.svg', encoding='utf-8').read()
print({k: len(re.findall('<' + k + r'[\s>/]', s)) for k in ['path', 'image', 'mask', 'clipPath', 'filter', 'text', 'use']},
      re.search(r'viewBox="([^"]+)"', s), re.findall(r'<title>(.*?)</title>', s))
```

## Direction

- A logo reveal like a commercial opener. The logo builds from its parts: the outlines draw themselves, the shapes fill, and the icon lands with a small bounce.
- Every part enters at a slightly different time, on a spring, so the logo feels alive.
- After the logo is built, a light sweep crosses it once.
- The slogan below, word by word with `rise`, `F.RUBIK` at weight 500. The colour is taken from the icon, with a contrast of at least 4.5:1 against the background. If there is no such colour, the slogan is in the logo's text colour.
- A single-colour background with a subtle gradient, and a soft drop-shadow on the whole logo (10 to 20 percent opacity). Not an ellipse on a floor.
- At the end the logo is identical to the original: the same colours, proportions and position of every part.
- **Forbidden:** distorting the logo, changing its colours, redrawing it, glow or particles that hide it, an old-fashioned font for the slogan, a hyphen between two words.

## Structure

- An empty background, and a dot in the logo's colour appears (`pop`) at the centre of the icon.
- The dot opens into the icon:
  - **A vector icon:** the outlines draw themselves, and each part fills right after the line passes through it.
  - **An icon that is an image:** the circle revealing it starts at the dot's size and grows outward.
  - While it builds, the icon rises 18 px (and can also rotate from -12 degrees to 0). On landing it drops back to the dot's position. The pivot for the rotation, scale and drop is the dot's centre.
- The letters of the brand name enter one after another, in the name's reading direction: an English name left to right, a Hebrew name right to left.
- The whole logo shrinks from 1.05 to 1 and lands.
- The light sweep crosses the logo.
- The slogan enters below, word by word.
- A hold of at least 1.5 seconds on the full logo. `CONFIG.hold` set to the hold length, so `render.py check` doesn't flag it as a frozen picture.

**A logo that is a single icon, with no name** (e.g. a star or a symbol from one path) has no letters entering one by one. Instead, split the icon into parts by its shape:
- Sample the outline with `getPointAtLength` (about 720 points), and measure each point's distance from the centre.
- Tips of rays or leaves are local maxima above 0.6 of the maximum radius, and the gaps between them are local minima.
- Each part is revealed through a wedge-shaped `clipPath` between two gaps. The wedge radius grows on a spring from the centre, starting the moment the line passes its first gap.

**Tested timing, 6 seconds:**

| Stage | Logo with name | Icon only |
|---|---|---|
| Dot | 0.25 to 0.55 | 0.25 |
| Icon builds | 0.55 to 1.35 | line 0.55 to 1.65, parts 0.66 to 1.48 |
| Letters | 1.05 to 2.35 (about 0.3 seconds per letter) | none |
| Landing | 2.3 to 2.9 | 1.72 |
| Light sweep | 2.82 to 3.37 | 2.65 |
| Slogan | 3.1 to 3.9 | 3.05 |
| Hold | from 3.9 to the end | from 3.5 to the end |

## Build

- **The logo goes into the page as code, not as an img.** `render.py` opens the page from a file, and `fetch` doesn't work from a file. So wrap the logo in `logo.js` with one command:
  `"$PY" -c "import json,pathlib; p=pathlib.Path('logo.svg'); pathlib.Path('logo.js').write_text('window.LOGO=' + json.dumps(p.read_text(encoding='utf-8')), encoding='utf-8')"`
  and add `<script src="logo.js"></script>` before `scene.js`. For a PNG, wrap a data URL: `'data:image/png;base64,' + base64`.
- **Inserting into the page:**

  ```js
  const txt = window.LOGO.replace(/\bid="([^"]+)"/g, 'id="lg-$1"')          // prefix: ids from the file must not clash with the page
    .replace(/url\(#([^)]+)\)/g, 'url(#lg-$1)').replace(/href="#([^"]+)"/g, 'href="#lg-$1"');
  const src = new DOMParser().parseFromString(txt, 'image/svg+xml').documentElement;
  src.querySelectorAll('title, metadata').forEach(n => n.remove());
  const [vx, vy, vw, vh] = src.getAttribute('viewBox').split(/[\s,]+/).map(Number);
  const k0 = SIZE / vw;                                                        // px per viewBox unit
  const box = svgBox(cam, -SIZE / 2, -SIZE * vh / vw / 2, SIZE, SIZE * vh / vw);
  const art = svgEl('g', box, { id: 'lg-art', transform: `scale(${k0}) translate(${-vx} ${-vy})` });
  for (const a of ['fill', 'stroke', 'fill-rule', 'style']) if (src.hasAttribute(a)) art.setAttribute(a, src.getAttribute(a));  // the root's paint is inherited
  [...src.childNodes].forEach(n => art.appendChild(document.importNode(n, true)));
  ```

  An id starting with a digit works only with the prefix.
- **Measurements:** `getBBox`, `getTotalLength` and `isPointInFill` work only when the SVG is in the page and visible. `core.js` builds every scene while it is visible, so measure inside the build.
- **Grouping parts:** by each part's `getBBox`: the icon, every letter of the name, and small details. The letters' entrance order is by on-screen `x`, not by order in the file (in exported files it is random).
- **An icon that is a masked image:** `getBBox` returns the image's rectangle, not the visible shape. Compute the icon centre and the dot colour from the pixels:
  - Draw the mask image onto a hidden `canvas2d` at build time (a data URL doesn't taint the canvas).
  - Find the centre of the opaque area.
  - Don't draw the image itself. Reveal it with your own round `clipPath` around the original group, inside the moving group, so the circle moves with the bounce.
- **A self-drawing line:**
  - `k = E.smooth(seg(t, a, b))`. Not a spring: a spring draws half the line in a third of the time.
  - Width 2.5 px on screen: `stroke-width = 2.5 / (k0 * s(t))`, where `s(t)` is the logo's current scale, including the landing's 1.05.
  - **Start point:** in exported files the path's start point is random, sometimes in the middle of an edge. Start in a gap between parts, at distance `S0` along the line. `L` is the length, `p` the progress:
    - Without wrap: `dasharray = p·L, L` and `dashoffset = -S0`.
    - With wrap: `dasharray = e, S0 - e, L - S0, L`, where `e = S0 + p·L - L`.
  - The outline is a copy of the path with `fill="none"`. `use` can't override a `fill` written on the path itself.
  - **The fill:**
    - Letters: `fill-opacity` from 0 to 1 per letter, right after its line finishes, then the line fades.
    - Icon parts: grow from the centre (the wedges above) rather than appearing in a uniform fade, which looks like a template.
- **The design tool's tight clipPath:** in files from Canva every word sits inside a tight rectangular clipPath, and a letter that moves outside it gets clipped. Measure the margin (`report`) and move letters only within it: entering from above, with a spring that overshoots the target by 2 units at most.
- **The light sweep:**
  - A rectangle at 20 degrees, 0.3 of the logo width wide, with a transparent white gradient (0, 0.55, 0).
  - It crosses the logo width once, with progress `S(τ, 10, 1)`.
  - Its mask is `<use href="#lg-art">` with a `feColorMatrix` that turns every colour white and keeps the alpha: `0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 1 0`.
  - The `use` and the sweep sit in the same coordinate system (both inside `box`).
  - On a black logo the sweep looks like grey chrome, and that's fine.
- **Landing:** a `track` on the whole logo's scale, from 1.05 to 1, `wn` 10 to 12.
- **Background:**
  - A subtle `radial-gradient`.
  - Above it, under the logo, a static grain layer: a `canvas2d` filled once with noise, 5 percent, `mix-blend-mode: overlay`. It keeps the gradient from banding in MP4 and GIF.
  - The grain sits under the logo, not above it, so the logo's colours stay exact.
- **Embedded images:** for every `image` in the SVG create an `Image` with the same href and push `img.decode()` into `PRELOAD`. Otherwise the first frame comes out without the icon.
- **Sound:** 4 to 6 events, per `references/sound.md`:
  - `pop` on the dot;
  - one soft `tick` for every 2 or 3 letters, or for every slogan word when there is no name;
  - `swish` on the light sweep;
  - `chime` on the landing.
- **Check against the original:**
  - `compare.html` in the folder:
    - the same `window.CONFIG`, `window.seek = () => {}` and `window.ready = Promise.resolve(true)`;
    - only `<img src="logo.svg">` in exactly the same rectangle;
    - no background and no shadow.
  - `PAGE=compare.html "$PY" render.py stills <DUR>`, rename the file created in `stills/` (the next run writes to the same name), then `"$PY" render.py stills <DUR>`.
  - A short numpy script compares only solid ink pixels (for a dark logo: brightness below 60), because the background and shadow differ on purpose.
  - The target:
    - the centre moves less than half a pixel;
    - overlap (IoU) above 0.99;
    - the same mean colour.
- **GIF for websites:** `"$PY" render.py gif len=<DUR>`, the whole animation, so the loop doesn't restart right after the logo locks. 6 seconds at 400 px comes out at about 0.3 to 0.7 MB.
- **stills:** the dot, the middle of the icon reveal, the middle of the letters, the landing, the middle of the light sweep, and the last frame.

## Pitfalls

- An SVG from Canva weighs several MB, with base64 images. Don't copy it into `scene.js`; it stays in `logo.js`.
- The light sweep doesn't cross the slogan, and doesn't leave the logo's bounds.
- The Hebrew slogan enters whole, word by word, right to left. No mask on the text.
- A white logo on a light background disappears. The background is chosen by the logo's text colour.
- The dot, the circle and the icon share the same centre. If the icon moves and the circle doesn't, the arrow slides through a fixed window.

## Approval list

What's in the logo file (parts, colours, embedded images, the title) and how each part will be revealed, the stages with times, the background, the slogan colour, and the sound.
