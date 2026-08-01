"""Offline exhaustive search and measurement over Circuli machines.

CPython only, and never imported by the badge app: everything here walks the
whole state space. States are base-`slots` encoded ints so they can index flat
lists; the solved state encodes to 0.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import _apply, is_valid  # noqa: E402

GREEDY_MAX_SWEEPS = 4
GREEDY_ORDERS = ("inner-out", "outer-in")
# +1 and -1 drive every ring the same way; 0 means shortest way round per ring.
GREEDY_MODES = (+1, -1, 0)


def encode(state, slots):
    code = 0
    for p in reversed(state):
        code = code * slots + p
    return code


def decode(code, rings, slots):
    state = []
    for _ in range(rings):
        state.append(code % slots)
        code //= slots
    return tuple(state)


def build_predecessors(machine):
    """preds[code] holds every valid state with a single legal move into
    `code`, or None when nothing reaches it. Jammed moves contribute no edge,
    so the graph carries no self-loops."""
    n, s = machine.rings, machine.slots
    preds = [None] * (s**n)
    for code in range(s**n):
        state = decode(code, n, s)
        if not is_valid(machine, state):
            continue
        for ring in range(n):
            for d in (1, -1):
                result = _apply(machine, state, ring, d)
                if result is None:
                    continue
                succ = encode(result, s)
                bucket = preds[succ]
                if bucket is None:
                    preds[succ] = [code]
                else:
                    bucket.append(code)
    return preds


def distance_map(machine, preds=None):
    """Exact distance-to-solved for every state that can reach solved, by
    reverse breadth-first search. Moves are not invertible, so solvability
    cannot be inferred from reachability in the forward direction."""
    if preds is None:
        preds = build_predecessors(machine)
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
    return dist


def doomed_states(machine, dist, preds=None):
    """Every state from which some sequence of legal moves reaches a state that
    can no longer reach solved.

    Computed once per machine by reverse breadth-first search from the unsafe
    states, so a candidate start is then an O(1) membership test rather than a
    fresh forward search.
    """
    n, s = machine.rings, machine.slots
    if preds is None:
        preds = build_predecessors(machine)
    doomed = set()
    frontier = []
    for code in range(s**n):
        if code in dist:
            continue
        if not is_valid(machine, decode(code, n, s)):
            continue
        doomed.add(code)
        frontier.append(code)
    while frontier:
        nxt = []
        for c in frontier:
            bucket = preds[c]
            if bucket:
                for p in bucket:
                    if p not in doomed:
                        doomed.add(p)
                        nxt.append(p)
        frontier = nxt
    return doomed


def is_dead_end_free(code, slots, doomed):
    """True when no legal play from `code` can strand the player. `code` may be
    an encoded int or a position tuple."""
    if not isinstance(code, int):
        code = encode(code, slots)
    return code not in doomed


def _step_direction(machine, pos, ring, mode, slots):
    """Which way the greedy sweep turns `ring`. A ratcheted ring only has one
    option, so every mode collapses to it and the bot never attempts a turn the
    ratchet refuses outright."""
    fixed = machine.ratchet[ring]
    if fixed:
        return fixed
    if mode:
        return mode
    return -1 if pos[ring] <= slots // 2 else +1


def _solved(pos):
    for p in pos:
        if p != 0:
            return False
    return True


def greedy_cost(machine, start, order, mode, max_sweeps=GREEDY_MAX_SWEEPS):
    """Moves the degenerate sweep spends solving `start`, or None if it jams or
    runs out of sweeps.

    The sweep aligns each ring in turn and repeats, which is what a player
    doing this by hand actually does: one pass rarely finishes once drags start
    disturbing rings already aligned. The driven ring always advances exactly
    one slot on a successful move, so each inner loop terminates.
    """
    rings = list(range(machine.rings))
    if order == "outer-in":
        rings.reverse()
    pos = tuple(start)
    moves = 0
    for _ in range(max_sweeps):
        if _solved(pos):
            return moves
        for ring in rings:
            while pos[ring] != 0:
                d = _step_direction(machine, pos, ring, mode, machine.slots)
                result = _apply(machine, pos, ring, d)
                if result is None:
                    return None
                pos = result
                moves += 1
    return moves if _solved(pos) else None


def best_greedy_cost(machine, start, max_sweeps=GREEDY_MAX_SWEEPS):
    """The cheapest sweep any variant finds, or None if every variant fails.
    Taking the best is the honest bar: a competent player finds the good one."""
    best = None
    for order in GREEDY_ORDERS:
        for mode in GREEDY_MODES:
            cost = greedy_cost(machine, start, order, mode, max_sweeps)
            if cost is not None and (best is None or cost < best):
                best = cost
    return best
