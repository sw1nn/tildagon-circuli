"""Pure game logic for the Circuli puzzle.

No display or hardware imports here, so it runs and tests under plain CPython as
well as on-badge MicroPython. Rendering and input live in app.py.
"""

import struct


class Machine:
    """A fixed 'safe': concentric rings with teeth at fixed ring-frame slot offsets.

    inner_teeth[i] / outer_teeth[i] are the slot offsets of ring i's inner and
    outer rim teeth. Only ring i's outer teeth and ring i+1's inner teeth share
    a gap and can catch on each other.
    """

    def __init__(self, inner_teeth, outer_teeth, slots=12):
        if len(inner_teeth) != len(outer_teeth):
            raise ValueError("inner_teeth and outer_teeth must cover the same rings")
        self.inner_teeth = [list(t) for t in inner_teeth]
        self.outer_teeth = [list(t) for t in outer_teeth]
        self.slots = slots
        self.rings = len(inner_teeth)


def default_machine():
    """A small fixed example machine, used by the tests as a known fixture.

    Both shared gaps carry three evenly-spaced teeth, offset so nothing meshes
    at rest (the solved state). The innermost inner tooth and outermost outer
    tooth have no partner ring, so they are purely decorative. Shipped puzzles
    come from the level catalogue instead.
    """
    return Machine(
        inner_teeth=[[6], [2, 6, 10], [3, 7, 11]],
        outer_teeth=[[0, 4, 8], [1, 5, 9], [0]],
        slots=12,
    )


TEETH_MIN = 3
TEETH_MAX = 5


def random_machine(
    rng,
    rings,
    slots=12,
    teeth_min=TEETH_MIN,
    teeth_max=TEETH_MAX,
):
    """A random safe: each shared gap gets teeth_min..teeth_max outer and
    inner teeth at distinct random slots, so nothing overlaps at rest and the
    solved state is valid by construction. The decorative rims (innermost
    inner, outermost outer) stay empty. Uses only rng.randrange, which
    MicroPython provides."""
    inner_teeth = [[] for _ in range(rings)]
    outer_teeth = [[] for _ in range(rings)]
    span = teeth_max - teeth_min + 1
    for gap in range(rings - 1):
        n_outer = teeth_min + rng.randrange(span)
        n_inner = teeth_min + rng.randrange(span)
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
        outer = {(positions[i] + t) % s for t in machine.outer_teeth[i]}
        for t in machine.inner_teeth[i + 1]:
            if (positions[i + 1] + t) % s in outer:
                return False
    return True


def _would_collide(machine, pos, i, j, sign, direction):
    """Would ring i's outer teeth land on ring j's (=i+1) inner teeth, given
    the travel each ring is currently assigned? A ring with sign 0 is not yet
    part of the cascade and is treated as stationary."""
    s = machine.slots
    pi = pos[i] + direction * sign[i]
    pj = pos[j] + direction * sign[j]
    outer = set()
    for t in machine.outer_teeth[i]:
        outer.add((pi + t) % s)
    for t in machine.inner_teeth[j]:
        if (pj + t) % s in outer:
            return True
    return False


def _apply(machine, positions, ring, direction):
    """Return the new positions after rotating `ring` one step in `direction`,
    or None if the gears bind.

    Meshing teeth turn their neighbour the opposite way, so signs alternate
    outward from the driven ring through the whole cascade. Because
    counter-rotating neighbours close on each other rather than travelling
    together, a cascade can drive teeth into the same slot; that state is
    physically impossible, so the move is refused rather than applied.
    Pure: does not mutate `positions`.
    """
    n = machine.rings
    s = machine.slots
    sign = [0] * n
    sign[ring] = 1
    grew = True
    while grew:
        grew = False
        for i in range(n - 1):
            j = i + 1
            if (sign[i] != 0) == (sign[j] != 0):
                continue
            if _would_collide(machine, positions, i, j, sign, direction):
                if sign[i] != 0:
                    sign[j] = -sign[i]
                else:
                    sign[i] = -sign[j]
                grew = True
    pos = list(positions)
    for r in range(n):
        if sign[r]:
            pos[r] = (pos[r] + direction * sign[r]) % s
    result = tuple(pos)
    if not is_valid(machine, result):
        return None
    return result


def start_is_scrambled(positions):
    """A start position that actually looks scrambled: no ring aligned to the
    target (slot 0) and no adjacent pair of rings sharing a position."""
    if 0 in positions:
        return False
    for i in range(len(positions) - 1):
        if positions[i] == positions[i + 1]:
            return False
    return True


def _has_single_undo(machine, pos, result, ring, d):
    """True if some single move maps `result` back to `pos`. The obvious
    counter-rotation is tried first; drag cascades usually reverse through
    the same chain, but not always, so all moves are checked."""
    if _apply(machine, result, ring, -d) == pos:
        return True
    for r2 in range(machine.rings):
        for d2 in (1, -1):
            if _apply(machine, result, r2, d2) == pos:
                return True
    return False


def reversible_moves(machine, positions):
    """Every (ring, direction, result) move from `positions` that some single
    move provably undoes. Applying only such moves preserves solvability: each
    step has a way back, so from a solvable state the result stays solvable.

    Atomic moves in general are NOT invertible (a catch that drags neighbours
    is not always undone by the counter-rotation), so each candidate's undo is
    found by checking all single moves from its result.
    """
    pos = tuple(positions)
    moves = []
    for ring in range(machine.rings):
        for d in (1, -1):
            result = _apply(machine, pos, ring, d)
            if result is None:
                continue
            if _has_single_undo(machine, pos, result, ring, d):
                moves.append((ring, d, result))
    return moves


def random_reversible_move(machine, positions, rng):
    """One uniformly-chosen reversible move as (ring, direction), or None.

    Tries candidate moves in a shuffled order and returns the first that
    verifies, so the caller pays for roughly one undo-check instead of
    enumerating the full reversible set — cheap enough for per-frame use on
    the badge. Distribution is uniform over candidates, which is close
    enough to uniform over reversible moves for game chaos.
    """
    pos = tuple(positions)
    candidates = []
    for ring in range(machine.rings):
        candidates.append((ring, 1))
        candidates.append((ring, -1))
    # Fisher-Yates with rng.randrange: MicroPython's random has no shuffle.
    for i in range(len(candidates) - 1, 0, -1):
        j = rng.randrange(i + 1)
        candidates[i], candidates[j] = candidates[j], candidates[i]
    for ring, d in candidates:
        result = _apply(machine, pos, ring, d)
        if result is None:
            continue
        if _has_single_undo(machine, pos, result, ring, d):
            return (ring, d)
    return None


def random_legal_move(machine, positions, rng):
    """One uniformly-chosen non-jamming move as (ring, direction), or None when
    the machine is jammed solid.

    Safe for the vortex burst because every shipped puzzle is verified
    dead-end-free: from any state reachable by play, solved is still reachable,
    so any legal move keeps the board solvable. Uses only rng.randrange, which
    MicroPython provides.
    """
    pos = tuple(positions)
    candidates = []
    for ring in range(machine.rings):
        candidates.append((ring, 1))
        candidates.append((ring, -1))
    # Fisher-Yates with rng.randrange: MicroPython's random has no shuffle.
    for i in range(len(candidates) - 1, 0, -1):
        j = rng.randrange(i + 1)
        candidates[i], candidates[j] = candidates[j], candidates[i]
    for ring, d in candidates:
        if _apply(machine, pos, ring, d) is not None:
            return (ring, d)
    return None


# Binary level catalogue (written by tools/generate_catalogue.py):
# header "CL2" + slots(1B) + rings(1B) + count(2B LE), then fixed-size records
# of dist(1B) + split(1B, 0 = not a composite) + ratchet_mask(1B, bit i set =
# ring i is ratcheted) + ratchet_dir(1B, bit i set = clockwise, clear =
# counter-clockwise) + one start byte per ring + per ring a little-endian
# 16-bit teeth bitmask for the inner and outer rims. Fixed records allow
# random access without parsing the file.
CATALOGUE_MAGIC = b"CL2"
_CATALOGUE_HEADER = struct.calcsize("<3sBBH")


def catalogue_info(data):
    """(slots, rings, puzzle_count) of a binary catalogue blob."""
    magic, slots, rings, count = struct.unpack_from("<3sBBH", data, 0)
    if magic != CATALOGUE_MAGIC:
        raise ValueError("not a level catalogue")
    return slots, rings, count


def _mask_teeth(mask, slots):
    return [s for s in range(slots) if (mask >> s) & 1]


def ratchet_masks(ratchet):
    """(ratcheted-rings mask, clockwise-direction mask) for a per-ring ratchet
    list. Direction bits for free rings stay clear so files round-trip."""
    mask = 0
    dirs = 0
    for i, r in enumerate(ratchet):
        if r:
            mask |= 1 << i
            if r > 0:
                dirs |= 1 << i
    return mask, dirs


def catalogue_entry(data, index):
    """Decode puzzle `index`:
    (inner_teeth, outer_teeth, start, dist, split, ratchet)."""
    slots, rings, count = catalogue_info(data)
    if not 0 <= index < count:
        raise IndexError(f"catalogue has {count} puzzles")
    record = 4 + 5 * rings
    off = _CATALOGUE_HEADER + index * record
    dist = data[off]
    split = data[off + 1]
    mask = data[off + 2]
    dirs = data[off + 3]
    start = list(data[off + 4 : off + 4 + rings])
    ratchet = []
    for i in range(rings):
        if (mask >> i) & 1:
            ratchet.append(1 if (dirs >> i) & 1 else -1)
        else:
            ratchet.append(0)
    inner = []
    outer = []
    pos = off + 4 + rings
    for _ in range(rings):
        inner_mask, outer_mask = struct.unpack_from("<HH", data, pos)
        inner.append(_mask_teeth(inner_mask, slots))
        outer.append(_mask_teeth(outer_mask, slots))
        pos += 4
    return inner, outer, start, dist, split, ratchet


class Game:
    """A machine plus the current ring positions: the mutable play state."""

    def __init__(self, machine, positions=None):
        self.machine = machine
        if positions is None:
            self.positions = [0] * machine.rings
        else:
            self.positions = list(positions)

    def rotate(self, ring, direction):
        """Rotate `ring` one step in `direction` (+1 CW, -1 CCW), turning any
        ring it catches the opposite way. Returns False and leaves the board
        untouched when the cascade would bind teeth into the same slot."""
        result = _apply(self.machine, self.positions, ring, direction)
        if result is None:
            return False
        self.positions = list(result)
        return True

    def is_solved(self):
        """True when every ring sits on slot 0, aligned with the target."""
        for p in self.positions:
            if p != 0:
                return False
        return True
