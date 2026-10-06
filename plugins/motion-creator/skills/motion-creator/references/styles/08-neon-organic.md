# 08 Neon Organic

**When:** a dramatic moment, an idea lighting up, a network, a connection. Showreel mode.

**Tested example:** `assets/examples/08-neon-organic.js` (1080x1920, 6 seconds). It implements everything written here: a neuron, a two-line headline under the node, roots that split around the headline and meet below it, and everything inside the frame. Start from it: copy it over `scene.js`, and change the headline, colours and times.

## Input

- The subject, e.g. a neuron, lightning, a network or roots.
- A Hebrew headline of 2 to 5 words.
- Glow colours. Default: purple `#8B5CF6` and blue `#3B82F6` with a yellow spark `#FDE047`, on dark blue `#070B1A`.
- Length (6 to 12 seconds, default 9) and size (default 1080x1920).

## Direction

- Branches that grow like a neuron or lightning: one line that splits again and again and stretches in soft curves.
- Around every line there is a glow: several thick transparent layers under a thin bright line.
- A yellow spark (in code: the pulse) runs along the branch and lights up the next node.
- Fine rain or dust in the background, for depth.
- The central node is in the upper half of the frame. When the light reaches it, an `F.D` 900 headline enters below it, word by word, with a soft dark patch behind it (in code: the plate). The branches keep away from the headline area.
- The second lightning is a real, jagged bolt, far behind the neuron.
- **Forbidden:** more than three strong flashes per second, rainbow colours, blur filters on large elements, a hyphen between two words.

## Structure

Darkness → a point of light → a main branch grows → branching → a light pulse runs → the node flares → a second lightning lights the background for a moment → the headline enters → everything breathes with glow until the end (the headline on screen at least 1.5 seconds).

Tested timing for 6 seconds: point of light 0.1, growth 0.15 to 2.6, pulse 2.55 to 3.05, flare 3.05, headline from 3.15, second lightning 3.85. For another length, in the same ratio.

## Layout (1080 wide, tested)

- **The node** at `[W/2, 0.30 * H]`.
- **The headline** in two lines, below the node (the first line's centre about 330 px below it). Each line `fit` to at most **half the frame** width (and no more than 150 px). Narrow lines leave corridors for the roots on both sides.
- **The plate** is an ellipse around the headline: `rx = line width / 2 + 80`, `ry = both lines / 2 + 70`.
- **Soft walls:** 90 px from the sides and 130 from the top and bottom. That's a 60 margin, plus room for the camera push (6 percent of the distance from the centre). At 1080 wide this leaves a corridor of about 100 px between the plate and the wall on each side.
- **The meeting point** M in the centre, about 190 px below the plate.

## Build

- `canvas2d` for the branches, pulses and rain, inside a camera (a `div` that also contains the plate and the headline). Above them a static grain layer.
- **The walk (at build time, with `rng(seed)`):** every branch is a walk in 9 px steps. At each step the new direction is the sum of:
  - the current direction;
  - **pull toward a target point** (attractor). A main branch gets a list of points (guide path) and moves to the next when it is within 60 of it;
  - a weak pull back toward its original direction, so the branches fan out and don't curl;
  - **gravity:** positive for roots (down), slightly negative for dendrites (up);
  - **repulsion from the plate:** when the branch is inside the ellipse scaled by 1.25, a push outward along the normal, stronger the deeper it is. Inside the ellipse itself the branch stops;
  - **repulsion from the soft walls**, and stopping 30 to 40 px past the wall;
  - a small deviation from `vnoise`.

  Then smoothing: `d = norm(0.7 * d + 0.3 * new)`.
- **Dendrites:** 6 main branches from the node upward, each to its own point in the upper band (x from 0.14W to 0.86W, y from 0.07H to 0.14H). Each has children on two levels: spawning every 60 to 110 px with probability 0.55, at an angle of 20 to 35 degrees, with a length of 45 to 65 percent of what remains for the parent.
- **Two roots:** from the node downward, one on each side, through points in the middle of the corridor (`PL.cx ± (PL.rx + 0.5 * gap)` at the plate's height, plus one above it and one below), then to M. When the root is within 45 px of M it finishes exactly at M and stops. Otherwise it circles M in loops.
- **Below the meeting point:** a short trunk from M downward, and 5 roots spreading from it into the lower band, with children. They start growing only once the roots have reached M.
- **One growth clock with easing:** each branch stores its distance from the node along the tree (`t0`). The clock is `tau = tauMax * E.o3(seg(t, T0, T1))`, and the drawn length of a branch is `tau - t0`. That way children start exactly when the parent passes the split point, and the whole tree accelerates and settles together. Not linear growth (principles.md section 2). `E.o3` and not `E.io3`: a fast start, so there's no dead opening.
- **Measurements with `report()`:** `report('growthEnd', T1)`, `report('treeBounds', [...])`, `report('corridor', gap)`. `render.py check` and `stills` print them. Not `console.log` and not `console.warn` (the check counts a warn as a problem).
- **Glow, about 10 layers** with `g.globalCompositeOperation = 'lighter'`, from thick to thin: width 64, 44, 30, 21, 14, 9, 6, 3.6, 2.2, 1.3, and opacity 0.018, 0.026, 0.036, 0.05, 0.07, 0.1, 0.15, 0.26, 0.5, 0.9. The outer ones purple, the middle ones blue, and the core almost white. Round `lineCap` and `lineJoin`.
- **One path per layer and per depth:** in each layer, all branches of the same depth go into one `beginPath` (each branch as a subpath) and one `stroke`. Width by depth: 1, 0.62, 0.42. That way there are no overlaps within the same layer.
- **Pulse:** along the longest dendrite, from the tip inward to the node: `s = len * (1 - E.io3(seg(t, a, b)))`, 8 small yellow halos whose trail shortens. When it arrives, the node flares: a halo that grows on `S(t - ta, 20, 0.6)` and fades.
- **Second lightning:** a jagged polyline from `rng`, in the upper corner, thin and dim, 0.15 seconds, and at the same moment the background brightens a little (a rectangle in the glow colour at 0.1 opacity that fades). That's one flash.
- **Flicker:** `hash(Math.round(t * 60))`, the displayed frame number, so it's identical across all sub-frames. Not `Math.random`.
- **Dust:** 150 to 300 points. `x = hash(i) * W`, `y = (hash(i + 99) * H + t * v_i) % H`. No state.
- **Headline plate:** an elliptical `radial-gradient` with **25 stops** (opacity by `1 - E.smooth(u)`), and on top of everything a subtle static grain layer (a `canvas2d` filled once with noise, alpha about 10 out of 255). The headline in a `row` per line, word by word with `rise`. Breathing: the glow rises and falls by `0.85 + 0.15 * sin(2 * PI * 0.5 * t)`.
- **Camera:** a slow pull back over the whole video (`s` from 1.06 to 1 on `E.o2`). Without it, the end of the growth looks like a frozen picture, and `check` flags it.
- **Flash check:** `"$PY" render.py flashcheck`. It measures the mean brightness of every frame, reports every jump over 2 percent, and fails if there are more than three per second.
- **Render:** `SUB=8` (fast motion of the pulse and lightning).
- **Sound:** `rise` at the start of growth, a short `glitch` on the pulse, `impact` on the flare, `sub` on the second lightning, `hit` on every headline word.
- **stills:** 1.6, 2.6, 3.1, 3.9, 4.5 (scaled to the length).

## Pitfalls

- **Roots outside the frame:** "a branch fanning out with a pull back" without target points sends roots out of the frame. Roots need a guide path, and the whole tree needs soft walls.
- **"Deflecting or cutting" branches near the headline** creates an artificial rounded rectangular hole. Soft repulsion from an ellipse, and roots that pass through corridors and meet below, look natural.
- **6 glow layers** show contour bands. About 10 layers with a gradual transition in width and opacity.
- **Tapering a branch in pieces** (each piece a separate `stroke` with a different width) creates bright spots where pieces overlap, because `lighter` adds them twice. Draw each branch as one continuous path in each layer. Tapering: by depth (a child branch is thinner), or `createLinearGradient` for opacity along the branch.
- **A radial gradient with few stops** shows rings on a dark background. 20 stops or more, and a subtle static grain layer on top.
- Flicker only from a `hash` of the displayed frame number.
- Too strong a glow burns out the headline. A soft dark plate behind it, and the branches keep away from it.
- `lighter` over many layers reaches white fast. If the core of the branches is fully white, lower the opacity of the thick layers.
- Fonts load from local files and core.js waits for them before the first frame.

## Approval list

The list of stages with times, the headline (how it splits into two lines), the colours, and what the subject looks like (how many branches, where the node is, where the roots meet).
