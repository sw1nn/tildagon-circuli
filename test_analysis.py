import random
import unittest

from game import Game, Machine, random_legal_move
from tools.analysis import (
    best_greedy_cost,
    build_predecessors,
    distance_map,
    doomed_states,
    encode,
    greedy_cost,
    is_dead_end_free,
)


def free_chain():
    """Ring 0 catches ring 1, which catches ring 2."""
    return Machine(
        inner_teeth=[[], [1], [2]],
        outer_teeth=[[0], [1], []],
        slots=12,
    )


def binding_pair():
    """One shared gap with two points of contact: the catching pair (slots
    0/1) closes safely under counter-rotation, but the second pair (slots
    5/7) closes onto the same slot once ring 1 turns the other way, so
    `_apply` refuses the move outright. This is the source of genuine jams
    and doomed states now that rings no longer ratchet."""
    return Machine(
        inner_teeth=[[], [1, 7]],
        outer_teeth=[[0, 5], []],
        slots=12,
    )


class DistanceMapTest(unittest.TestCase):
    def test_solved_state_is_distance_zero(self):
        dist = distance_map(free_chain())
        self.assertEqual(dist[0], 0)

    def test_jammed_moves_create_no_edges(self):
        machine = binding_pair()
        preds = build_predecessors(machine)
        for code, bucket in enumerate(preds):
            if bucket:
                self.assertNotIn(code, bucket)


class DeadEndTest(unittest.TestCase):
    def test_a_fully_reversible_machine_has_no_doomed_states(self):
        machine = free_chain()
        dist = distance_map(machine)
        self.assertEqual(doomed_states(machine, dist), set())

    def test_a_safe_state_reports_dead_end_free(self):
        machine = free_chain()
        dist = distance_map(machine)
        doomed = doomed_states(machine, dist)
        self.assertTrue(is_dead_end_free(encode((1, 1, 1), 12), 12, doomed))


class GreedyTest(unittest.TestCase):
    def test_a_free_machine_with_no_teeth_costs_the_obvious_sweep(self):
        machine = Machine(inner_teeth=[[], []], outer_teeth=[[], []], slots=12)
        # Rings at 1 and 2, shortest way round for each: 1 + 2 moves.
        self.assertEqual(greedy_cost(machine, (1, 2), "inner-out", 0), 3)

    def test_best_greedy_cost_takes_the_cheapest_variant(self):
        machine = Machine(inner_teeth=[[], []], outer_teeth=[[], []], slots=12)
        best = best_greedy_cost(machine, (1, 11))
        self.assertEqual(best, 2)

    def test_an_already_solved_start_costs_nothing(self):
        self.assertEqual(best_greedy_cost(free_chain(), (0, 0, 0)), 0)

    def test_a_sweep_that_jams_reports_failure(self):
        # Both rings start on the same slot: driving ring 0 toward solved
        # immediately closes the second contact pair onto itself, and every
        # sweep variant runs into the same binding.
        self.assertIsNone(best_greedy_cost(binding_pair(), (5, 5)))


class LegalChurnTest(unittest.TestCase):
    """The vortex burst draws any non-jamming move and relies on the puzzle
    being dead-end-free. Verified here against the exact distance map rather
    than a bounded search, because a directed move graph gives no bound on how
    far one move can push the distance."""

    def test_churning_a_safe_state_never_leaves_the_distance_map(self):
        machine = free_chain()
        dist = distance_map(machine)
        doomed = doomed_states(machine, dist)
        self.assertEqual(doomed, set())
        rng = random.Random(5)
        game = Game(machine, [3, 4, 5])
        for _ in range(40):
            move = random_legal_move(machine, game.positions, rng)
            self.assertIsNotNone(move)
            self.assertTrue(game.rotate(move[0], move[1]))
            self.assertIn(encode(tuple(game.positions), 12), dist)


if __name__ == "__main__":
    unittest.main()
