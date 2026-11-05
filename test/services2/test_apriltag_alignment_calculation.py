#!/usr/bin/env python3
"""离线算法检查：无 MQTT/GDK，不连接机器人、不下发任何运动。"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from apriltag_alignment_support import AlignmentTest, line_geometry, plan_correction


class CalculationTests(unittest.TestCase):
    def test_slope_and_prediction(self):
        geometry = line_geometry([{"id": 1, "center": [100, 200]},
                                  {"id": 2, "center": [300, 190]}])
        self.assertEqual(geometry["slope"], -0.05)
        plan = plan_correction([(0, -3), (2, -2)], 1.5, 4.5, 4.5)
        self.assertAlmostEqual(plan["turn"], 3.6)

    def test_overshoot_reverses_using_zero_crossing(self):
        plan = plan_correction([(0, -3), (2, -2), (6, 1)], 0.1, 4.5, 4.5)
        self.assertEqual(plan["mode"], "bracket_compensation")
        self.assertAlmostEqual(plan["turn"], -4 / 3)

    def test_no_forced_minimum_or_noise_amplification(self):
        small = plan_correction([(0, -2), (2, -.4)], 1.5, 4.5, 4.5)
        noisy = plan_correction([(0, -2), (2, -1.99)], .1, 4.5, 4.5)
        empty_budget = plan_correction([(0, -3), (2, -2)], 1.5, 4.5, 1)
        for plan in (small, noisy, empty_budget):
            self.assertIsNone(plan["turn"])

    def test_command_is_bounded(self):
        plan = plan_correction([(0, -10), (2, -9)], 1.5, 4.5, 3)
        self.assertEqual(plan["turn"], 3)

    def simulate_stage(self, stage, initial, observations, measured=None):
        # 仅替换 I/O，验证真实编排函数；这里的 move 只记录数值。
        runner = AlignmentTest.__new__(AlignmentTest)
        runner.args = SimpleNamespace(tolerance=.3, probe_sign=1)
        turns, records = [], []
        angles = iter(observations)
        actual = iter(measured) if measured else None

        def record_turn(_stage, turn):
            turns.append(turn)
            return next(actual) if actual else turn

        runner.move = record_turn
        runner.observe = lambda: next(angles)
        runner.record = lambda event, **data: records.append((event, data))
        with patch("builtins.input", side_effect=AssertionError("不得等待回车确认")), \
                patch("builtins.print"):
            final = runner.stage(stage, initial)
        return turns, final, records

    def test_overshoot_then_compensation_not_early_abort(self):
        turns, final, _ = self.simulate_stage("waist", -.9, [-.5, .6, .1])
        self.assertEqual(len(turns), 3)
        self.assertGreater(turns[1], .5)
        self.assertLess(turns[2], 0)
        self.assertLessEqual(sum(map(abs, turns)), 2)
        self.assertEqual(final, .1)

    def test_four_commands_max_and_reserve(self):
        for stage, initial, readings, measured, budget in (
            ("base", -4, [-3, -2, -1, -.2], [1, 1, 2, .85], 8),
            ("waist", -.9, [-.65, -.5, -.35, -.1], [.3, .5, .4, .25], 2),
        ):
            turns, _, _ = self.simulate_stage(stage, initial, readings, measured)
            self.assertEqual(len(turns), 4)
            self.assertLessEqual(sum(map(abs, turns)), budget)

    def test_same_side_worsening_stops(self):
        turns, _, _ = self.simulate_stage("base", -3, [-2, -3])
        self.assertEqual(len(turns), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
