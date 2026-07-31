import math
import random
import time

import app
from app_components import YesNoDialog
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.patterndisplay.events import PatternDisable, PatternEnable
from tildagonos import tildagonos

from .game import Game, random_machine, start_is_scrambled

DEBUG = False           # centre readout of ring slots and current selection

START_RINGS = 3
MAX_RINGS = 5           # progression cap; the 240px display gets cramped above

# Ring band. Radii are spread evenly from R_INNER to R_OUTER whatever the ring
# count; teeth and gaps shrink together as rings are added.
R_INNER = 40
R_OUTER = 100
TOOTH_RATIO = 0.43      # tooth length as a fraction of ring spacing
MARKER_LEN = 12         # arc length of the yellow alignment section, px

RING_COLORS = [
    (1.0, 0.35, 0.35),
    (0.3, 1.0, 0.45),
    (0.4, 0.6, 1.0),
    (1.0, 0.75, 0.2),
    (0.85, 0.4, 1.0),
]
INACTIVE_COLOR = (0.5, 0.5, 0.5)  # rings that are not currently selected

SOLVED_COLOR = (0.2, 1.0, 0.3)
ENGAGED_COLOR = (1.0, 1.0, 1.0)  # teeth currently catching an opposing tooth

HINT_COLOR = (1.0, 1.0, 1.0)  # edge glyphs reminding what the keys do
HINT_R = 115

LED_COUNT = 12
LED_TALLY_COLOR = (255, 210, 40)  # steady tally, one LED per solve
LED_CYCLE_STEP_MS = 120           # sweep speed; full cycle ~1.7s with the beat

# Victory arpeggio, one note as every third LED lights during the sweep.
VICTORY_NOTES = ("C5", "E5", "G5", "C6")


def _led_wheel(i, n=LED_COUNT):
    """Rainbow colour for LED i of n: hue i/n around the colour wheel."""
    h = (i % n) * 6.0 / n
    sector = int(h)
    x = int(255 * (h - sector))
    if sector == 0:
        return (255, x, 0)
    if sector == 1:
        return (255 - x, 255, 0)
    if sector == 2:
        return (0, 255, x)
    if sector == 3:
        return (0, 255 - x, 255)
    if sector == 4:
        return (x, 0, 255)
    return (255, 0, 255 - x)


def _slot_angle(machine, v):
    """Absolute slot value -> screen angle, with slot 0 at the top and CW = +."""
    return -math.pi / 2 + v * (2 * math.pi / machine.slots)


def _circular_dist(a, b, slots):
    d = (a - b) % slots
    return min(d, slots - d)


def _tooth(ctx, r0, r1, angle, half_w):
    """Fill a gear tooth: a parallel-sided block running radially r0 -> r1,
    offset a constant `half_w` px either side of the radius line."""
    ca, sa = math.cos(angle), math.sin(angle)
    px, py = -sa * half_w, ca * half_w
    ctx.begin_path()
    ctx.move_to(r0 * ca - px, r0 * sa - py)
    ctx.line_to(r0 * ca + px, r0 * sa + py)
    ctx.line_to(r1 * ca + px, r1 * sa + py)
    ctx.line_to(r1 * ca - px, r1 * sa - py)
    ctx.close_path()
    ctx.fill()




class Circuli(app.App):
    """Circuli: rotate the interlocking rings so every alignment marker points
    to the top."""

    def __init__(self):
        super().__init__()
        self.button_states = Buttons(self)
        random.seed(time.ticks_ms())
        self.t = 0
        self.dialog = None
        self.ring_count = START_RINGS
        self.solve_count = 0
        self._leds_active = False
        self._cycle_ms = 0
        self._cycle_lit = -1
        self._synth = None
        self._new_puzzle()

    def _layout(self):
        """Derive ring geometry from the current ring count."""
        n = self.ring_count
        spacing = (R_OUTER - R_INNER) / (n - 1)
        self.radii = [R_INNER + i * spacing for i in range(n)]
        self.tooth_len = spacing * TOOTH_RATIO
        self.tooth_half_w = max(2.0, self.tooth_len * 0.35)

    def _new_puzzle(self, ring_count=None):
        if ring_count is not None:
            self.ring_count = ring_count
        # Reroll machines whose walk could not produce a properly scrambled
        # start (no ring on the target, no adjacent pair mutually aligned).
        while True:
            self.machine = random_machine(random, self.ring_count)
            self.game = Game(self.machine)
            self.game.scramble(random)
            if start_is_scrambled(self.game.positions):
                break
        self._layout()
        self.selected = 0
        self.solved = False

    def _request_new_puzzle(self):
        # A solved board advances the progression with nothing to lose (B
        # skips the victory sweep); mid-game a scramble throws away progress,
        # so ask first.
        if self.solved:
            self._new_puzzle(min(self.ring_count + 1, MAX_RINGS))
            self._show_tally()
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
        if not self._leds_active:
            # Take the LEDs from the OS pattern on first focus and again
            # whenever we come back from being minimised.
            eventbus.emit(PatternDisable())
            self._show_tally()
            self._leds_active = True
        if self.dialog is not None:
            # The open dialog owns the buttons; its handlers close it.
            return True
        b = self.button_states
        # Rotation lives on CONFIRM/LEFT (physical C bottom-right / E
        # bottom-left), matching the rotation direction to the buttons'
        # positions on the hexagon. New-puzzle is on RIGHT (physical B).
        if b.pressed(BUTTON_TYPES["CANCEL"]):
            eventbus.emit(PatternEnable())
            self._leds_active = False
            self.minimise()
            return True
        if b.pressed(BUTTON_TYPES["RIGHT"]):
            self._request_new_puzzle()
            return True
        if self.solved:
            self._advance_win_cycle(delta)
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
            self.solve_count += 1
            self._cycle_ms = 0
            self._cycle_lit = -1
        return True

    def _ensure_audio(self):
        # Lazily build a synth voice. Audio must never take the game down, so
        # any failure (no speaker, bl00mbox API drift) marks the synth broken
        # and the tune simply doesn't play.
        if self._synth is not None:
            return
        try:
            import bl00mbox

            self._blm = bl00mbox.Channel("Circuli")
            self._synth = self._blm.new(bl00mbox.patches.tinysynth)
            self._synth.signals.output = self._blm.mixer
        except Exception:
            self._synth = False

    def _play_note(self, name):
        if not self._synth:
            return
        try:
            self._synth.signals.pitch.tone = name
            self._synth.signals.trigger.start()
        except Exception:
            self._synth = False

    def _show_tally(self):
        # Steady display: one lit LED per puzzle solved this session.
        lit = min(self.solve_count, LED_COUNT)
        for i in range(1, LED_COUNT + 1):
            tildagonos.leds[i] = LED_TALLY_COLOR if i <= lit else (0, 0, 0)
        tildagonos.leds.write()

    def _advance_win_cycle(self, delta):
        # Victory sweep: paint the LEDs rainbow once around the hexagon, hold
        # a beat, then advance to the next level automatically.
        self._cycle_ms += delta
        step = int(self._cycle_ms // LED_CYCLE_STEP_MS)
        if step > LED_COUNT + 2:
            self._new_puzzle(min(self.ring_count + 1, MAX_RINGS))
            self._show_tally()
            return
        lit = min(step, LED_COUNT)
        if lit != self._cycle_lit:
            self._cycle_lit = lit
            if lit < LED_COUNT and lit % 3 == 0:
                self._ensure_audio()
                self._play_note(VICTORY_NOTES[lit // 3])
            for i in range(1, LED_COUNT + 1):
                tildagonos.leds[i] = _led_wheel(i - 1) if i <= lit else (0, 0, 0)
            tildagonos.leds.write()

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
        if not self.solved:
            self._draw_key_hints(ctx)
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

    def _draw_key_hints(self, ctx):
        # Compact reminders at the physical button angles: C (+30) rotates CW,
        # E (+150) rotates CCW, A (top) selects outward, D (bottom) inward.
        ctx.rgb(*HINT_COLOR)
        ctx.line_width = 2
        self._hint_arc_arrow(ctx, math.radians(30), cw=True)
        self._hint_arc_arrow(ctx, math.radians(150), cw=False)
        # Both chevrons point radially outward: at the top that reads as an
        # up arrow, at the bottom as a down arrow.
        self._hint_chevron(ctx, math.radians(-90), outward=True)
        self._hint_chevron(ctx, math.radians(90), outward=True)

    def _hint_arc_arrow(self, ctx, angle, cw):
        # A short arc concentric with the rings, with a filled arrowhead on
        # the end it points along (increasing angle = clockwise on screen).
        half = math.radians(8)
        ctx.begin_path()
        ctx.arc(0, 0, HINT_R, angle - half, angle + half, False)
        ctx.stroke()
        s = 1 if cw else -1
        tip = angle + half * s
        ca, sa = math.cos(tip), math.sin(tip)
        tx, ty = HINT_R * ca, HINT_R * sa
        ctx.begin_path()
        ctx.move_to(tx - sa * 5 * s, ty + ca * 5 * s)
        ctx.line_to(tx + ca * 3, ty + sa * 3)
        ctx.line_to(tx - ca * 3, ty - sa * 3)
        ctx.close_path()
        ctx.fill()

    def _hint_chevron(self, ctx, angle, outward):
        # A stroked chevron pointing radially out (select outward) or in.
        ca, sa = math.cos(angle), math.sin(angle)
        px, py = -sa, ca
        tip_r = HINT_R + 4 if outward else HINT_R - 4
        base_r = HINT_R - 4 if outward else HINT_R + 4
        ctx.begin_path()
        ctx.move_to(base_r * ca + px * 5, base_r * sa + py * 5)
        ctx.line_to(tip_r * ca, tip_r * sa)
        ctx.line_to(base_r * ca - px * 5, base_r * sa - py * 5)
        ctx.stroke()

    def _draw_top_reference(self, ctx):
        # Dotted target line at 12 o'clock spanning the ring band, drawn under
        # the rings; the puzzle is solved when every marker points along it.
        ctx.rgb(1.0, 0.9, 0.2)
        ctx.line_width = 2
        dash, gap = 3, 4
        y = -self.radii[0]
        y_end = -self.radii[-1]
        while y > y_end:
            e = max(y - dash, y_end)
            ctx.begin_path()
            ctx.move_to(0, y)
            ctx.line_to(0, e)
            ctx.stroke()
            y -= dash + gap

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
        r = self.radii[i]
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
            _tooth(ctx, r, r + self.tooth_len, _slot_angle(m, p + off), self.tooth_half_w)
        for off in m.inner_teeth[i]:
            tc = ENGAGED_COLOR if (not self.solved and off in engaged_inner) else color
            ctx.rgb(*tc)
            _tooth(ctx, r - self.tooth_len, r, _slot_angle(m, p + off), self.tooth_half_w)

    def _draw_marker(self, ctx, i):
        # Alignment marker (ring-frame offset 0): a yellow section of the ring
        # itself, MARKER_LEN px along the arc whatever the radius. Solved when
        # every section sits under the dotted target line.
        r = self.radii[i]
        p = self.game.positions[i]
        a = _slot_angle(self.machine, p)
        half = MARKER_LEN / (2 * r)
        ctx.rgb(1.0, 0.9, 0.2)
        ctx.line_width = (5 if i == self.selected else 3) + 2
        ctx.begin_path()
        ctx.arc(0, 0, r, a - half, a + half, False)
        ctx.stroke()

    def _draw_cracked(self, ctx):
        # Knockout disc: the text spans the rings, so clear a circle behind
        # it to keep it legible.
        ctx.rgb(0, 0, 0)
        ctx.begin_path()
        ctx.arc(0, 0, 66, 0, 2 * math.pi, False)
        ctx.fill()
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
