import os
import random
import struct
import unittest
from itertools import product

from game import (
    CATALOGUE_MAGIC,
    TEETH_MAX,
    TEETH_MIN,
    Game,
    Machine,
    catalogue_entry,
    catalogue_info,
    default_machine,
    is_valid,
    random_legal_move,
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
    path = os.path.join(CATALOGUE_DIR, "assets", f"levels_{rings}.lvl")
    with open(path, "rb") as f:
        data = f.read()
    slots, file_rings, count = catalogue_info(data)
    puzzles = []
    for i in range(count):
        inner, outer, start, dist, split = catalogue_entry(data, i)
        entry = {
            "inner": inner,
            "outer": outer,
            "start": start,
            "dist": dist,
        }
        if split:
            entry["split"] = split
        puzzles.append(entry)
    return {"slots": slots, "rings": file_rings, "puzzles": puzzles}


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
    """Ring 0 catches ring 1 (outer 0 -> inner 1). Under the old same-direction
    rule this rippled on to ring 2 as well; under counter-rotation ring 1
    travels the *opposite* way to ring 0, so its outer tooth (slot 1) moves
    away from, not into, ring 2's inner tooth (slot 2) and the cascade stops
    at ring 1. Kept to document that change; see counter_cascade_machine for
    a cascade that does reach three rings under the new rule."""
    return Machine(
        inner_teeth=[[], [1], [2]],
        outer_teeth=[[0], [1], []],
        slots=12,
    )


def counter_cascade_machine():
    """Ring 0 catches ring 1 exactly as in cascade_machine, but ring 1's
    second outer tooth (slot 1) and ring 2's inner tooth (slot 0) are placed
    so that ring 1's *counter*-rotation (the opposite way to ring 0) is what
    reaches ring 2: signs alternate +1, -1, +1 all the way out."""
    return Machine(
        inner_teeth=[[], [1], [0]],
        outer_teeth=[[0], [1], []],
        slots=12,
    )


def binding_machine():
    """Ring 0's outer teeth and ring 1's inner teeth are one slot apart at one
    contact (slots 0 and 1: the catch that starts the cascade) and two slots
    apart at another (slots 5 and 7). Counter-rotation closes the catching
    gap safely, but the second pair closes exactly onto the same slot, so
    driving ring 0 clockwise binds and is refused."""
    return Machine(
        inner_teeth=[[], [1, 7], []],
        outer_teeth=[[0, 5], [], []],
        slots=12,
    )


class RotateTest(unittest.TestCase):
    def test_rotate_with_no_meshing_moves_only_driven_ring(self):
        game = Game(bare_machine(), positions=[0, 0, 0])
        game.rotate(0, +1)
        self.assertEqual(game.positions, [1, 0, 0])

    def test_rotating_into_a_neighbours_tooth_turns_it_the_other_way(self):
        # Ring 0's outer tooth (slot 0) closes on ring 1's inner tooth (slot
        # 1): ring 0 moves to 1, ring 1 is caught and turns -1 to 11, not +1.
        game = Game(meshing_machine(), positions=[0, 0, 0])
        game.rotate(0, +1)
        self.assertEqual(game.positions, [1, 11, 0])

    def test_cascade_machine_no_longer_reaches_a_third_ring(self):
        # Ring 1 now travels -1 while ring 0 travels +1, so ring 1's outer
        # tooth (slot 1) moves to slot 0, away from ring 2's inner tooth
        # (slot 2) rather than towards it: the old three-ring ripple no
        # longer forms under counter-rotation.
        game = Game(cascade_machine(), positions=[0, 0, 0])
        game.rotate(0, +1)
        self.assertEqual(game.positions, [1, 11, 0])

    def test_push_cascades_through_to_a_third_ring_with_alternating_signs(self):
        # counter_cascade_machine is built so ring 1's counter-rotation (-1)
        # is what reaches ring 2, giving alternating signs +1, -1, +1.
        game = Game(counter_cascade_machine(), positions=[0, 0, 0])
        game.rotate(0, +1)
        self.assertEqual(game.positions, [1, 11, 1])

    def test_rotating_away_from_a_tooth_does_not_catch(self):
        # meshing_machine catches on CW; a CCW turn of ring 0 opens the gap.
        game = Game(meshing_machine(), positions=[0, 0, 0])
        game.rotate(0, -1)
        self.assertEqual(game.positions, [11, 0, 0])

    def test_rotating_outer_ring_pushes_inner_neighbour(self):
        # Ring 1's inner tooth (slot 1) turned CCW closes on ring 0's outer
        # tooth (slot 0): ring 1 goes to 11, ring 0 is caught and turns the
        # other way, +1 to slot 1. Contact works outer -> inner as well.
        game = Game(meshing_machine(), positions=[0, 0, 0])
        game.rotate(1, -1)
        self.assertEqual(game.positions, [1, 11, 0])


class BindingTest(unittest.TestCase):
    """Counter-rotation's new failure mode: a neighbour's teeth close onto
    each other instead of just travelling together, and the physically
    impossible result is refused rather than applied."""

    def test_binding_two_teeth_into_the_same_slot_is_refused(self):
        game = Game(binding_machine(), positions=[0, 0, 0])
        self.assertFalse(game.rotate(0, +1))
        self.assertEqual(game.positions, [0, 0, 0])


class RandomLegalMoveTest(unittest.TestCase):
    def test_only_returns_moves_that_do_not_jam(self):
        machine = binding_machine()
        rng = random.Random(3)
        for state in all_valid_states(machine):
            for _ in range(4):
                move = random_legal_move(machine, state, rng)
                self.assertIsNotNone(move)
                game = Game(machine, list(state))
                self.assertTrue(game.rotate(move[0], move[1]))

    def test_returns_none_when_every_move_jams(self):
        # Two rings, densely toothed: outer 0 has teeth at 0, 4, 5, 10 and
        # inner 1 at 1, 3, 7, 8. Slots 0/1 are one apart and start a catch
        # for any drive; the extra teeth then bind onto each other in the
        # counter-rotated position, so all four (ring, direction)
        # combinations from [0, 0] refuse.
        machine = Machine(
            inner_teeth=[[], [1, 3, 7, 8]],
            outer_teeth=[[0, 4, 5, 10], []],
            slots=12,
        )
        rng = random.Random(1)
        self.assertIsNone(random_legal_move(machine, [0, 0], rng))

    def test_reaches_every_legal_move_across_repeated_draws(self):
        machine = bare_machine()
        rng = random.Random(11)
        seen = set()
        for _ in range(200):
            seen.add(random_legal_move(machine, [0, 0, 0], rng))
        self.assertEqual(len(seen), 6)


class DrivenRingInvariantTest(unittest.TestCase):
    """Whatever the interlocking drags along, the driven ring itself must move
    exactly one slot in the requested direction on every non-jamming move: CW
    takes it from N to (N + 1) % slots, CCW from N to (N - 1) % slots.
    Exhaustive over every valid state, ring, and direction."""

    def assert_driven_ring_moves_one_slot(self, machine):
        s = machine.slots
        for state in all_valid_states(machine):
            for ring in range(machine.rings):
                for direction in (+1, -1):
                    game = Game(machine, list(state))
                    if not game.rotate(ring, direction):
                        self.assertEqual(game.positions, list(state))
                        continue
                    expected = (state[ring] + direction) % s
                    self.assertEqual(
                        game.positions[ring],
                        expected,
                        f"ring {ring} driven {direction:+d} from {state!r} "
                        f"landed on {game.positions[ring]}, expected {expected}",
                    )
                    # Non-jamming results must also preserve physical
                    # validity: teeth can push each other but never overlap.
                    self.assertTrue(
                        is_valid(machine, game.positions),
                        f"ring {ring} driven {direction:+d} from {state!r} "
                        f"produced overlap {game.positions!r}",
                    )

    def test_default_machine_driven_ring_always_moves_one_slot(self):
        self.assert_driven_ring_moves_one_slot(default_machine())

    def test_meshing_machine_driven_ring_always_moves_one_slot(self):
        self.assert_driven_ring_moves_one_slot(meshing_machine())

    def test_cascade_machine_driven_ring_always_moves_one_slot(self):
        self.assert_driven_ring_moves_one_slot(cascade_machine())

    def test_binding_machine_driven_ring_always_moves_one_slot(self):
        # binding_machine actually jams for some (ring, direction) pairs, so
        # this exercises the non-jamming guard above, not just the trivial
        # always-succeeds case the other fixtures give it.
        self.assert_driven_ring_moves_one_slot(binding_machine())

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
                        f"gap {gap} shares a slot: {combined!r}",
                    )
                    for t in combined:
                        self.assertTrue(0 <= t < m.slots)


ALL_TIERS = (3, 4, 5, 6, 7, 8)


def _teeth_mask(teeth):
    m = 0
    for t in teeth:
        m |= 1 << t
    return m


class CatalogueRoundTripTest(unittest.TestCase):
    def test_shipped_files_reencode_byte_for_byte(self):
        # Independently re-encode every decoded record using only the format
        # documentation; any drift between writer and reader shows up here.
        for rings in ALL_TIERS:
            path = os.path.join(CATALOGUE_DIR, "assets", f"levels_{rings}.lvl")
            with open(path, "rb") as f:
                data = f.read()
            slots, file_rings, count = catalogue_info(data)
            out = [struct.pack("<3sBBH", CATALOGUE_MAGIC, slots, file_rings, count)]
            for i in range(count):
                inner, outer, start, dist, split = catalogue_entry(data, i)
                out.append(struct.pack("<BB", dist, split))
                out.append(bytes(start))
                for inn, o in zip(inner, outer):
                    out.append(struct.pack("<HH", _teeth_mask(inn), _teeth_mask(o)))
            self.assertEqual(b"".join(out), data, f"rings {rings}")

    def test_entry_index_is_bounds_checked(self):
        path = os.path.join(CATALOGUE_DIR, "assets", "levels_3.lvl")
        with open(path, "rb") as f:
            data = f.read()
        _slots, _rings, count = catalogue_info(data)
        with self.assertRaises(IndexError):
            catalogue_entry(data, count)

    def test_the_previous_format_is_rejected_rather_than_misread(self):
        stale = struct.pack("<3sBBH", b"CL1", 12, 3, 0)
        with self.assertRaises(ValueError):
            catalogue_info(stale)


class LegalMoveChurnTest(unittest.TestCase):
    def test_churned_composites_stay_solvable_per_half(self):
        # Bursts on the 6-8 ring composite tiers: churn with the fast picker,
        # then verify each independent half can still reach solved. The limit
        # is widened to dist + 4*churns: with reversible churn each move could
        # raise the distance-to-solved by at most one, but in a directed move
        # graph a legal move can raise it by more, so the old bound no longer
        # holds.
        churns = 6
        for rings in (6, 7, 8):
            cat = load_catalogue(rings)
            rng = random.Random(rings * 11)
            for _ in range(2):
                p = cat["puzzles"][rng.randrange(len(cat["puzzles"]))]
                m = Machine(p["inner"], p["outer"], cat["slots"])
                game = Game(m, p["start"])
                for _ in range(churns):
                    move = random_legal_move(m, game.positions, rng)
                    assert move is not None
                    game.rotate(move[0], move[1])
                k = p["split"]
                limit = p["dist"] + 4 * churns
                half_a = Machine(p["inner"][:k], p["outer"][:k], cat["slots"])
                half_b = Machine(p["inner"][k:], p["outer"][k:], cat["slots"])
                self.assertIsNotNone(solve_distance(half_a, game.positions[:k], limit))
                self.assertIsNotNone(solve_distance(half_b, game.positions[k:], limit))


class CatalogueTest(unittest.TestCase):
    def test_catalogue_entries_are_valid_and_scrambled(self):
        for rings in ALL_TIERS:
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

    def test_composite_entries_have_decoupled_boundaries(self):
        # A composite's halves must not interact: the first ring of half B
        # carries no inner teeth, so nothing meshes across the boundary and
        # the summed distance stays exact.
        for rings in (6, 7, 8):
            cat = load_catalogue(rings)
            for p in cat["puzzles"]:
                k = p["split"]
                self.assertEqual(p["inner"][k], [])
                self.assertTrue(p["outer"][k - 1])

    def test_composite_distances_are_the_sum_of_their_halves(self):
        # Spot-check per composite tier: BFS-verify each half's distance and
        # confirm the recorded distance is exactly their sum.
        for rings in (6, 7, 8):
            cat = load_catalogue(rings)
            rng = random.Random(rings)
            for _ in range(3):
                p = cat["puzzles"][rng.randrange(len(cat["puzzles"]))]
                k = p["split"]
                half_a = Machine(p["inner"][:k], p["outer"][:k], cat["slots"])
                half_b = Machine(p["inner"][k:], p["outer"][k:], cat["slots"])
                da = solve_distance(half_a, p["start"][:k], p["dist"])
                assert da is not None
                db = solve_distance(half_b, p["start"][k:], p["dist"] - da)
                assert db is not None
                self.assertEqual(da + db, p["dist"])

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
                self.assertEqual(solve_distance(m, p["start"], p["dist"]), p["dist"])


class InvertibilityTest(unittest.TestCase):
    def test_counter_rotating_the_same_ring_undoes_a_catchless_move(self):
        # With no cascade, rotate then counter-rotate is a clean round trip.
        game = Game(bare_machine(), positions=[3, 5, 7])
        game.rotate(1, +1)
        game.rotate(1, -1)
        self.assertEqual(game.positions, [3, 5, 7])

    def test_counter_rotating_the_driven_ring_undoes_even_a_cascading_move(self):
        # Counter-rotation meshes like real gears: turning the driven ring
        # back retraces the whole cascade exactly, even through a full
        # three-ring chain. This is unlike the old same-direction rule, where
        # reversing the drive ring separated it from a ring it had dragged.
        game = Game(counter_cascade_machine(), positions=[0, 0, 0])
        game.rotate(0, +1)
        self.assertEqual(game.positions, [1, 11, 1])
        game.rotate(0, -1)
        self.assertEqual(game.positions, [0, 0, 0])


if __name__ == "__main__":
    unittest.main()
