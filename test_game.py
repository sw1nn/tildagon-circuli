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
    random_reversible_move,
    ratchet_masks,
    reversible_moves,
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
        inner, outer, start, dist, split, ratchet = catalogue_entry(data, i)
        entry = {
            "inner": inner,
            "outer": outer,
            "start": start,
            "dist": dist,
            "ratchet": ratchet,
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
    """Ring 0 catches ring 1 (outer 0 -> inner 1), and ring 1 catches ring 2
    (outer 1 -> inner 2), so a single push of ring 0 ripples to ring 2."""
    return Machine(
        inner_teeth=[[], [1], [2]],
        outer_teeth=[[0], [1], []],
        slots=12,
    )


def ratchet_bare_machine():
    """No teeth anywhere, ring 1 ratcheted clockwise-only: the cleanest case
    of a direct turn being refused with no cascade involved."""
    return Machine(
        inner_teeth=[[], [], []],
        outer_teeth=[[], [], []],
        slots=12,
        ratchet=[0, +1, 0],
    )


def dragged_machine():
    """meshing_machine with ring 1 ratcheted clockwise-only, so the drag that
    a clockwise push of ring 0 produces is in the permitted direction."""
    return Machine(
        inner_teeth=[[], [1], []],
        outer_teeth=[[0], [], []],
        slots=12,
        ratchet=[0, +1, 0],
    )


def anchor_machine():
    """Ring 0's outer tooth sits one slot clockwise of ring 1's inner tooth, so
    driving ring 0 counter-clockwise drags ring 1 the same way. Ring 1 is
    ratcheted clockwise-only, so that drag jams the whole move."""
    return Machine(
        inner_teeth=[[], [1], []],
        outer_teeth=[[2], [], []],
        slots=12,
        ratchet=[0, +1, 0],
    )


def deep_anchor_machine():
    """A counter-clockwise push of ring 0 ripples all the way to ring 2, which
    is ratcheted clockwise-only: the far ring anchors the whole group."""
    return Machine(
        inner_teeth=[[], [1], [2]],
        outer_teeth=[[2], [3], []],
        slots=12,
        ratchet=[0, 0, +1],
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


class RatchetTest(unittest.TestCase):
    def test_a_ratcheted_ring_turns_freely_in_its_permitted_direction(self):
        game = Game(ratchet_bare_machine(), positions=[0, 0, 0])
        self.assertTrue(game.rotate(1, +1))
        self.assertEqual(game.positions, [0, 1, 0])

    def test_a_direct_turn_against_the_ratchet_is_refused(self):
        game = Game(ratchet_bare_machine(), positions=[0, 5, 0])
        self.assertFalse(game.rotate(1, -1))
        self.assertEqual(game.positions, [0, 5, 0])

    def test_free_rings_are_unaffected_by_a_neighbours_ratchet(self):
        game = Game(ratchet_bare_machine(), positions=[0, 0, 0])
        self.assertTrue(game.rotate(0, -1))
        self.assertEqual(game.positions, [11, 0, 0])

    def test_a_drag_in_the_permitted_direction_is_allowed(self):
        game = Game(dragged_machine(), positions=[0, 0, 0])
        self.assertTrue(game.rotate(0, +1))
        self.assertEqual(game.positions, [1, 1, 0])

    def test_a_drag_against_the_ratchet_jams_the_whole_move(self):
        game = Game(anchor_machine(), positions=[0, 0, 0])
        self.assertFalse(game.rotate(0, -1))
        self.assertEqual(game.positions, [0, 0, 0])

    def test_a_ratchet_the_cascade_never_reaches_does_not_block(self):
        game = Game(anchor_machine(), positions=[0, 0, 0])
        self.assertTrue(game.rotate(0, +1))
        self.assertEqual(game.positions, [1, 0, 0])

    def test_a_ratchet_deep_in_the_cascade_anchors_every_ring(self):
        game = Game(deep_anchor_machine(), positions=[0, 0, 0])
        self.assertFalse(game.rotate(0, -1))
        self.assertEqual(game.positions, [0, 0, 0])

    def test_the_same_deep_cascade_moves_in_the_permitted_direction(self):
        game = Game(deep_anchor_machine(), positions=[0, 0, 0])
        self.assertTrue(game.rotate(0, +1))
        self.assertEqual(game.positions[0], 1)

    def test_ratchet_defaults_to_every_ring_free(self):
        self.assertEqual(bare_machine().ratchet, [0, 0, 0])

    def test_ratchet_length_must_cover_every_ring(self):
        with self.assertRaises(ValueError):
            Machine(
                inner_teeth=[[], [], []],
                outer_teeth=[[], [], []],
                slots=12,
                ratchet=[0, +1],
            )

    def test_driven_ring_still_moves_one_slot_on_every_non_jamming_move(self):
        machine = deep_anchor_machine()
        s = machine.slots
        for state in all_valid_states(machine):
            for ring in range(machine.rings):
                for direction in (+1, -1):
                    game = Game(machine, list(state))
                    if not game.rotate(ring, direction):
                        self.assertEqual(game.positions, list(state))
                        continue
                    self.assertEqual(
                        game.positions[ring], (state[ring] + direction) % s
                    )
                    self.assertTrue(is_valid(machine, game.positions))


class RandomLegalMoveTest(unittest.TestCase):
    def test_only_returns_moves_that_do_not_jam(self):
        machine = deep_anchor_machine()
        rng = random.Random(3)
        for state in all_valid_states(machine):
            for _ in range(4):
                move = random_legal_move(machine, state, rng)
                self.assertIsNotNone(move)
                game = Game(machine, list(state))
                self.assertTrue(game.rotate(move[0], move[1]))

    def test_returns_none_when_every_move_jams(self):
        # Both rings ratcheted the same way and permanently meshed: any push
        # gathers both rings, and one of them always refuses.
        machine = Machine(
            inner_teeth=[[], [1]],
            outer_teeth=[[0], []],
            slots=12,
            ratchet=[+1, -1],
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
                        f"ring {ring} driven {direction:+d} from {state!r} "
                        f"landed on {game.positions[ring]}, expected {expected}",
                    )
                    # Moves must also preserve physical validity: teeth can
                    # push each other but never overlap.
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

    def test_ratchet_count_is_honoured_with_valid_directions(self):
        for rings in (3, 4, 5):
            for count in range(rings + 1):
                rng = random.Random(rings * 100 + count)
                m = random_machine(rng, rings, ratchet_count=count)
                self.assertEqual(sum(1 for r in m.ratchet if r), count)
                for r in m.ratchet:
                    self.assertIn(r, (0, +1, -1))


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
                inner, outer, start, dist, split, ratchet = catalogue_entry(data, i)
                mask, dirs = ratchet_masks(ratchet)
                out.append(struct.pack("<BBBB", dist, split, mask, dirs))
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

    def test_unused_ratchet_direction_bits_are_clear(self):
        # A set direction bit for a free ring would round-trip differently and
        # signals a writer bug.
        for rings in ALL_TIERS:
            path = os.path.join(CATALOGUE_DIR, "assets", f"levels_{rings}.lvl")
            with open(path, "rb") as f:
                data = f.read()
            _slots, _rings, count = catalogue_info(data)
            for i in range(count):
                ratchet = catalogue_entry(data, i)[5]
                mask, dirs = ratchet_masks(ratchet)
                self.assertEqual(dirs & ~mask, 0)


class RatchetRampTest(unittest.TestCase):
    RAMP = {3: 0, 4: 0, 5: 1, 6: 2, 7: 2, 8: 3}

    def test_every_puzzle_carries_the_ratchet_count_its_tier_specifies(self):
        for rings in ALL_TIERS:
            cat = load_catalogue(rings)
            for p in cat["puzzles"]:
                count = sum(1 for r in p["ratchet"] if r)
                self.assertEqual(count, self.RAMP[rings], f"rings {rings}")

    def test_ratchet_directions_are_only_ever_plus_or_minus_one(self):
        for rings in ALL_TIERS:
            cat = load_catalogue(rings)
            for p in cat["puzzles"]:
                for r in p["ratchet"]:
                    self.assertIn(r, (0, +1, -1))


class ReversibleChurnTest(unittest.TestCase):
    def test_reversible_churn_preserves_solvability(self):
        # The vortex burst punishes button-mashing with random moves, but
        # draws them only from reversible_moves: churning a catalogue start
        # must leave the board solvable (within original distance + churns).
        cat = load_catalogue(3)
        rng = random.Random(99)
        churns = 6
        for _ in range(5):
            p = cat["puzzles"][rng.randrange(len(cat["puzzles"]))]
            m = Machine(p["inner"], p["outer"], cat["slots"], p["ratchet"])
            game = Game(m, p["start"])
            for _ in range(churns):
                options = reversible_moves(m, game.positions)
                self.assertTrue(options)
                ring, d, _result = options[rng.randrange(len(options))]
                game.rotate(ring, d)
            self.assertIsNotNone(
                solve_distance(m, game.positions, p["dist"] + churns),
                f"churned start became unsolvable: {game.positions!r}",
            )

    def test_random_reversible_move_matches_reversible_set(self):
        # The fast picker the burst uses must only ever return moves the
        # exhaustive enumeration also considers reversible.
        cat = load_catalogue(4)
        rng = random.Random(7)
        for _ in range(10):
            p = cat["puzzles"][rng.randrange(len(cat["puzzles"]))]
            m = Machine(p["inner"], p["outer"], cat["slots"], p["ratchet"])
            move = random_reversible_move(m, p["start"], rng)
            self.assertIsNotNone(move)
            allowed = {(r, d) for r, d, _res in reversible_moves(m, p["start"])}
            self.assertIn(move, allowed)

    def test_churned_composites_stay_solvable_per_half(self):
        # Bursts on the 6-8 ring composite tiers: churn with the fast picker,
        # then verify each independent half can still reach solved.
        churns = 6
        for rings in (6, 7, 8):
            cat = load_catalogue(rings)
            rng = random.Random(rings * 11)
            for _ in range(2):
                p = cat["puzzles"][rng.randrange(len(cat["puzzles"]))]
                m = Machine(p["inner"], p["outer"], cat["slots"], p["ratchet"])
                game = Game(m, p["start"])
                for _ in range(churns):
                    move = random_reversible_move(m, game.positions, rng)
                    assert move is not None
                    game.rotate(move[0], move[1])
                k = p["split"]
                limit = p["dist"] + churns
                half_a = Machine(
                    p["inner"][:k], p["outer"][:k], cat["slots"], p["ratchet"][:k]
                )
                half_b = Machine(
                    p["inner"][k:], p["outer"][k:], cat["slots"], p["ratchet"][k:]
                )
                self.assertIsNotNone(solve_distance(half_a, game.positions[:k], limit))
                self.assertIsNotNone(solve_distance(half_b, game.positions[k:], limit))


class CatalogueTest(unittest.TestCase):
    def test_catalogue_entries_are_valid_and_scrambled(self):
        for rings in ALL_TIERS:
            cat = load_catalogue(rings)
            self.assertEqual(cat["rings"], rings)
            self.assertTrue(cat["puzzles"])
            for p in cat["puzzles"]:
                m = Machine(p["inner"], p["outer"], cat["slots"], p["ratchet"])
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
                half_a = Machine(
                    p["inner"][:k], p["outer"][:k], cat["slots"], p["ratchet"][:k]
                )
                half_b = Machine(
                    p["inner"][k:], p["outer"][k:], cat["slots"], p["ratchet"][k:]
                )
                da = solve_distance(half_a, p["start"][:k], p["dist"])
                assert da is not None
                db = solve_distance(half_b, p["start"][k:], p["dist"] - da)
                assert db is not None
                self.assertEqual(da + db, p["dist"])

    def test_catalogue_distances_are_exact_for_three_rings(self):
        # Every shipped 3-ring puzzle re-verified against the BFS oracle.
        cat = load_catalogue(3)
        for p in cat["puzzles"]:
            m = Machine(p["inner"], p["outer"], cat["slots"], p["ratchet"])
            self.assertEqual(solve_distance(m, p["start"], p["dist"]), p["dist"])

    def test_catalogue_distances_spot_checked_for_higher_rings(self):
        # Full re-verification is slow at 4-5 rings; spot-check a sample.
        for rings, samples in ((4, 4), (5, 2)):
            cat = load_catalogue(rings)
            rng = random.Random(rings)
            for _ in range(samples):
                p = cat["puzzles"][rng.randrange(len(cat["puzzles"]))]
                m = Machine(p["inner"], p["outer"], cat["slots"], p["ratchet"])
                self.assertEqual(solve_distance(m, p["start"], p["dist"]), p["dist"])


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
