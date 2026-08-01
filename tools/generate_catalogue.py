#!/usr/bin/env python3
"""Generate the on-badge level catalogue. CPython only; never deployed.

For each ring count, random machines are exhaustively distance-mapped by
reverse breadth-first search over the real move graph (moves are not
invertible, so solvability cannot be assumed from reversibility). The
hardest properly-scrambled starts are harvested with their exact minimum
solve distance and written to binary assets/levels_<rings>.lvl files
(format documented alongside the decoder in game.py).

Usage: python tools/generate_catalogue.py [seed]
"""

import os
import random
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import (
    CATALOGUE_MAGIC,
    random_machine,
    start_is_scrambled,
)
from tools.analysis import (
    best_greedy_cost,
    build_predecessors,
    decode,
    distance_map,
    doomed_states,
    is_dead_end_free,
)

# Acceptance bar for the degenerate inner-to-outer sweep: a start only ships if
# the best greedy variant costs at least this multiple of the true optimum, or
# fails outright. The pre-change baseline (tools/measure_greedy.py) found a
# median ratio of exactly 1.00 on every tier and a worst case anywhere of only
# 1.53, so 1.5 is the bar that is actually reachable without starving any
# tier.
GREEDY_RATIO = 1.5

# Per ring count: puzzles wanted, max starts taken per machine, minimum
# acceptable solve distance, a cap on machines tried, and the teeth-density
# ranges to sample per machine. Dense machines feel treacherous but have
# SHALLOW solvable spaces (measured: at 3-5 teeth almost nothing sits more
# than ~6 moves from solved), so depth comes from the lighter densities and
# the distance map decides which machines make the cut.
BASE_PLAN = {
    3: {
        "want": 72,
        "per_machine": 3,
        "floor": 5,
        "machine_cap": 200,
        "densities": [(2, 3), (2, 4)],
    },
    4: {
        "want": 64,
        "per_machine": 4,
        "floor": 5,
        "machine_cap": 200,
        "densities": [(2, 3), (2, 4)],
    },
    5: {
        "want": 36,
        "per_machine": 4,
        "floor": 5,
        "machine_cap": 100,
        "densities": [(2, 3), (2, 4)],
    },
}

# Ring counts beyond exhaustive reach (12^n states) are COMPOSITES: two base
# puzzles spliced at a boundary gap that carries teeth on the inner side only,
# so the halves never interact and the minimum solve distance is exactly the
# sum of the halves' verified distances. "split" records the boundary for
# re-verification.
COMPOSITE_PLAN = {
    6: {"want": 36, "halves": (3, 3)},
    7: {"want": 24, "halves": (4, 3)},
    8: {"want": 24, "halves": (4, 4)},
}


def harvest(machine, dist, per_machine, floor, rng, preds=None):
    """The hardest properly-scrambled starts of one machine that are also safe
    and greedy-resistant: states within 80% of the machine's own maximum
    distance, at or above the floor, from which no play can strand the player,
    and which the degenerate sweep cannot solve cheaply.

    The greedy bot is the expensive check (up to 6 searches per candidate), so
    it only runs over the top-80% band, not every candidate above the floor,
    and stops as soon as enough picks are found. `doomed_states` is computed
    once per machine, so the per-candidate safety test is a set membership
    rather than a fresh search.
    """
    doomed = doomed_states(machine, dist, preds)
    cands = []
    for code, d in dist.items():
        if d < floor:
            continue
        state = decode(code, machine.rings, machine.slots)
        if not start_is_scrambled(state):
            continue
        if not is_dead_end_free(code, machine.slots, doomed):
            continue
        cands.append((d, state))
    if not cands:
        return []
    dmax = max(d for d, _ in cands)
    top = [(d, st) for d, st in cands if d >= max(floor, int(dmax * 0.8))]
    rng.shuffle(top)
    picks = []
    for d, state in top:
        greedy = best_greedy_cost(machine, state)
        if greedy is not None and greedy < GREEDY_RATIO * d:
            continue
        picks.append((d, state))
        if len(picks) >= per_machine:
            break
    return picks


def generate(rings, plan, rng):
    puzzles = []
    machines = 0
    t0 = time.time()
    while len(puzzles) < plan["want"] and machines < plan["machine_cap"]:
        teeth_min, teeth_max = plan["densities"][rng.randrange(len(plan["densities"]))]
        machine = random_machine(
            rng,
            rings,
            teeth_min=teeth_min,
            teeth_max=teeth_max,
        )
        machines += 1
        preds = build_predecessors(machine)
        dist = distance_map(machine, preds)
        picks = harvest(machine, dist, plan["per_machine"], plan["floor"], rng, preds)
        for d, state in picks:
            puzzles.append(
                {
                    "inner": machine.inner_teeth,
                    "outer": machine.outer_teeth,
                    "start": list(state),
                    "dist": d,
                }
            )
        if picks:
            print(
                f"rings {rings}: machine {machines} "
                f"(teeth {teeth_min}-{teeth_max}) -> "
                f"dists {sorted(d for d, _ in picks)}, "
                f"total {len(puzzles)}/{plan['want']} [{time.time() - t0:.0f}s]",
                flush=True,
            )
    print(
        f"rings {rings}: tried {machines} machines in {time.time() - t0:.0f}s",
        flush=True,
    )
    return puzzles[: plan["want"]]


def _mask(teeth):
    m = 0
    for t in teeth:
        m |= 1 << t
    return m


def compose(entry_a, entry_b, rng, slots=12):
    """Splice two base puzzles; half A's outermost rim gets decorative teeth
    (its partner rim is empty, so the halves never couple) and the composite
    distance is exactly the sum of the halves'."""
    inner = [list(t) for t in entry_a["inner"]] + [list(t) for t in entry_b["inner"]]
    outer = [list(t) for t in entry_a["outer"]] + [list(t) for t in entry_b["outer"]]
    k = len(entry_a["inner"])
    n_teeth = 2 + rng.randrange(3)
    teeth = []
    while len(teeth) < n_teeth:
        slot = rng.randrange(slots)
        if slot not in teeth:
            teeth.append(slot)
    outer[k - 1] = sorted(teeth)
    return {
        "inner": inner,
        "outer": outer,
        "start": list(entry_a["start"]) + list(entry_b["start"]),
        "dist": entry_a["dist"] + entry_b["dist"],
        "split": k,
    }


def compose_tier(plan, pools, rng):
    rings_a, rings_b = plan["halves"]
    pool_a, pool_b = pools[rings_a], pools[rings_b]
    if not pool_a or not pool_b:
        # A base tier came up empty; report rather than crash on randrange.
        return []
    puzzles = []
    seen = set()
    attempts = 0
    while len(puzzles) < plan["want"] and attempts < plan["want"] * 50:
        attempts += 1
        ia = rng.randrange(len(pool_a))
        ib = rng.randrange(len(pool_b))
        if rings_a == rings_b and ia == ib:
            continue
        if (ia, ib) in seen:
            continue
        pa, pb = pool_a[ia], pool_b[ib]
        # The boundary is the only place the splice could break
        # start_is_scrambled: both halves are already fully scrambled.
        if pa["start"][-1] == pb["start"][0]:
            continue
        seen.add((ia, ib))
        puzzles.append(compose(pa, pb, rng))
    return puzzles


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    rng = random.Random(seed)
    out_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    failed = []
    pools = {}
    for rings, plan in BASE_PLAN.items():
        pools[rings] = generate(rings, plan, rng)
    for rings, plan in COMPOSITE_PLAN.items():
        pools[rings] = compose_tier(plan, pools, rng)
    for rings, puzzles in sorted(pools.items()):
        if not puzzles:
            failed.append(rings)
            print(f"rings {rings}: NO puzzles found — file not written", flush=True)
            continue
        dists = sorted(p["dist"] for p in puzzles)
        assets = os.path.join(out_dir, "assets")
        if not os.path.isdir(assets):
            os.makedirs(assets)
        path = os.path.join(assets, f"levels_{rings}.lvl")
        with open(path, "wb") as f:
            f.write(struct.pack("<3sBBH", CATALOGUE_MAGIC, 12, rings, len(puzzles)))
            for p in puzzles:
                f.write(struct.pack("<BB", p["dist"], p.get("split", 0)))
                f.write(bytes(p["start"]))
                f.writelines(
                    struct.pack("<HH", _mask(inner), _mask(outer))
                    for inner, outer in zip(p["inner"], p["outer"])
                )
        print(
            f"rings {rings}: wrote {len(puzzles)} puzzles, dist "
            f"min {dists[0]} median {dists[len(dists) // 2]} max {dists[-1]} "
            f"-> {path}",
            flush=True,
        )
    if failed:
        sys.exit(f"incomplete catalogue: no puzzles for rings {failed}")


if __name__ == "__main__":
    main()
