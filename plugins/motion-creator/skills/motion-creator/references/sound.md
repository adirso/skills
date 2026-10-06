# Sound

## The rules

- **No sound files in the skill.** Every effect is synthesised with numpy inside `audio.py`, at render time.
- **Music only from the user.** The skill doesn't download songs. The user brings a file they are allowed to use. Recommendation: Mixkit (mixkit.co), whose free license allows commercial use without credit. Songs from streaming services or YouTube are not allowed.
- The master comes out at `-14 LUFS` (the social media level), with a peak of `-1 dBTP` at most.

## Default: effects only

At scene build time call `sfx(t, kind, gain)`. The time is the moment the picture happens (the slam starts, the button is pressed), not before it.

| Kind | Sound | When |
|---|---|---|
| `click` | UI click | A cursor press, a switch |
| `tick` | Small tick | A small change, a transition between states |
| `count` | Tiny tick | A number counter, several in a row |
| `key` | Key | Every character while typing (gain 0.5) |
| `pop` / `popHi` | Pop | An element popping in, a bubble |
| `hit` | Short hit | A word slams, a cut on the beat |
| `impact` | Big hit | One or two peak moments |
| `sub` | Deep boom | At most once per scene |
| `thud` | Soft thud | A landing, a ball hitting |
| `whoosh` / `swish` | Air | A big transition. **At most once per scene**, and deliberately quieter than the hits |
| `rise` | Riser | A build before a peak moment |
| `ding` / `chime` / `success` | Chime | Success, notification, ending |
| `sparkle` | Sparkle | A logo or word reveal |
| `glitch` | Glitch | A digital break |
| `shutter` | Shutter | A picture captured, a selection locked |
| `boing` | Spring | A character jumping, cartoon |

- 2 to 6 effects per scene, only on peak moments. Sound on every move sounds like a kids' game.
- `gain` between 0.3 and 1 grades effects of the same kind (the first loud, the rest quieter).
- To hear all the kinds in a row: `"$PY" audio.py demo` creates `out/sfx-demo.wav`.
- A new kind: add a branch in `make()` and a level in `LEVEL` inside `audio.py`.

## With the user's song

1. The user puts the file in the project folder (or gives a path, and you copy it there).
2. Measure the tempo:
   ```bash
   "$PY" audio.py beat music.mp3
   ```
   Output: BPM, the first beat, and the first bar (downbeat).
3. In `CONFIG`:
   ```js
   bpm: 120, beat0: 0,
   music: { file: 'music.mp3', start: 13.357, gain: 0 },
   ```
   `start` is a downbeat in the song (the moment the animation starts). `beat0: 0` because the video starts exactly on it. `gain` is in decibels.
4. In the scene use `beat(n)` for all timing, and `sfx(beat(n), 'click')` for UI sounds.
5. `audio.py` shifts each effect up to 25 ms toward the nearest peak in the song, so it sits on the measured beat. `snap: false` in CONFIG disables this.

Length: `DUR` should be a whole number of bars (at 120 BPM, a bar is 2 seconds). In a loop it is required.

## How loud

`LEVEL` in `audio.py` sets each kind relative to the song's loudness (or to a fixed reference level when there is no song). If something sticks out, change the call's gain, not LEVEL.
