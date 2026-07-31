import json
import os
import random
import unittest
from itertools import product

from game import (
    TEETH_MAX,
    TEETH_MIN,
    Game,
    Machine,
    default_machine,
    is_valid,
    random_machine,
    start_is_scrambled,
)

CATALOGUE_DIR = os.path.dirname(os.path.abspath(__file__))


def solve_distance(machine, start, limit):
    """Independent oracle: exact minimum moves from `start` to solved via
    breadth-first search over the real move set; None if deeper than
    `limit`. Used to verify the shipped catalogue distances."""
    n = machine.rings
    solved = tuple([0] * n)
    start = tuple(start)
    if start == solved:
        return 0
    seen = {start}
    frontier = [start]
    for depth in range(1, limit + 1):
        nxt = []
        for state in frontier:
            for ring in range(n):
                for d in (1, -1):
                    g = Game(machine, list(state))
                    g.rotate(ring, d)
                    t = tuple(g.positions)
                    if t == solved:
                        return depth
                    if t not in seen:
                        seen.add(t)
                        nxt.append(t)
        if not nxt:
            return None
        frontier = nxt
    return None


def load_catalogue(rings):
    with open(os.path.join(CATALOGUE_DIR, "levels_%d.json" % rings)) as f:
        return json.load(f)


def all_valid_states(machine):
    """Yield every ring-position tuple with no physically overlapping teeth."""
    for state in product(range(machine.slots), repeat=machine.rings):
        if is_valid(machine, state):
            yield state


def bare_machine():
    """Three rings, no teeth: nothing ever meshes."""
    return Machine(inner_teeth=[[], [], []], outer_teeth=[[], [], []], slots=12)


def meshing_machine():
    """Ring 0's outer tooth (slot 0) catches ring 1's inner tooth (slot 1).

    At rest they sit one slot apart; rotating ring 0 CW closes the gap and
    catches ring 1. Ring 2 has no teeth, so it never joins.
    """
    return Machine(
        inner_teeth=[[], [1], []],
        outer_teeth=[[0], [], []],
        slots=12,
    )


def cascade_machine():
    """Ring 0 catches ring 1 (outer 0 -> inner 1), and ring 1 catches ring 2
    (outer 1 -> inner 2), so a single push of ring 0 ripples to ring 2."""
    return Machine(
        inner_teeth=[[], [1], [2]],
        outer_teeth=[[0], [1], []],
        slots=12,
    )


class RotateTest(unittest.TestCase):
    def test_rotate_with_no_meshing_moves_only_driven_ring(self):
        game = Game(bare_machine(), positions=[0, 0, 0])
        game.rotate(0, +1)
        self.assertEqual(game.positions, [1, 0, 0])

    def test_rotating_into_a_neighbours_tooth_drags_it_same_direction(self):
        game = Game(meshing_machine(), positions=[0, 0, 0])
        game.rotate(0, +1)
        self.assertEqual(game.positions, [1, 1, 0])

    def test_push_cascades_through_to_a_third_ring(self):
        game = Game(cascade_machine(), positions=[0, 0, 0])
        game.rotate(0, +1)
        self.assertEqual(game.positions, [1, 1, 1])

    def test_rotating_away_from_a_tooth_does_not_catch(self):
        # meshing_machine catches on CW; a CCW turn of ring 0 opens the gap.
        game = Game(meshing_machine(), positions=[0, 0, 0])
        game.rotate(0, -1)
        self.assertEqual(game.positions, [11, 0, 0])

    def test_rotating_outer_ring_pushes_inner_neighbour(self):
        # Ring 1's inner tooth (slot 1) turned CCW lands on ring 0's outer tooth
        # (slot 0), dragging ring 0 CCW too. Contact works outer -> inner as well.
        game = Game(meshing_machine(), positions=[0, 0, 0])
        game.rotate(1, -1)
        self.assertEqual(game.positions, [11, 11, 0])


class DrivenRingInvariantTest(unittest.TestCase):
    """Whatever the interlocking drags along, the driven ring itself must move
    exactly one slot in the requested direction: CW takes it from N to
    (N + 1) % slots, CCW from N to (N - 1) % slots. Exhaustive over every
    valid state, ring, and direction."""

    def assert_driven_ring_moves_one_slot(self, machine):
        s = machine.slots
        for state in all_valid_states(machine):
            for ring in range(machine.rings):
                for direction in (+1, -1):
                    game = Game(machine, list(state))
                    game.rotate(ring, direction)
                    expected = (state[ring] + direction) % s
                    self.assertEqual(
                        game.positions[ring],
                        expected,
                        "ring %d driven %+d from %r landed on %d, expected %d"
                        % (ring, direction, state, game.positions[ring], expected),
                    )

    def test_default_machine_driven_ring_always_moves_one_slot(self):
        self.assert_driven_ring_moves_one_slot(default_machine())

    def test_meshing_machine_driven_ring_always_moves_one_slot(self):
        self.assert_driven_ring_moves_one_slot(meshing_machine())

    def test_cascade_machine_driven_ring_always_moves_one_slot(self):
        self.assert_driven_ring_moves_one_slot(cascade_machine())

    def test_cw_wraps_from_last_slot_to_zero(self):
        game = Game(bare_machine(), positions=[11, 0, 0])
        game.rotate(0, +1)
        self.assertEqual(game.positions[0], 0)

    def test_ccw_wraps_from_zero_to_last_slot(self):
        game = Game(bare_machine(), positions=[0, 0, 0])
        game.rotate(0, -1)
        self.assertEqual(game.positions[0], 11)


class SolvedTest(unittest.TestCase):
    def test_all_markers_at_top_is_solved(self):
        self.assertTrue(Game(bare_machine(), positions=[0, 0, 0]).is_solved())

    def test_any_ring_off_top_is_not_solved(self):
        self.assertFalse(Game(bare_machine(), positions=[0, 1, 0]).is_solved())


class RandomMachineTest(unittest.TestCase):
    def test_random_machines_are_valid_at_rest_with_bounded_teeth(self):
        for rings in (3, 4, 5):
            for seed in range(30):
                rng = random.Random(seed)
                m = random_machine(rng, rings)
                self.assertEqual(m.rings, rings)
                self.assertEqual(m.slots, 12)
                # Decorative rims carry no teeth.
                self.assertEqual(m.inner_teeth[0], [])
                self.assertEqual(m.outer_teeth[-1], [])
                # The solved state must be physically possible.
                self.assertTrue(is_valid(m, [0] * rings))
                for gap in range(rings - 1):
                    outer = m.outer_teeth[gap]
                    inner = m.inner_teeth[gap + 1]
                    self.assertTrue(TEETH_MIN <= len(outer) <= TEETH_MAX)
                    self.assertTrue(TEETH_MIN <= len(inner) <= TEETH_MAX)
                    combined = outer + inner
                    self.assertEqual(
                        len(combined),
                        len(set(combined)),
                        "gap %d shares a slot: %r" % (gap, combined),
                    )
                    for t in combined:
                        self.assertTrue(0 <= t < m.slots)


class CatalogueTest(unittest.TestCase):
    def test_catalogue_entries_are_valid_and_scrambled(self):
        for rings in (3, 4, 5):
            cat = load_catalogue(rings)
            self.assertEqual(cat["rings"], rings)
            self.assertTrue(cat["puzzles"])
            for p in cat["puzzles"]:
                m = Machine(p["inner"], p["outer"], cat["slots"])
                self.assertEqual(m.rings, rings)
                self.assertTrue(is_valid(m, [0] * rings))
                self.assertTrue(is_valid(m, p["start"]))
                self.assertTrue(start_is_scrambled(p["start"]))
                self.assertGreater(p["dist"], 0)

    def test_catalogue_distances_are_exact_for_three_rings(self):
        # Every shipped 3-ring puzzle re-verified against the BFS oracle.
        cat = load_catalogue(3)
        for p in cat["puzzles"]:
            m = Machine(p["inner"], p["outer"], cat["slots"])
            self.assertEqual(solve_distance(m, p["start"], p["dist"]), p["dist"])

    def test_catalogue_distances_spot_checked_for_higher_rings(self):
        # Full re-verification is slow at 4-5 rings; spot-check a sample.
        for rings, samples in ((4, 4), (5, 2)):
            cat = load_catalogue(rings)
            rng = random.Random(rings)
            for _ in range(samples):
                p = cat["puzzles"][rng.randrange(len(cat["puzzles"]))]
                m = Machine(p["inner"], p["outer"], cat["slots"])
                self.assertEqual(
                    solve_distance(m, p["start"], p["dist"]), p["dist"]
                )


class InvertibilityTest(unittest.TestCase):
    def test_counter_rotating_the_same_ring_undoes_a_catchless_move(self):
        # With no cascade, rotate then counter-rotate is a clean round trip.
        game = Game(bare_machine(), positions=[3, 5, 7])
        game.rotate(1, +1)
        game.rotate(1, -1)
        self.assertEqual(game.positions, [3, 5, 7])

    def test_counter_rotating_does_not_undo_a_cascading_move(self):
        # Documents that atomic moves are NOT invertible once a catch drags
        # neighbours: turning ring 0 back CCW separates from ring 1 instead of
        # dragging it home. This is why scramble must verify reachability, not
        # assume reversibility.
        game = Game(cascade_machine(), positions=[0, 0, 0])
        game.rotate(0, +1)
        self.assertEqual(game.positions, [1, 1, 1])
        game.rotate(0, -1)
        self.assertNotEqual(game.positions, [0, 0, 0])


if __name__ == "__main__":
    unittest.main()
