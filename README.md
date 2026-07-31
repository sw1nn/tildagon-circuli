# Circuli

A ring puzzle for the [Tildagon](https://github.com/emfcamp/badge-2024-software)
badge. Concentric rings carry interlocking teeth; rotating one ring can catch
and drag its neighbours. Line up every ring's alignment marker with the target
at the top to solve it.

Puzzles come from a pre-generated level catalogue: random teeth layouts whose
solvability and exact minimum solve distance are verified offline by
exhaustive search (see `tools/generate_catalogue.py`), so every start is
guaranteed solvable and properly hard for its tier. You start at 3 rings;
solving a puzzle sweeps the badge LEDs once around the hexagon to a short
victory arpeggio, then automatically advances to the next level, up to 5
rings. The LEDs then show a steady tally — one lit LED per puzzle solved this
session. Progress resets when the app restarts. Glyphs on tabs at the display
edge remind you what the game buttons do.

## Controls

| Button | Action |
|---|---|
| C (bottom-right) | Rotate the selected ring clockwise |
| E (bottom-left) | Rotate the selected ring anticlockwise |
| A / D (top / bottom) | Select the next ring outward / inward |
| B (top-right) | New puzzle — skips the victory sweep on a solved board; asks for confirmation mid-game |
| F (top-left) | Exit to launcher |

In the new-puzzle confirmation, C answers **Yes** and F answers **No**, as
labelled on screen.

## How the rings catch

Each ring has teeth on its inner and outer rims. When a rotating ring's tooth
would move into a slot occupied by a neighbour's opposing tooth, it pushes that
neighbour the same direction instead — and the push cascades. Turning back the
other way separates them.

## Structure

- `game.py` — pure game logic (rings, teeth, the coupling rule). No display
  or hardware imports, so it runs and tests under plain CPython.
- `levels_<n>.json` — the level catalogue for `n` rings; each entry is a
  machine, a start position, and its exact minimum solve distance.
- `tools/generate_catalogue.py` — offline (CPython-only) catalogue generator:
  exhaustively distance-maps random machines by reverse breadth-first search
  and harvests the hardest properly-scrambled starts. Regenerate with
  `just gen-levels [seed]`.
- `test_game.py` — unit tests for the logic and the shipped catalogue:
  `python -m unittest test_game`.
- `app.py` — the `Circuli` app: input handling, `ctx` rendering, LEDs/sound.
- `metadata.json` / `__init__.py` — Tildagon app metadata and entry point.

## Developing

From the `spaceagon` environment:

- `just sim` — run in the simulator; pick **Circuli** from the app list.
- `just deploy` — install onto a USB-connected badge.
