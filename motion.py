"""Pure MOTU (motion-control) input logic for Circuli.

No hardware imports: app.py feeds gyro samples in and steps come out, so
everything here runs and tests under plain CPython. Both MOTU gestures are
flicks — a sharp twist about the screen normal turns the selected ring, a
sharp tilt about the left-right axis steps the selection — detected by the
same rate ratchet, so slow movement never registers and the badge can be
repositioned freely between gestures.
"""


class FlickDial:
    """One ring step per sharp twist-and-stop about the screen normal.

    A step fires when the twist rate (deg/s) crosses fire_dps in either
    direction. The dial then stays quiet until the rate has remained inside
    rearm_dps for quiet_ms — so a flick registers exactly once however long
    it swings, wrist bounce-back cannot fire a phantom reverse step, and
    slow movement (repositioning the badge between flicks) never registers
    at all. The simulator's constant fake gyro sits far below rearm_dps.
    """

    def __init__(self, fire_dps=100.0, rearm_dps=30.0, quiet_ms=150.0):
        self.fire_dps = fire_dps
        self.rearm_dps = rearm_dps
        self.quiet_ms = quiet_ms
        self._armed = True
        self._quiet = 0.0

    def feed(self, rate, dt_ms):
        """Consume one gyro sample; return -1, 0, or +1 slot steps."""
        if self._armed:
            if rate >= self.fire_dps:
                self._armed = False
                self._quiet = 0.0
                return 1
            if rate <= -self.fire_dps:
                self._armed = False
                self._quiet = 0.0
                return -1
            return 0
        if abs(rate) <= self.rearm_dps:
            self._quiet += dt_ms
            if self._quiet >= self.quiet_ms:
                self._armed = True
        else:
            self._quiet = 0.0
        return 0


