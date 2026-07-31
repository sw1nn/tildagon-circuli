# Circuli development tasks. Everything here runs under plain CPython.

_default:
    @just --list

# Run the full test suite (game logic, catalogue, motion input).
test:
    python -m unittest test_game test_motion

# Regenerate the level catalogue in assets/ (offline exhaustive search).
gen-levels seed="2026":
    python tools/generate_catalogue.py {{ seed }}
