import unittest

from motion import FlickDial


class FlickDialTest(unittest.TestCase):
    def test_sharp_flick_fires_exactly_once(self):
        dial = FlickDial(fire_dps=100.0, rearm_dps=30.0, quiet_ms=150.0)
        self.assertEqual(dial.feed(180.0, 50), 1)
        for rate in (220.0, 150.0, 90.0, 40.0):  # rest of the swing
            self.assertEqual(dial.feed(rate, 50), 0)

    def test_slow_rotation_never_fires(self):
        dial = FlickDial(fire_dps=100.0, rearm_dps=30.0)
        # Repositioning the badge: sustained sub-threshold rotation.
        steps = sum(dial.feed(60.0, 50) for _ in range(200))
        self.assertEqual(steps, 0)

    def test_reposition_after_flick_is_free(self):
        dial = FlickDial(fire_dps=100.0, rearm_dps=30.0, quiet_ms=150.0)
        self.assertEqual(dial.feed(180.0, 50), 1)
        for _ in range(4):  # settle quietly, dial re-arms
            self.assertEqual(dial.feed(5.0, 50), 0)
        # Slowly rotating back stays below fire threshold: no reverse step.
        steps = sum(dial.feed(-60.0, 50) for _ in range(40))
        self.assertEqual(steps, 0)

    def test_bounce_back_cannot_fire_reverse(self):
        dial = FlickDial(fire_dps=100.0, rearm_dps=30.0, quiet_ms=150.0)
        self.assertEqual(dial.feed(180.0, 50), 1)
        # One transition frame inside the rearm band, then a hard bounce the
        # other way: quiet time was not met, so nothing fires.
        self.assertEqual(dial.feed(20.0, 50), 0)
        self.assertEqual(dial.feed(-140.0, 50), 0)

    def test_opposite_flick_fires_after_quiet(self):
        dial = FlickDial(fire_dps=100.0, rearm_dps=30.0, quiet_ms=150.0)
        self.assertEqual(dial.feed(180.0, 50), 1)
        for _ in range(4):
            self.assertEqual(dial.feed(0.0, 50), 0)
        self.assertEqual(dial.feed(-180.0, 50), -1)


if __name__ == "__main__":
    unittest.main()
