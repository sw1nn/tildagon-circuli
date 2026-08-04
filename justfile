# Circuli development tasks. Everything here runs under plain CPython.

_default:
    @just --list

# Run the full test suite (game logic, catalogue, motion input, offline analysis).
test:
    python -m unittest discover --pattern 'test_*.py'

# Regenerate the level catalogue in assets/ (offline exhaustive search).
gen-levels seed="2026":
    python tools/generate_catalogue.py {{ seed }}

# The version comes from conventional commits; the cog.toml hooks lint, test,
# stamp tildagon.toml/metadata.json, push the tag, and publish the GitHub
# release.
# Cut a release via cocogitto (level: auto, patch, minor or major).
release level="auto":
    cog bump --{{ level }}
