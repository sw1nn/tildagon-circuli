"""Audits the shipped catalogues against the guarantees the app relies on.

Slow by nature: the checks walk whole state spaces. Base tiers are audited
exhaustively where affordable and sampled above that, matching the existing
distance spot-check strategy.
"""

import os
import random
import unittest

from game import Machine, catalogue_entry, catalogue_info
from tools.analysis import (
    best_greedy_cost,
    build_predecessors,
    distance_map,
    doomed_states,
    is_dead_end_free,
)
from tools.generate_catalogue import GREEDY_RATIO

CATALOGUE_DIR = os.path.dirname(os.path.abspath(__file__))


def load(rings):
    path = os.path.join(CATALOGUE_DIR, "assets", f"levels_{rings}.lvl")
    with open(path, "rb") as f:
        data = f.read()
    slots, _rings, count = catalogue_info(data)
    puzzles = []
    for i in range(count):
        inner, outer, start, dist, split = catalogue_entry(data, i)
        puzzles.append(
            {
                "inner": inner,
                "outer": outer,
                "start": start,
                "dist": dist,
                "split": split,
            }
        )
    return slots, puzzles


def halves(puzzle, slots):
    """A composite's two independent machines with their own starts."""
    k = puzzle["split"]
    a = Machine(puzzle["inner"][:k], puzzle["outer"][:k], slots)
    b = Machine(puzzle["inner"][k:], puzzle["outer"][k:], slots)
    return (a, puzzle["start"][:k]), (b, puzzle["start"][k:])


def assert_safe_and_resistant(case, machine, start, dist_recorded):
    preds = build_predecessors(machine)
    dist = distance_map(machine, preds)
    doomed = doomed_states(machine, dist, preds)
    case.assertTrue(
        is_dead_end_free(tuple(start), machine.slots, doomed),
        f"start {start!r} can be stranded",
    )
    greedy = best_greedy_cost(machine, start)
    if greedy is not None:
        case.assertGreaterEqual(
            greedy,
            GREEDY_RATIO * dist_recorded,
            f"greedy solves {start!r} in {greedy} against optimal {dist_recorded}",
        )


class BaseTierAuditTest(unittest.TestCase):
    def test_three_ring_tier_is_fully_audited(self):
        slots, puzzles = load(3)
        for p in puzzles:
            machine = Machine(p["inner"], p["outer"], slots)
            assert_safe_and_resistant(self, machine, p["start"], p["dist"])

    def test_higher_base_tiers_are_sampled(self):
        for rings, samples in ((4, 4), (5, 2)):
            slots, puzzles = load(rings)
            rng = random.Random(rings)
            for _ in range(samples):
                p = puzzles[rng.randrange(len(puzzles))]
                machine = Machine(p["inner"], p["outer"], slots)
                assert_safe_and_resistant(self, machine, p["start"], p["dist"])


class CompositeAuditTest(unittest.TestCase):
    def test_composite_halves_are_safe_and_resistant(self):
        for rings in (6, 7, 8):
            slots, puzzles = load(rings)
            rng = random.Random(rings * 3)
            for _ in range(2):
                p = puzzles[rng.randrange(len(puzzles))]
                for machine, start in halves(p, slots):
                    preds = build_predecessors(machine)
                    dist = distance_map(machine, preds)
                    doomed = doomed_states(machine, dist, preds)
                    self.assertTrue(
                        is_dead_end_free(tuple(start), slots, doomed),
                        f"rings {rings} half start {start!r} can be stranded",
                    )


if __name__ == "__main__":
    unittest.main()
