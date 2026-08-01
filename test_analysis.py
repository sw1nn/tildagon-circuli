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
    """Ring 0 catches ring 1, which catches ring 2. No ratchets."""
    return Machine(
        inner_teeth=[[], [1], [2]],
        outer_teeth=[[0], [1], []],
        slots=12,
    )


def one_way_chain():
    """free_chain with ring 1 clockwise-only, so some pushes jam."""
    return Machine(
        inner_teeth=[[], [1], [2]],
        outer_teeth=[[0], [1], []],
        slots=12,
        ratchet=[0, +1, 0],
    )


def lone_ratchet():
    """A single-gap machine with no teeth and one clockwise-only ring: the
    only route home for ring 1 is the long way round."""
    return Machine(
        inner_teeth=[[], []],
        outer_teeth=[[], []],
        slots=12,
        ratchet=[0, +1],
    )


def deadlocked_pair():
    """One shared gap, ratcheted in opposing directions: ring 0 clockwise-
    only, ring 1 counter-clockwise-only. Once the pair catches, neither
    ratchet's permitted direction can separate them again, so most states
    are doomed."""
    return Machine(
        inner_teeth=[[], [1]],
        outer_teeth=[[0], []],
        slots=12,
        ratchet=[+1, -1],
    )


class DistanceMapTest(unittest.TestCase):
    def test_solved_state_is_distance_zero(self):
        dist = distance_map(free_chain())
        self.assertEqual(dist[0], 0)

    def test_distances_agree_with_a_hand_computed_case(self):
        # No teeth: each ring moves alone, ring 0 is free, ring 1 is CW-only.
        # From [0, 1] ring 1 needs 11 clockwise steps to wrap back to 0.
        machine = lone_ratchet()
        dist = distance_map(machine)
        self.assertEqual(dist[encode((0, 1), 12)], 11)
        self.assertEqual(dist[encode((1, 0), 12)], 1)

    def test_jammed_moves_create_no_edges(self):
        machine = one_way_chain()
        preds = build_predecessors(machine)
        for code, bucket in enumerate(preds):
            if bucket:
                self.assertNotIn(code, bucket)


class DeadEndTest(unittest.TestCase):
    def test_a_fully_reversible_machine_has_no_doomed_states(self):
        machine = free_chain()
        dist = distance_map(machine)
        self.assertEqual(doomed_states(machine, dist), set())

    def test_a_lone_one_way_ratchet_never_creates_a_dead_end(self):
        # A single ratcheted ring can always be driven the long way round in
        # its own permitted direction, so nothing traps it: verified here
        # rather than assumed, since a chain with only one ratchet turns out
        # to produce zero doomed states.
        machine = one_way_chain()
        dist = distance_map(machine)
        self.assertEqual(doomed_states(machine, dist), set())

    def test_doomed_states_form_a_closed_set_under_legal_moves(self):
        # Every doomed state is either itself a genuine trap (outside dist,
        # so it can never reach solved), or has at least one legal move into
        # another doomed state. This is the closure the reverse BFS in
        # doomed_states is supposed to establish; re-checked here directly
        # against build_predecessors rather than trusting doomed_states'
        # own bookkeeping.
        machine = deadlocked_pair()
        dist = distance_map(machine)
        preds = build_predecessors(machine)
        doomed = doomed_states(machine, dist, preds)
        self.assertTrue(doomed)
        for code in doomed:
            if code not in dist:
                continue
            reaches_another_doomed_state = any(
                other in doomed and bucket and code in bucket
                for other, bucket in enumerate(preds)
                if other != code
            )
            self.assertTrue(reaches_another_doomed_state)

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

    def test_a_ratcheted_ring_must_go_the_long_way_round(self):
        # Ring 1 is clockwise-only and sits one slot clockwise of solved, so
        # the sweep pays 11 moves instead of 1.
        self.assertEqual(greedy_cost(lone_ratchet(), (0, 1), "inner-out", 0), 11)

    def test_the_mode_collapses_to_the_permitted_direction(self):
        # Asking for counter-clockwise on a clockwise-only ring must not jam;
        # the bot uses the ring's own direction instead.
        self.assertEqual(greedy_cost(lone_ratchet(), (0, 1), "inner-out", -1), 11)

    def test_best_greedy_cost_takes_the_cheapest_variant(self):
        machine = Machine(inner_teeth=[[], []], outer_teeth=[[], []], slots=12)
        best = best_greedy_cost(machine, (1, 11))
        self.assertEqual(best, 2)

    def test_an_already_solved_start_costs_nothing(self):
        self.assertEqual(best_greedy_cost(free_chain(), (0, 0, 0)), 0)

    def test_a_sweep_that_jams_reports_failure(self):
        # Both rings start on the same slot: the very first move drags the
        # other ring's ratchet the wrong way and _apply refuses it outright.
        self.assertIsNone(best_greedy_cost(deadlocked_pair(), (5, 5)))


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
