import random
import unittest

from game import Game, Machine, default_machine, is_valid


def reaches_solved(machine, start):
    """Independent oracle: breadth-first search from `start` to the solved
    (all-zero) state over the real move set. Used to verify scramble output."""
    n = machine.rings
    solved = tuple([0] * n)
    seen = set()
    seen.add(tuple(start))
    frontier = [tuple(start)]
    while frontier:
        nxt = []
        for state in frontier:
            if state == solved:
                return True
            for ring in range(n):
                for d in (1, -1):
                    g = Game(machine, list(state))
                    g.rotate(ring, d)
                    t = tuple(g.positions)
                    if t not in seen:
                        seen.add(t)
                        nxt.append(t)
        frontier = nxt
    return False


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


class SolvedTest(unittest.TestCase):
    def test_all_markers_at_top_is_solved(self):
        self.assertTrue(Game(bare_machine(), positions=[0, 0, 0]).is_solved())

    def test_any_ring_off_top_is_not_solved(self):
        self.assertFalse(Game(bare_machine(), positions=[0, 1, 0]).is_solved())


class ScrambleTest(unittest.TestCase):
    def test_scramble_is_never_already_solved(self):
        machine = default_machine()
        for seed in range(25):
            game = Game(machine)
            game.scramble(random.Random(seed))
            self.assertFalse(game.is_solved(), "seed %d produced a solved start" % seed)

    def test_scramble_is_always_solvable(self):
        machine = default_machine()
        for seed in range(25):
            game = Game(machine)
            game.scramble(random.Random(seed))
            self.assertTrue(
                reaches_solved(machine, game.positions),
                "seed %d produced an unsolvable start: %r" % (seed, game.positions),
            )

    def test_scramble_never_starts_in_an_overlapping_state(self):
        machine = default_machine()
        for seed in range(40):
            game = Game(machine)
            game.scramble(random.Random(seed))
            self.assertTrue(
                is_valid(machine, game.positions),
                "seed %d produced overlapping teeth: %r" % (seed, game.positions),
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
