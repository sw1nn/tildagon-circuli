"""Pure MOTU (motion-control) input logic for Circuli.

No hardware imports: app.py feeds IMU samples in and slot/selection steps
come out, so everything here runs and tests under plain CPython.
"""


class GyroDial:
    """Integrate twist rate (deg/s) about the screen normal into slot steps.

    Rates inside the deadband never integrate — instead the accumulator
    decays toward zero, so gyro noise, bias, and the simulator's constant
    fake readings cannot add up to a phantom step. Each full slot's worth of
    accumulated twist emits one step and carries the remainder.
    """

    def __init__(self, deg_per_slot=30.0, deadband=10.0, decay=45.0):
        self.deg_per_slot = deg_per_slot
        self.deadband = deadband
        self.decay = decay
        self.accumulated = 0.0

    def feed(self, rate, dt_ms):
        """Consume one gyro sample; return -1, 0, or +1 slot steps."""
        dt = dt_ms / 1000.0
        if abs(rate) < self.deadband:
            if self.accumulated > 0:
                self.accumulated = max(0.0, self.accumulated - self.decay * dt)
            else:
                self.accumulated = min(0.0, self.accumulated + self.decay * dt)
            return 0
        self.accumulated += rate * dt
        if self.accumulated >= self.deg_per_slot:
            self.accumulated -= self.deg_per_slot
            return 1
        if self.accumulated <= -self.deg_per_slot:
            self.accumulated += self.deg_per_slot
            return -1
        return 0


class TiltRatchet:
    """One selection step per deliberate tilt, with hysteresis.

    Tilt is measured relative to a baseline captured on the first sample, so
    any holding posture (flat on a table, upright on a lanyard) is 'level'.
    The baseline re-adapts slowly, but only while the badge is near level and
    the ratchet is armed, so posture drift is absorbed without eating
    deliberate tilts. Fires when relative pitch crosses fire_deg, then stays
    quiet until the badge returns within rearm_deg of the baseline — holding
    a tilt selects exactly once and threshold wobble cannot repeat-fire.
    """

    def __init__(self, fire_deg=20.0, rearm_deg=10.0, adapt_ms=4000.0):
        self.fire_deg = fire_deg
        self.rearm_deg = rearm_deg
        self.adapt_ms = adapt_ms
        self.baseline = None
        self._armed = True

    def feed(self, pitch_deg, dt_ms=0.0):
        """Consume one pitch sample (degrees); return -1, 0, or +1 steps."""
        if self.baseline is None:
            self.baseline = pitch_deg
            return 0
        rel = pitch_deg - self.baseline
        rel = ((rel + 180.0) % 360.0) - 180.0
        if self._armed:
            if rel >= self.fire_deg:
                self._armed = False
                return 1
            if rel <= -self.fire_deg:
                self._armed = False
                return -1
            if abs(rel) <= self.rearm_deg and self.adapt_ms > 0:
                self.baseline += rel * min(1.0, dt_ms / self.adapt_ms)
        elif abs(rel) <= self.rearm_deg:
            self._armed = True
        return 0
