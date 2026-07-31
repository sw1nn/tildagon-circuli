#!/usr/bin/env python3
"""Generate the on-badge level catalogue. CPython only; never deployed.

For each ring count, random machines are exhaustively distance-mapped by
reverse breadth-first search over the real move graph (moves are not
invertible, so solvability cannot be assumed from reversibility). The
hardest properly-scrambled starts are harvested with their exact minimum
solve distance and written to levels_<rings>.json next to the app code.

Usage: python tools/generate_catalogue.py [seed]
"""

import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import game
from game import _apply, is_valid, random_machine, start_is_scrambled

# Per ring count: puzzles wanted, max starts taken per machine, minimum
# acceptable solve distance, a cap on machines tried, and the teeth-density
# ranges to sample per machine. Dense machines feel treacherous but have
# SHALLOW solvable spaces (measured: at 3-5 teeth almost nothing sits more
# than ~6 moves from solved), so depth comes from the lighter densities and
# the distance map decides which machines make the cut.
PLAN = {
    3: {
        "want": 72,
        "per_machine": 3,
        "floor": 7,
        "machine_cap": 400,
        "densities": [(2, 4), (3, 4), (3, 5)],
    },
    4: {
        "want": 64,
        "per_machine": 4,
        "floor": 9,
        "machine_cap": 250,
        "densities": [(2, 3), (2, 4), (3, 4)],
    },
    5: {
        "want": 36,
        "per_machine": 4,
        "floor": 10,
        "machine_cap": 150,
        "densities": [(2, 3), (2, 4)],
    },
}


def distance_map(machine):
    """Exact distance-to-solved for every state that can reach solved.

    States are base-`slots` encoded ints; solved encodes to 0. Returns the
    {code: distance} map and the decoder.
    """
    n, s = machine.rings, machine.slots
    total = s**n

    def decode(code):
        state = []
        for _ in range(n):
            state.append(code % s)
            code //= s
        return tuple(state)

    def encode(state):
        code = 0
        for p in reversed(state):
            code = code * s + p
        return code

    preds = [None] * total
    for code in range(total):
        state = decode(code)
        if not is_valid(machine, state):
            continue
        for ring in range(n):
            for d in (1, -1):
                succ = encode(_apply(machine, state, ring, d))
                bucket = preds[succ]
                if bucket is None:
                    preds[succ] = bucket = [code]
                else:
                    bucket.append(code)

    dist = {0: 0}
    frontier = [0]
    while frontier:
        nxt = []
        for c in frontier:
            bucket = preds[c]
            if bucket:
                for p in bucket:
                    if p not in dist:
                        dist[p] = dist[c] + 1
                        nxt.append(p)
        frontier = nxt
    return dist, decode


def harvest(machine, dist, decode, per_machine, floor, rng):
    """The hardest properly-scrambled starts of one machine: states within
    80% of the machine's own maximum distance, at or above the floor."""
    cands = []
    for code, d in dist.items():
        if d < floor:
            continue
        state = decode(code)
        if start_is_scrambled(state):
            cands.append((d, state))
    if not cands:
        return []
    dmax = max(d for d, _ in cands)
    top = [(d, st) for d, st in cands if d >= max(floor, int(dmax * 0.8))]
    rng.shuffle(top)
    return top[:per_machine]


def generate(rings, plan, rng):
    puzzles = []
    machines = 0
    t0 = time.time()
    while len(puzzles) < plan["want"] and machines < plan["machine_cap"]:
        game.TEETH_MIN, game.TEETH_MAX = plan["densities"][
            rng.randrange(len(plan["densities"]))
        ]
        machine = random_machine(rng, rings)
        machines += 1
        dist, decode = distance_map(machine)
        picks = harvest(
            machine, dist, decode, plan["per_machine"], plan["floor"], rng
        )
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
                f"(teeth {game.TEETH_MIN}-{game.TEETH_MAX}) -> "
                f"dists {sorted(d for d, _ in picks)}, "
                f"total {len(puzzles)}/{plan['want']} [{time.time() - t0:.0f}s]",
                flush=True,
            )
    print(
        f"rings {rings}: tried {machines} machines in {time.time() - t0:.0f}s",
        flush=True,
    )
    return puzzles[: plan["want"]]


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    rng = random.Random(seed)
    out_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    failed = []
    for rings, plan in PLAN.items():
        puzzles = generate(rings, plan, rng)
        if not puzzles:
            failed.append(rings)
            print(f"rings {rings}: NO puzzles found — file not written", flush=True)
            continue
        dists = sorted(p["dist"] for p in puzzles)
        path = os.path.join(out_dir, f"levels_{rings}.json")
        with open(path, "w") as f:
            json.dump({"slots": 12, "rings": rings, "puzzles": puzzles}, f)
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
