#!/usr/bin/env python3
"""Report how well the degenerate sweep does against the shipped catalogues.

For every puzzle: the recorded optimal distance, the cheapest greedy sweep, and
their ratio. A ratio near 1.0 means inner-to-outer alignment is as good as
optimal play, which is the weakness the ratchet mechanic exists to fix.

Usage: python tools/measure_greedy.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import Machine, catalogue_entry, catalogue_info  # noqa: E402
from tools.analysis import best_greedy_cost  # noqa: E402

TIERS = (3, 4, 5, 6, 7, 8)


def measure(rings):
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets",
        f"levels_{rings}.lvl",
    )
    with open(path, "rb") as f:
        data = f.read()
    slots, _rings, count = catalogue_info(data)
    ratios = []
    failures = 0
    for i in range(count):
        entry = catalogue_entry(data, i)
        inner, outer, start, dist = entry[0], entry[1], entry[2], entry[3]
        ratchet = entry[5] if len(entry) > 5 else None
        machine = Machine(inner, outer, slots, ratchet)
        greedy = best_greedy_cost(machine, start)
        if greedy is None:
            failures += 1
        else:
            ratios.append(greedy / dist)
    return count, ratios, failures


def main():
    for rings in TIERS:
        count, ratios, failures = measure(rings)
        if not ratios:
            print(f"rings {rings}: {count} puzzles, greedy fails on all")
            continue
        ratios.sort()
        median = ratios[len(ratios) // 2]
        at_or_below_1 = sum(1 for r in ratios if r <= 1.0)
        print(
            f"rings {rings}: {count} puzzles, "
            f"greedy/optimal min {ratios[0]:.2f} "
            f"median {median:.2f} max {ratios[-1]:.2f}, "
            f"optimal-or-better on {at_or_below_1}/{count}, "
            f"greedy fails on {failures}"
        )


if __name__ == "__main__":
    main()
