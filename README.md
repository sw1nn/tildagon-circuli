# Circuli

A ring puzzle for the [Tildagon](https://github.com/emfcamp/badge-2024-software)
badge. Concentric rings carry interlocking teeth; rotating one ring can catch
and drag its neighbours. Line up every ring's alignment marker with the target
at the top to solve it.

Every puzzle has a freshly randomised teeth layout (1–3 teeth per rim on each
gap between rings), scrambled by a random walk that is solvable by
construction. You start at 3 rings; each solved puzzle adds a ring, up to 5.
Progress resets when the app restarts. Dim glyphs at the display edge remind
you what the game buttons do.

## Controls

| Button | Action |
|---|---|
| C (bottom-right) | Rotate the selected ring clockwise |
| E (bottom-left) | Rotate the selected ring anticlockwise |
| A / D (top / bottom) | Select the next ring outward / inward |
| B (top-right) | New puzzle — advances to the next level on a solved board; asks for confirmation mid-game |
| F (top-left) | Exit to launcher |

In the new-puzzle confirmation, C answers **Yes** and F answers **No**, as
labelled on screen.

## How the rings catch

Each ring has teeth on its inner and outer rims. When a rotating ring's tooth
would move into a slot occupied by a neighbour's opposing tooth, it pushes that
neighbour the same direction instead — and the push cascades. Turning back the
other way separates them.

## Structure

- `game.py` — pure game logic (rings, teeth, the coupling rule, solvability). No
  display or hardware imports, so it runs and tests under plain CPython.
- `test_game.py` — unit tests for the logic: `python -m unittest test_game`.
- `app.py` — the `Circuli` app: input handling and `ctx` rendering.
- `metadata.json` / `__init__.py` — Tildagon app metadata and entry point.

## Developing

From the `spaceagon` environment:

- `just sim` — run in the simulator; pick **Circuli** from the app list.
- `just deploy` — install onto a USB-connected badge.
