import unittest

from motion import GyroDial, TiltRatchet


class GyroDialTest(unittest.TestCase):
    def test_steady_twist_steps_once_per_slot(self):
        dial = GyroDial(deg_per_slot=30.0, deadband=10.0)
        # 60 deg/s for 1s of 50ms samples = 60 degrees = exactly 2 slots.
        steps = sum(dial.feed(60.0, 50) for _ in range(20))
        self.assertEqual(steps, 2)

    def test_counter_twist_steps_negative(self):
        dial = GyroDial(deg_per_slot=30.0, deadband=10.0)
        steps = sum(dial.feed(-60.0, 50) for _ in range(20))
        self.assertEqual(steps, -2)

    def test_deadband_rates_never_accumulate(self):
        dial = GyroDial(deg_per_slot=30.0, deadband=10.0)
        # The sim fake reads a constant 4-6 deg/s; a minute of it must not step.
        steps = sum(dial.feed(6.0, 50) for _ in range(1200))
        self.assertEqual(steps, 0)
        self.assertEqual(dial.accumulated, 0.0)

    def test_partial_slot_decays_when_twist_stops(self):
        dial = GyroDial(deg_per_slot=30.0, deadband=10.0, decay=45.0)
        for _ in range(8):  # 24 degrees accumulated, no step yet
            self.assertEqual(dial.feed(60.0, 50), 0)
        self.assertGreater(dial.accumulated, 0.0)
        for _ in range(20):  # a second of stillness drains it
            dial.feed(0.0, 50)
        self.assertEqual(dial.accumulated, 0.0)

    def test_remainder_carries_between_steps(self):
        dial = GyroDial(deg_per_slot=30.0, deadband=10.0)
        dial.feed(45.0 * 20, 50)  # one 45-degree sample: one step, 15 carried
        self.assertEqual(dial.accumulated, 15.0)


class TiltRatchetTest(unittest.TestCase):
    def _level(self, ratchet, pitch=0.0):
        # First sample calibrates the baseline and never fires.
        self.assertEqual(ratchet.feed(pitch), 0)

    def test_first_sample_sets_baseline_without_firing(self):
        ratchet = TiltRatchet(fire_deg=20.0, rearm_deg=10.0)
        # An upright badge (pitch ~90) must count as level, not as a tilt.
        self.assertEqual(ratchet.feed(90.0), 0)
        self.assertEqual(ratchet.feed(91.0), 0)

    def test_holding_a_tilt_fires_exactly_once(self):
        ratchet = TiltRatchet(fire_deg=20.0, rearm_deg=10.0)
        self._level(ratchet)
        self.assertEqual(ratchet.feed(25.0), 1)
        for _ in range(50):
            self.assertEqual(ratchet.feed(30.0), 0)

    def test_fires_relative_to_upright_baseline(self):
        ratchet = TiltRatchet(fire_deg=20.0, rearm_deg=10.0)
        self._level(ratchet, 90.0)
        self.assertEqual(ratchet.feed(115.0), 1)
        self.assertEqual(ratchet.feed(92.0), 0)  # rearm near baseline
        self.assertEqual(ratchet.feed(65.0), -1)

    def test_rearms_after_returning_level(self):
        ratchet = TiltRatchet(fire_deg=20.0, rearm_deg=10.0)
        self._level(ratchet)
        self.assertEqual(ratchet.feed(25.0), 1)
        self.assertEqual(ratchet.feed(5.0), 0)  # rearms, does not fire
        self.assertEqual(ratchet.feed(25.0), 1)

    def test_wobble_around_fire_threshold_cannot_repeat(self):
        ratchet = TiltRatchet(fire_deg=20.0, rearm_deg=10.0)
        self._level(ratchet)
        self.assertEqual(ratchet.feed(21.0), 1)
        for pitch in (19.0, 21.0, 15.0, 22.0):  # never back inside rearm zone
            self.assertEqual(ratchet.feed(pitch), 0)

    def test_opposite_tilt_fires_negative(self):
        ratchet = TiltRatchet(fire_deg=20.0, rearm_deg=10.0)
        self._level(ratchet)
        self.assertEqual(ratchet.feed(-25.0), -1)
        self.assertEqual(ratchet.feed(0.0), 0)
        self.assertEqual(ratchet.feed(-25.0), -1)

    def test_baseline_adapts_to_slow_posture_change(self):
        ratchet = TiltRatchet(fire_deg=20.0, rearm_deg=10.0, adapt_ms=1000.0)
        self._level(ratchet)
        # Drift to 8 degrees (inside rearm) and stay: baseline follows.
        for _ in range(100):
            self.assertEqual(ratchet.feed(8.0, 50), 0)
        self.assertAlmostEqual(ratchet.baseline, 8.0, delta=0.5)
        # A deliberate tilt relative to the NEW posture still fires.
        self.assertEqual(ratchet.feed(30.0, 50), 1)


if __name__ == "__main__":
    unittest.main()
