# Circuli

A ring puzzle for the [Tildagon](https://github.com/emfcamp/badge-2024-software) badge. Concentric rings carry interlocking teeth; rotating one ring can catch and drag its neighbours. Line up every ring's alignment marker with the target at the top to solve it.

Puzzles come from a pre-generated level catalogue: random teeth layouts whose solvability and exact minimum solve distance are verified offline by exhaustive search (see `tools/generate_catalogue.py`), so every start is guaranteed solvable and properly hard for its tier. You start at 3 rings; solving a puzzle sweeps the badge LEDs once around the hexagon, then automatically advances to the next level, up to 8 rings. The LEDs then show a steady tally — one lit LED per puzzle solved this session. Progress resets when the app restarts. Glyphs on tabs at the display edge remind you what the game buttons do.

An instruction page opens when the app starts, followed by a control chooser: **C** plays with buttons, **E** plays _MOTU_ — flick the badge sharply like a dial to turn the selected ring one slot, and tilt-flick it away/toward you to select rings. Slow movements never register, so you can reposition the badge freely between flicks. Buttons stay live in MOTU mode as backup.

Something lives in the gap at the centre of the rings. Players who lean on the same button will meet it. Don't make it angry.

## Controls

| Button               | Action                                           |
| -------------------- | ------------------------------------------------ |
| C (bottom-right)     | Rotate the selected ring clockwise               |
| E (bottom-left)      | Rotate the selected ring anticlockwise           |
| A / D (top / bottom) | Select the next ring outward / inward            |
| B (top-right)        | Game menu: new puzzle, reset level, restart game |
| F (top-left)         | Exit to launcher                                 |

The game menu (_QUID NUNC?_) offers **C** NOVUM — a fresh puzzle at the current level, **A** ITERUM — this puzzle back to its starting scramble, and **E** AB INITIO — restart at 3 rings with the tally cleared; **F** backs out. On a solved board B skips the victory sweep and advances immediately.

## How the rings catch

Each ring has teeth on its inner and outer rims. When a rotating ring's tooth would move into a slot occupied by a neighbour's opposing tooth, it pushes that neighbour the same direction instead — and the push cascades. Turning back the other way separates them.

## Structure

- `game.py` — pure game logic (rings, teeth, the coupling rule) and the catalogue decoder. No display or hardware imports, so it runs and tests under plain CPython.
- `motion.py` — pure MOTU input logic: the flick detector that turns gyro samples into ring turns and selection steps.
- `assets/levels_<n>.lvl` — the binary level catalogue for `n` rings: fixed-size records of teeth bitmasks, start position, and exact minimum solve distance (format documented beside the decoder in `game.py`).
- `tools/generate_catalogue.py` — offline (CPython-only) catalogue generator: exhaustively distance-maps random machines by reverse breadth-first search and harvests the hardest properly-scrambled starts. Regenerate with `just gen-levels` (or `python tools/generate_catalogue.py [seed]`).
- `test_game.py` / `test_motion.py` — unit tests for the logic, the shipped catalogue, and the motion input: `just test` (or `python -m unittest test_game test_motion`).
- `app.py` — the `Circuli` app: input handling, `ctx` rendering, LEDs.
- `metadata.json` / `__init__.py` — Tildagon app metadata and entry point.

## The name

_Circuli_ is Latin — the plural of _circulus_, "small circle" or "ring" — and the victory screen's CIRCULI COMPLETI is elliptical dog-Latin for "the rings are complete". A proper Roman would probably have written _circuli perfecti_; corrections from passing classicists are welcome and will be graded.

A note for Italian players: yes, we know the name appears to contain _culi_, and that the victory screen can therefore be read as proudly announcing "complete arses". This was entirely unintentional, may nevertheless be the most honest review this puzzle will ever receive, and we apologise for absolutely nothing. _Buona fortuna._
