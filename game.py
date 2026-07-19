"""Pure game logic for the Circuli puzzle.

No display or hardware imports here, so it runs and tests under plain CPython as
well as on-badge MicroPython. Rendering and input live in app.py.
"""


class Machine:
    """A fixed 'safe': concentric rings with teeth at fixed ring-frame slot offsets.

    inner_teeth[i] / outer_teeth[i] are the slot offsets of ring i's inner and
    outer rim teeth. Only ring i's outer teeth and ring i+1's inner teeth share
    a gap and can catch on each other.
    """

    def __init__(self, inner_teeth, outer_teeth, slots=12):
        self.inner_teeth = [list(t) for t in inner_teeth]
        self.outer_teeth = [list(t) for t in outer_teeth]
        self.slots = slots
        self.rings = len(inner_teeth)
        self._solvable = None


def default_machine():
    """The fixed safe the game ships with.

    Both shared gaps carry three evenly-spaced teeth, offset so nothing meshes
    at rest (the solved state). The innermost inner tooth and outermost outer
    tooth have no partner ring, so they are purely decorative.
    """
    return Machine(
        inner_teeth=[[6], [2, 6, 10], [3, 7, 11]],
        outer_teeth=[[0, 4, 8], [1, 5, 9], [0]],
        slots=12,
    )


def is_valid(machine, positions):
    """True if no shared gap has an inner ring's outer tooth overlapping the
    outer ring's inner tooth. Overlapping teeth are physically impossible; the
    solved state and every state reachable from it by play are valid."""
    s = machine.slots
    for i in range(machine.rings - 1):
        outer = set((positions[i] + t) % s for t in machine.outer_teeth[i])
        for t in machine.inner_teeth[i + 1]:
            if (positions[i + 1] + t) % s in outer:
                return False
    return True


def _would_collide(machine, pos, i, j, group, direction):
    """Would ring i's outer teeth land on ring j's (=i+1) inner teeth, with the
    rings currently in `group` shifted by `direction`?"""
    s = machine.slots
    pi = pos[i] + (direction if i in group else 0)
    pj = pos[j] + (direction if j in group else 0)
    outer = set((pi + t) % s for t in machine.outer_teeth[i])
    for t in machine.inner_teeth[j]:
        if (pj + t) % s in outer:
            return True
    return False


def _apply(machine, positions, ring, direction):
    """Return the new positions after rotating `ring` one step in `direction`.

    Gathers every ring that would catch in the direction of motion into one
    rigid group (cascading inward and outward), then turns the whole group
    together. Pure: does not mutate `positions`.
    """
    n = machine.rings
    s = machine.slots
    pos = list(positions)
    group = set()
    group.add(ring)
    grew = True
    while grew:
        grew = False
        for i in range(n - 1):
            j = i + 1
            i_in = i in group
            j_in = j in group
            if i_in == j_in:
                continue
            if _would_collide(machine, pos, i, j, group, direction):
                group.add(i if j_in else j)
                grew = True
    for r in group:
        pos[r] = (pos[r] + direction) % s
    return tuple(pos)


def _all_states(n, s):
    """Yield every ring-position tuple, odometer order."""
    state = [0] * n
    while True:
        yield tuple(state)
        i = 0
        while i < n:
            state[i] += 1
            if state[i] < s:
                break
            state[i] = 0
            i += 1
        else:
            return


def solvable_states(machine):
    """Map every state from which the solved state is reachable to its shortest
    distance (in moves) to solved. Computed once per machine and cached.

    Atomic moves are not invertible (a catch that drags neighbours cannot be
    undone by a single counter-rotation), so solvability is established by
    reverse breadth-first search from solved over the real move graph rather
    than assumed from reversibility.
    """
    if machine._solvable is not None:
        return machine._solvable
    n = machine.rings
    s = machine.slots
    solved = tuple([0] * n)
    preds = {}
    for state in _all_states(n, s):
        if not is_valid(machine, state):
            continue
        for ring in range(n):
            for d in (1, -1):
                succ = _apply(machine, state, ring, d)
                bucket = preds.get(succ)
                if bucket is None:
                    bucket = set()
                    preds[succ] = bucket
                bucket.add(state)
    dist = {solved: 0}
    frontier = [solved]
    while frontier:
        nxt = []
        for st in frontier:
            for p in preds.get(st, ()):
                if p not in dist:
                    dist[p] = dist[st] + 1
                    nxt.append(p)
        frontier = nxt
    machine._solvable = dist
    return dist


class Game:
    def __init__(self, machine, positions=None):
        self.machine = machine
        if positions is None:
            self.positions = [0] * machine.rings
        else:
            self.positions = list(positions)

    def rotate(self, ring, direction):
        """Rotate `ring` one step in `direction` (+1 CW, -1 CCW), dragging any
        rings it catches."""
        self.positions = list(_apply(self.machine, self.positions, ring, direction))

    def is_solved(self):
        for p in self.positions:
            if p != 0:
                return False
        return True

    def scramble(self, rng, min_distance=6):
        """Set positions to a guaranteed-solvable, not-already-solved start.

        Prefers states at least `min_distance` moves from solved; falls back to
        any solvable non-solved state if none are that far.
        """
        dist = solvable_states(self.machine)
        hard = [st for st, d in dist.items() if d >= min_distance]
        pool = hard if hard else [st for st, d in dist.items() if d > 0]
        self.positions = list(pool[rng.randrange(len(pool))])
