# Circles

An example [Tildagon](https://github.com/emfcamp/badge-2024-software) badge app.
It draws three concentric circles centred on the display and exits to the
launcher when the **CANCEL** button is pressed.

## Structure

- `metadata.json` — Tildagon app metadata.
- `__init__.py` — re-exports the `Circles` app class.
- `app.py` — the `Circles` app: an `app.App` subclass with `update` and `draw`.

## Running

This app is developed inside the `spaceagon` environment, which provides the
simulator and badge tooling. From the `spaceagon` repo root:

- `just sim` — run in the simulator.
- `just deploy` — install onto a USB-connected badge.
