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


TEETH_MIN = 3
TEETH_MAX = 5


def random_machine(rng, rings, slots=12):
    """A random safe: each shared gap gets TEETH_MIN..TEETH_MAX outer and
    inner teeth at distinct random slots, so nothing overlaps at rest and the
    solved state is valid by construction. The decorative rims (innermost
    inner, outermost outer) stay empty. Uses only rng.randrange, which
    MicroPython provides."""
    inner_teeth = [[] for _ in range(rings)]
    outer_teeth = [[] for _ in range(rings)]
    span = TEETH_MAX - TEETH_MIN + 1
    for gap in range(rings - 1):
        n_outer = TEETH_MIN + rng.randrange(span)
        n_inner = TEETH_MIN + rng.randrange(span)
        picked = []
        while len(picked) < n_outer + n_inner:
            slot = rng.randrange(slots)
            if slot not in picked:
                picked.append(slot)
        outer_teeth[gap] = sorted(picked[:n_outer])
        inner_teeth[gap + 1] = sorted(picked[n_outer:])
    return Machine(inner_teeth, outer_teeth, slots)


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


def start_is_scrambled(positions):
    """A start position that actually looks scrambled: no ring aligned to the
    target (slot 0) and no adjacent pair of rings sharing a position."""
    if 0 in positions:
        return False
    for i in range(len(positions) - 1):
        if positions[i] == positions[i + 1]:
            return False
    return True



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
