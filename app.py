import math
import random
import time

import app
from app_components import YesNoDialog
from events.input import Buttons, BUTTON_TYPES

from .game import Game, default_machine

# Ring radii (innermost first). Gaps are sized so adjacent rings' teeth reach
# toward each other and nearly meet, making meshing visible.
RING_RADII = [40, 70, 100]
RING_COLORS = [(1.0, 0.35, 0.35), (0.3, 1.0, 0.45), (0.4, 0.6, 1.0)]
INACTIVE_COLOR = (0.5, 0.5, 0.5)  # rings that are not currently selected

DEBUG = False           # centre readout of ring slots and current selection

TOOTH_LEN = 13          # radial length of a tooth (nearly half the 30px gap)
TOOTH_HALF_W = 0.12     # angular half-width of a tooth, radians
MARKER_SIZE = 11
SOLVED_COLOR = (0.2, 1.0, 0.3)
ENGAGED_COLOR = (1.0, 1.0, 1.0)  # teeth currently catching an opposing tooth


def _slot_angle(machine, v):
    """Absolute slot value -> screen angle, with slot 0 at the top and CW = +."""
    return -math.pi / 2 + v * (2 * math.pi / machine.slots)


def _circular_dist(a, b, slots):
    d = (a - b) % slots
    return min(d, slots - d)


def _tooth(ctx, r0, r1, angle, half_w):
    """Fill a chunky tooth: a radial block from r0 to r1, `half_w` wide."""
    a0, a1 = angle - half_w, angle + half_w
    ctx.begin_path()
    ctx.move_to(r0 * math.cos(a0), r0 * math.sin(a0))
    ctx.line_to(r0 * math.cos(a1), r0 * math.sin(a1))
    ctx.line_to(r1 * math.cos(a1), r1 * math.sin(a1))
    ctx.line_to(r1 * math.cos(a0), r1 * math.sin(a0))
    ctx.close_path()
    ctx.fill()


def _triangle(ctx, r_base, angle, size, outward=True):
    """Fill a triangle at `angle` whose tip points radially out (or in)."""
    ca, sa = math.cos(angle), math.sin(angle)
    tip_r = r_base + size if outward else r_base - size
    tx, ty = tip_r * ca, tip_r * sa
    hw = size * 0.7
    b1x, b1y = r_base * ca - sa * hw, r_base * sa + ca * hw
    b2x, b2y = r_base * ca + sa * hw, r_base * sa - ca * hw
    ctx.begin_path()
    ctx.move_to(tx, ty)
    ctx.line_to(b1x, b1y)
    ctx.line_to(b2x, b2y)
    ctx.close_path()
    ctx.fill()



class Circuli(app.App):
    """Circuli: rotate the interlocking rings so every alignment marker points
    to the top."""

    def __init__(self):
        super().__init__()
        self.button_states = Buttons(self)
        self.machine = default_machine()
        self.game = Game(self.machine)
        random.seed(time.ticks_ms())
        self.selected = 0
        self.solved = False
        self.t = 0
        self.dialog = None
        self._new_puzzle()

    def _new_puzzle(self):
        self.game.scramble(random)
        self.solved = False

    def _request_new_puzzle(self):
        # Mid-game a scramble throws away progress, so ask first; a solved
        # board has nothing to lose.
        if self.solved:
            self._new_puzzle()
            return
        self.dialog = YesNoDialog(
            "New puzzle?",
            self,
            on_yes=self._scramble_confirmed,
            on_no=self._close_dialog,
        )

    def _scramble_confirmed(self):
        self._new_puzzle()
        self._close_dialog()

    def _close_dialog(self):
        self.dialog = None
        # Presses that answered the dialog must not leak into game input.
        self.button_states.clear()

    def update(self, delta):
        self.t += delta
        if self.dialog is not None:
            # The open dialog owns the buttons; its handlers close it.
            return True
        b = self.button_states
        # Rotation lives on CONFIRM/LEFT (physical C bottom-right / E
        # bottom-left), matching the rotation direction to the buttons'
        # positions on the hexagon. New-puzzle is on RIGHT (physical B).
        if b.pressed(BUTTON_TYPES["CANCEL"]):
            self.minimise()
            return True
        if b.pressed(BUTTON_TYPES["RIGHT"]):
            self._request_new_puzzle()
            return True
        if self.solved:
            return True
        n = self.machine.rings
        if b.pressed(BUTTON_TYPES["UP"]):
            self.selected = (self.selected + 1) % n
        if b.pressed(BUTTON_TYPES["DOWN"]):
            self.selected = (self.selected - 1) % n
        if b.pressed(BUTTON_TYPES["CONFIRM"]):
            self.game.rotate(self.selected, +1)
        if b.pressed(BUTTON_TYPES["LEFT"]):
            self.game.rotate(self.selected, -1)
        if self.game.is_solved():
            self.solved = True
        return True

    def _engaged_teeth(self):
        """Return (engaged_outer, engaged_inner): per-ring sets of tooth
        offsets that sit within one slot of an opposing tooth in a shared gap
        (currently catching)."""
        m = self.machine
        pos = self.game.positions
        s = m.slots
        engaged_outer = [set() for _ in range(m.rings)]
        engaged_inner = [set() for _ in range(m.rings)]
        for i in range(m.rings - 1):
            j = i + 1
            for o in m.outer_teeth[i]:
                oa = (pos[i] + o) % s
                for k in m.inner_teeth[j]:
                    ia = (pos[j] + k) % s
                    if _circular_dist(oa, ia, s) <= 1:
                        engaged_outer[i].add(o)
                        engaged_inner[j].add(k)
        return engaged_outer, engaged_inner

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        self._draw_top_reference(ctx)
        engaged_outer, engaged_inner = self._engaged_teeth()
        for i in range(self.machine.rings):
            self._draw_ring(ctx, i, engaged_outer[i], engaged_inner[i])
        # Draw every alignment indicator last, so notches from neighbouring
        # rings can never obscure it.
        for i in range(self.machine.rings):
            self._draw_marker(ctx, i)
        if self.solved:
            self._draw_cracked(ctx)
        elif DEBUG:
            self._draw_debug(ctx)
        if self.dialog is not None:
            self.dialog.draw(ctx)
        ctx.restore()

    def _draw_debug(self, ctx):
        # Centre readout: the selection index, then one line per ring (r0 =
        # innermost) with its current slot. Each ring line is tinted with the
        # exact colour _draw_ring used for it and '>' marks self.selected, so
        # any drift between the selection state and the highlighted ring is
        # directly visible.
        ctx.font_size = 11
        # Real badge ctx wants the enum constants; strings only work in the sim.
        ctx.text_align = ctx.CENTER
        ctx.text_baseline = ctx.MIDDLE
        n = self.machine.rings
        y = -5.5 * n
        ctx.rgb(1.0, 1.0, 1.0)
        ctx.begin_path()
        ctx.move_to(0, y)
        ctx.text("sel %d" % self.selected)
        for i in range(n):
            y += 11
            selected = i == self.selected
            ctx.rgb(*self._ring_color(i, selected))
            ctx.begin_path()
            ctx.move_to(0, y)
            ctx.text("%sr%d %d" % (">" if selected else "", i, self.game.positions[i]))

    def _draw_top_reference(self, ctx):
        # Fixed target marker at the top, pointing down toward the rings.
        angle = _slot_angle(self.machine, 0)
        r = RING_RADII[-1] + TOOTH_LEN + MARKER_SIZE + 6
        ctx.rgb(1.0, 0.9, 0.2)
        _triangle(ctx, r, angle, MARKER_SIZE, outward=False)

    def _ring_color(self, i, selected):
        if self.solved:
            pulse = 0.5 + 0.5 * math.sin(self.t / 150.0)
            return (SOLVED_COLOR[0], 0.4 + 0.6 * pulse, SOLVED_COLOR[2] * pulse + 0.2)
        # Only the selected ring is coloured; the rest are grey.
        if selected:
            return RING_COLORS[i]
        return INACTIVE_COLOR

    def _draw_ring(self, ctx, i, engaged_outer, engaged_inner):
        m = self.machine
        p = self.game.positions[i]
        r = RING_RADII[i]
        selected = i == self.selected
        color = self._ring_color(i, selected)

        ctx.line_width = 5 if selected else 3
        ctx.rgb(*color)
        ctx.begin_path()
        ctx.arc(0, 0, r, 0, 2 * math.pi, False)
        ctx.stroke()

        for off in m.outer_teeth[i]:
            tc = ENGAGED_COLOR if (not self.solved and off in engaged_outer) else color
            ctx.rgb(*tc)
            _tooth(ctx, r, r + TOOTH_LEN, _slot_angle(m, p + off), TOOTH_HALF_W)
        for off in m.inner_teeth[i]:
            tc = ENGAGED_COLOR if (not self.solved and off in engaged_inner) else color
            ctx.rgb(*tc)
            _tooth(ctx, r - TOOTH_LEN, r, _slot_angle(m, p + off), TOOTH_HALF_W)

    def _draw_marker(self, ctx, i):
        # Alignment marker (ring-frame offset 0), tip pointing outward.
        r = RING_RADII[i]
        p = self.game.positions[i]
        ctx.rgb(*self._ring_color(i, i == self.selected))
        _triangle(ctx, r + TOOTH_LEN + 3, _slot_angle(self.machine, p), MARKER_SIZE, outward=True)

    def _draw_cracked(self, ctx):
        ctx.rgb(*SOLVED_COLOR)
        ctx.font_size = 24
        ctx.text_align = ctx.CENTER
        ctx.text_baseline = ctx.MIDDLE
        ctx.begin_path()
        ctx.move_to(0, -15)
        ctx.text("CIRCULI")
        ctx.begin_path()
        ctx.move_to(0, 15)
        ctx.text("COMPLETI!")
