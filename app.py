import math
import random
import time

import app
from app_components import YesNoDialog
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.patterndisplay.events import PatternDisable, PatternEnable
from tildagonos import tildagonos

from .game import Game, Machine, catalogue_entry, catalogue_info, reversible_moves
from .motion import FlickDial

try:
    import imu
except ImportError:
    imu = None

DEBUG = False           # centre readout of ring slots and current selection

START_RINGS = 3
MAX_RINGS = 8           # progression cap; matches the deepest catalogue tier

# Ring band. Radii are spread evenly from R_INNER to R_OUTER whatever the ring
# count; teeth, gaps, and strokes shrink together as rings are added.
R_INNER = 34
R_OUTER = 102
TOOTH_RATIO = 0.43      # tooth length as a fraction of ring spacing
MARKER_LEN = 12         # arc length of the yellow alignment section, px

RING_COLORS = [
    (1.0, 0.35, 0.35),
    (0.3, 1.0, 0.45),
    (0.4, 0.6, 1.0),
    (1.0, 0.75, 0.2),
    (0.85, 0.4, 1.0),
    (0.25, 0.9, 0.95),
    (1.0, 0.45, 0.75),
    (0.95, 0.85, 0.7),
]
INACTIVE_COLOR = (0.5, 0.5, 0.5)  # rings that are not currently selected

SOLVED_COLOR = (0.2, 1.0, 0.3)
ENGAGED_COLOR = (1.0, 1.0, 1.0)  # teeth currently catching an opposing tooth

HINT_COLOR = (1.0, 1.0, 1.0)  # edge glyphs reminding what the keys do
HINT_R = 115
HINT_BG = (0.2, 0.2, 0.2)     # tab behind each glyph
HINT_TAB_EDGE = 122           # just past the visible screen edge
HINT_TAB_INNER = 105          # how far the tab pokes into the play area
HINT_TAB_HALF_W = 19
HINT_TAB_CORNER = 5

LED_COUNT = 12
LED_TALLY_COLOR = (255, 210, 40)  # steady tally, one LED per solve
LED_CYCLE_STEP_MS = 120           # sweep speed; full cycle ~1.7s with the beat

# The ominous vortex: hammering the same rotation feeds it; at the limit it
# bursts and churns the rings with random reversible moves (teeth still
# latch, and reversibility keeps the mess provably solvable).
OMINOUS_LIMIT = 8       # same-move presses before the burst

# MOTU (motion controls): both gestures are sharp flicks read from the gyro
# alone, so holding posture never matters. Twist axis calibrated on hardware
# (2026-07-31): player-clockwise flick reads negative on gyro z. The tilt
# flick (top edge away/toward) rotates about the left-right axis, gyro y;
# its sign is calibrated the same way.
MOTU_TWIST_AXIS = 2     # gyro axis about the screen normal
MOTU_TWIST_SIGN = -1
MOTU_TILT_AXIS = 1      # gyro axis for top-edge away/toward flicks
MOTU_TILT_SIGN = 1      # calibrated: away-flick reads positive (select out)
OMINOUS_VISIBLE = 2     # presses before the vortex starts to show
BURST_MOVES = 6         # churn moves per burst
BURST_STEP_MS = 90      # churn speed, one move per step
LED_BURST_COLOR = (255, 30, 30)


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
        self.page = "help"  # launch flow: help -> mode chooser -> game
        self.motu = False
        self._twist = None
        self._tilt = None
        self.ring_count = START_RINGS
        self._catalogues = {}
        self.solve_count = 0
        self._leds_active = False
        self._cycle_ms = 0
        self._cycle_lit = -1
        self._new_puzzle()

    def _layout(self):
        """Derive ring geometry from the current ring count."""
        n = self.ring_count
        spacing = (R_OUTER - R_INNER) / (n - 1)
        self.radii = [R_INNER + i * spacing for i in range(n)]
        self.tooth_len = spacing * TOOTH_RATIO
        self.tooth_half_w = max(2.0, self.tooth_len * 0.35)
        self.ring_stroke = 3 if spacing >= 14 else 2

    def _load_catalogue(self, rings):
        # Levels are generated offline (tools/generate_catalogue.py) with
        # exact, exhaustively-verified solve distances; on-badge generation
        # was both too slow and too shallow. The raw binary blob is cached
        # and only the picked record is ever decoded.
        data = self._catalogues.get(rings)
        if data is None:
            path = __file__.rsplit("/", 1)[0] + "/levels_%d.lvl" % rings
            with open(path, "rb") as f:
                data = f.read()
            self._catalogues[rings] = data
        return data

    def _new_puzzle(self, ring_count=None):
        if ring_count is not None:
            self.ring_count = ring_count
        data = self._load_catalogue(self.ring_count)
        slots, _rings, count = catalogue_info(data)
        inner, outer, start, _dist, _split = catalogue_entry(
            data, random.randrange(count)
        )
        self.machine = Machine(inner, outer, slots)
        self.game = Game(self.machine, start)
        self._layout()
        self.selected = 0
        self.solved = False
        self._calm_vortex()
        self._burst_left = 0
        self._burst_ms = 0

    def _calm_vortex(self):
        self._repeat_move = None
        self._repeat_count = 0

    def _register_rotate(self, direction):
        """Track same-move spam. Returns False when the vortex consumes the
        press (burst triggered) instead of rotating."""
        move = (self.selected, direction)
        if move == self._repeat_move:
            self._repeat_count += 1
        else:
            self._repeat_move = move
            self._repeat_count = 1
        if self._repeat_count >= OMINOUS_LIMIT:
            self._start_burst()
            return False
        return True

    def _start_burst(self):
        self._calm_vortex()
        self._burst_left = BURST_MOVES
        self._burst_ms = 0
        for i in range(1, LED_COUNT + 1):
            tildagonos.leds[i] = LED_BURST_COLOR
        tildagonos.leds.write()

    def _advance_burst(self, delta):
        # One churn move per step so the damage is watchable. Reversible
        # moves only: the board stays solvable, however bad it looks.
        self._burst_ms += delta
        if self._burst_ms < BURST_STEP_MS:
            return
        self._burst_ms = 0
        options = reversible_moves(self.machine, self.game.positions)
        if not options:
            self._burst_left = 0
        else:
            ring, d, _result = options[random.randrange(len(options))]
            self.game.rotate(ring, d)
            self._burst_left -= 1
        if self._burst_left <= 0:
            self._show_tally()
            if self.game.is_solved():
                self._mark_solved()

    def _mark_solved(self):
        self.solved = True
        self.solve_count += 1
        self._cycle_ms = 0
        self._cycle_lit = -1

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
        if self._burst_left:
            # The vortex is churning; input waits until it is spent.
            self._advance_burst(delta)
            return True
        if self.page == "help":
            b = self.button_states
            if b.pressed(BUTTON_TYPES["CANCEL"]):
                eventbus.emit(PatternEnable())
                self._leds_active = False
                self.minimise()
                return True
            for name in ("CONFIRM", "UP", "DOWN", "LEFT", "RIGHT"):
                if b.pressed(BUTTON_TYPES[name]):
                    self.page = "mode"
                    self.button_states.clear()
                    break
            return True
        if self.page == "mode":
            # Dedicated chooser page: C plays with buttons, E plays MOTU
            # (flick gestures; buttons stay live as backup).
            b = self.button_states
            if b.pressed(BUTTON_TYPES["CANCEL"]):
                eventbus.emit(PatternEnable())
                self._leds_active = False
                self.minimise()
                return True
            if b.pressed(BUTTON_TYPES["CONFIRM"]):
                self.motu = False
                self.page = None
                self.button_states.clear()
            elif b.pressed(BUTTON_TYPES["LEFT"]) and imu is not None:
                self.motu = True
                self._twist = FlickDial()
                # Tilt is a flick-AND-RETURN gesture: measured returns swing
                # to ~-360 deg/s, so a higher fire threshold plus a long
                # quiet time keep the return stroke from firing a reverse
                # step (calibrated flicks run 300-900 deg/s).
                self._tilt = FlickDial(fire_dps=150.0, rearm_dps=40.0, quiet_ms=400.0)
                self.page = None
                self.button_states.clear()
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
            self._calm_vortex()
            self._request_new_puzzle()
            return True
        if self.solved:
            self._advance_win_cycle(delta)
            return True
        n = self.machine.rings
        if b.pressed(BUTTON_TYPES["UP"]):
            self.selected = (self.selected + 1) % n
            self._calm_vortex()
        if b.pressed(BUTTON_TYPES["DOWN"]):
            self.selected = (self.selected - 1) % n
            self._calm_vortex()
        if b.pressed(BUTTON_TYPES["CONFIRM"]):
            if self._register_rotate(+1):
                self.game.rotate(self.selected, +1)
        if b.pressed(BUTTON_TYPES["LEFT"]):
            if self._register_rotate(-1):
                self.game.rotate(self.selected, -1)
        if self.motu and imu is not None:
            self._update_motu(delta)
        if self.game.is_solved():
            self._mark_solved()
        return True

    def _update_motu(self, delta):
        # A sharp twist flick turns the selected ring; the vortex counts
        # flicks exactly like button presses, so repeat-flicking one way is
        # punished the same as mashing. A sharp tilt flick (top edge
        # away/toward) steps the selection outward/inward.
        gyro = imu.gyro_read()
        step = self._twist.feed(gyro[MOTU_TWIST_AXIS] * MOTU_TWIST_SIGN, delta)
        if step:
            if self._register_rotate(step):
                self.game.rotate(self.selected, step)
        moved = self._tilt.feed(gyro[MOTU_TILT_AXIS] * MOTU_TILT_SIGN, delta)
        if moved:
            self.selected = (self.selected + moved) % self.machine.rings
            self._calm_vortex()

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
        if self.page == "help":
            self._draw_help(ctx)
            ctx.restore()
            return
        if self.page == "mode":
            self._draw_mode(ctx)
            ctx.restore()
            return
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
        if not self.solved and (
            self._burst_left or self._repeat_count >= OMINOUS_VISIBLE
        ):
            self._draw_vortex(ctx)
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

    def _draw_help(self, ctx):
        # Launch instruction page; any game button dismisses it (F exits).
        ctx.text_align = ctx.CENTER
        ctx.text_baseline = ctx.MIDDLE
        ctx.rgb(1.0, 0.9, 0.2)
        ctx.font_size = 26
        ctx.begin_path()
        ctx.move_to(0, -74)
        ctx.text("CIRCULI")
        ctx.rgb(1.0, 1.0, 1.0)
        ctx.font_size = 14
        goal = (
            "Rotate rings until every",
            "yellow mark sits under",
            "the dotted line.",
            "Teeth catch and drag",
            "neighbouring rings!",
            "Don't make it angry tho!",
        )
        for i, line in enumerate(goal):
            if i == len(goal) - 1:
                ctx.rgb(0.9, 0.3, 0.4)
            ctx.begin_path()
            ctx.move_to(0, -52 + i * 15)
            ctx.text(line)
        ctx.rgb(0.7, 0.7, 0.7)
        ctx.font_size = 13
        controls = (
            "C / E  rotate ring",
            "A / D  select ring",
            "B  new puzzle    F  exit",
        )
        for i, line in enumerate(controls):
            ctx.begin_path()
            ctx.move_to(0, 44 + i * 14)
            ctx.text(line)
        ctx.rgb(0.45, 0.45, 0.45)
        ctx.font_size = 12
        ctx.begin_path()
        ctx.move_to(0, 92)
        ctx.text("press any key")

    def _draw_mode(self, ctx):
        # Dedicated control-scheme chooser, shown after the instructions.
        # Latin to match the theme (both ablatives: "by keys" / "by motion").
        ctx.text_align = ctx.CENTER
        ctx.text_baseline = ctx.MIDDLE
        ctx.rgb(1.0, 0.9, 0.2)
        ctx.font_size = 22
        ctx.begin_path()
        ctx.move_to(0, -70)
        ctx.text("ELIGE MODUM")
        ctx.rgb(0.55, 0.55, 0.55)
        ctx.font_size = 12
        ctx.begin_path()
        ctx.move_to(0, -50)
        ctx.text("(choose controls)")
        ctx.rgb(1.0, 1.0, 1.0)
        ctx.font_size = 16
        ctx.begin_path()
        ctx.move_to(0, -16)
        ctx.text("C   CLAVIBUS (buttons)")
        ctx.begin_path()
        ctx.move_to(0, 14)
        ctx.text("E   MOTU (flick & tilt)")
        ctx.rgb(0.7, 0.7, 0.7)
        ctx.font_size = 13
        motu_lines = (
            "flick the badge to turn,",
            "tilt-flick to select a ring",
        )
        for i, line in enumerate(motu_lines):
            ctx.begin_path()
            ctx.move_to(0, 40 + i * 15)
            ctx.text(line)
        ctx.rgb(0.45, 0.45, 0.45)
        ctx.font_size = 12
        ctx.begin_path()
        ctx.move_to(0, 78)
        ctx.text("buttons work in MOTU too")

    def _draw_vortex(self, ctx):
        # Something ominous in the centre gap. It grows with each repeated
        # press of the same rotation, and spins wildly while bursting.
        if self._burst_left:
            intensity = 1.0
            spin = self.t / 60.0
        else:
            intensity = self._repeat_count / OMINOUS_LIMIT
            spin = self.t / 400.0
        pulse = 0.5 + 0.5 * math.sin(self.t / 90.0)
        r = 4 + 16 * intensity
        ctx.rgb(0.25 * intensity + 0.2 * intensity * pulse, 0.02, 0.35 * intensity)
        ctx.begin_path()
        ctx.arc(0, 0, r, 0, 2 * math.pi, False)
        ctx.fill()
        ctx.rgb(0.5 + 0.4 * intensity * pulse, 0.1, 0.25)
        for k in range(5):
            angle = spin + k * (2 * math.pi / 5)
            _tooth(ctx, r, r + 3 + 3 * intensity * pulse, angle, 1.5 + 2 * intensity)

    def _draw_key_hints(self, ctx):
        # Compact reminders at the physical button angles: C (+30) rotates CW,
        # E (+150) rotates CCW, A (top) selects outward, D (bottom) inward.
        # Each glyph sits on a tab poking in from the screen edge — square at
        # the rim, rounded toward the centre — so the hints read as furniture
        # from outside the puzzle, drawn over the outer teeth.
        angles = (
            math.radians(30),
            math.radians(150),
            math.radians(-90),
            math.radians(90),
        )
        ctx.rgb(*HINT_BG)
        for a in angles:
            self._hint_tab(ctx, a)
        ctx.rgb(*HINT_COLOR)
        ctx.line_width = 2
        self._hint_arc_arrow(ctx, angles[0], cw=True)
        self._hint_arc_arrow(ctx, angles[1], cw=False)
        # Both chevrons point radially outward: at the top that reads as an
        # up arrow, at the bottom as a down arrow.
        self._hint_chevron(ctx, angles[2], outward=True)
        self._hint_chevron(ctx, angles[3], outward=True)

    def _hint_tab(self, ctx, angle):
        # Drawn in a rotated frame with the tab lying along +x: square corners
        # at the screen edge, quarter-circle corners on the inner end.
        edge, inner = HINT_TAB_EDGE, HINT_TAB_INNER
        w, rr = HINT_TAB_HALF_W, HINT_TAB_CORNER
        ctx.save()
        ctx.rotate(angle)
        ctx.begin_path()
        ctx.move_to(edge, -w)
        ctx.line_to(inner + rr, -w)
        ctx.arc(inner + rr, -w + rr, rr, -math.pi / 2, math.pi, True)
        ctx.line_to(inner, w - rr)
        ctx.arc(inner + rr, w - rr, rr, math.pi, math.pi / 2, True)
        ctx.line_to(edge, w)
        ctx.close_path()
        ctx.fill()
        ctx.restore()

    def _hint_arc_arrow(self, ctx, angle, cw):
        # A short arc concentric with the rings, with a filled arrowhead on
        # the end it points along (increasing angle = clockwise on screen).
        # Short enough that arc plus arrowhead stay within the tab's width.
        half = math.radians(5)
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

        ctx.line_width = self.ring_stroke + (2 if selected else 0)
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
        ctx.line_width = self.ring_stroke + (4 if i == self.selected else 2)
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
