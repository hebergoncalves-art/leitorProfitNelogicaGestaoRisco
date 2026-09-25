import unittest
from datetime import date, datetime, timedelta

from profit_alert.core import (
    ActionGate, AlertGate, DrawdownTracker, default_drawdown_cents, format_brl,
    parse_drawdown_threshold, parse_gain_threshold, parse_result, parse_threshold,
)


class MoneyParsingTests(unittest.TestCase):
    def test_reads_only_monetary_daily_result(self):
        self.assertEqual(parse_result("Res. Dia R$ -504,00"), -50400)
        self.assertEqual(parse_result("Res. Dia R$-150,00"), -15000)
        self.assertEqual(parse_result("Res Dia -R$150,00"), -15000)
        self.assertEqual(parse_result("Res. Dia R$ 1.234,56"), 123456)
        self.assertIsNone(parse_result("Res. Dia (%) -344,08 pts"))
        self.assertIsNone(parse_result("Res. Aberto R$ -504,00"))
        self.assertIsNone(parse_result("Res. Dia R$ --150,00"))

    def test_threshold_and_format(self):
        self.assertEqual(parse_threshold("-150"), -15000)
        self.assertEqual(parse_threshold("-R$ 150,00"), -15000)
        self.assertEqual(format_brl(-123456), "-R$ 1.234,56")
        with self.assertRaises(ValueError):
            parse_threshold("150,00")

    def test_optional_gain_threshold_accepts_only_positive_values(self):
        self.assertIsNone(parse_gain_threshold(""))
        self.assertIsNone(parse_gain_threshold("  "))
        self.assertEqual(parse_gain_threshold("150"), 15000)
        self.assertEqual(parse_gain_threshold("R$ 1.234,56"), 123456)
        for invalid in ("0", "0,00", "-0,00", "-150", "-R$ 150,00", "abc", "1.2,00"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_gain_threshold(invalid)

    def test_drawdown_threshold_and_default(self):
        self.assertEqual(default_drawdown_cents(-15000), 45000)
        self.assertIsNone(parse_drawdown_threshold("  "))
        self.assertEqual(parse_drawdown_threshold("450"), 45000)
        self.assertEqual(parse_drawdown_threshold("R$ 1.234,56"), 123456)
        for invalid in ("0", "-1", "abc", "1.2,00"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_drawdown_threshold(invalid)


class AlertGateTests(unittest.TestCase):
    def test_crossing_jump_and_one_alert_per_day(self):
        gate = AlertGate(-15000)
        now = datetime(2026, 9, 24, 10, 0)
        self.assertFalse(gate.observe(-14900, "OCR", now))
        self.assertTrue(gate.observe(-15200, "OCR", now + timedelta(seconds=1)))
        self.assertFalse(gate.observe(-20000, "OCR", now + timedelta(seconds=2)))
        self.assertTrue(gate.observe(-20000, "OCR", now + timedelta(days=1)))

    def test_exact_boundary_and_invalid_reading(self):
        gate = AlertGate(-15000, ocr_confirmations=2)
        now = datetime(2026, 9, 24, 10, 0)
        self.assertFalse(gate.observe(-15000, "OCR", now))
        self.assertFalse(gate.observe(None, "OCR", now))
        self.assertFalse(gate.observe(-15000, "OCR", now))
        self.assertTrue(gate.observe(-15000, "OCR", now))

    def test_gain_alert_at_or_above_limit_once_per_day(self):
        gate = AlertGate(15000, direction="gain")
        now = datetime(2026, 9, 24, 10, 0)
        self.assertFalse(gate.observe(14999, "OCR", now))
        self.assertTrue(gate.observe(15000, "OCR", now))
        self.assertFalse(gate.observe(20000, "OCR", now + timedelta(seconds=1)))
        self.assertFalse(gate.observe(14000, "OCR", now + timedelta(seconds=2)))
        self.assertFalse(gate.observe(15000, "OCR", now + timedelta(seconds=3)))
        self.assertTrue(gate.observe(20000, "OCR", now + timedelta(days=1)))

    def test_gain_can_alert_on_first_reading_and_resets_with_new_gate(self):
        now = datetime(2026, 9, 24, 10, 0)
        self.assertTrue(AlertGate(15000, direction="gain").observe(16000, "OCR", now))
        self.assertTrue(AlertGate(15000, direction="gain").observe(16000, "OCR", now))


class ActionGateTests(unittest.TestCase):
    def test_requires_above_then_two_distinct_fresh_captures(self):
        gate = ActionGate(-15000)
        self.assertFalse(gate.observe(-15100, 100, 100))  # iniciou abaixo
        self.assertFalse(gate.observe(-14900, 101, 101))
        self.assertFalse(gate.observe(-15000, 102, 102))
        self.assertFalse(gate.observe(-15200, 102, 103))  # mesmo quadro
        self.assertTrue(gate.observe(-15200, 104, 104))
        self.assertFalse(gate.observe(-16000, 105, 105))

    def test_invalid_or_stale_reading_resets_confirmation(self):
        gate = ActionGate(-15000)
        gate.observe(-14900, 100, 100)
        gate.observe(-15000, 101, 101)
        self.assertFalse(gate.observe(-15000, 102, 109))  # quadro antigo
        self.assertFalse(gate.observe(-15000, 110, 110))
        self.assertTrue(gate.observe(-15000, 111, 111))

    def test_gain_requires_crossing_and_two_distinct_captures(self):
        gate = ActionGate(15000, direction="gain")
        self.assertFalse(gate.observe(16000, 100, 100))  # iniciou acima
        self.assertFalse(gate.observe(14900, 101, 101))
        self.assertFalse(gate.observe(15000, 102, 102))  # igualdade conta
        self.assertFalse(gate.observe(15100, 102, 103))  # mesmo quadro
        self.assertTrue(gate.observe(15100, 104, 104))
        self.assertFalse(gate.observe(16000, 105, 105))

    def test_gain_stale_capture_resets_confirmation(self):
        gate = ActionGate(15000, direction="gain")
        gate.observe(14900, 100, 100)
        gate.observe(15000, 101, 101)
        self.assertFalse(gate.observe(15000, 102, 109))
        self.assertFalse(gate.observe(15000, 110, 110))
        self.assertTrue(gate.observe(15000, 111, 111))

    def test_deferred_action_requires_exit_and_new_crossing(self):
        gate = ActionGate(-15000)
        gate.observe(-14900, 100, 100)
        gate.observe(-15000, 101, 101)
        self.assertTrue(gate.observe(-15100, 102, 102))
        gate.defer_until_recross()
        self.assertFalse(gate.observe(-15200, 103, 103))
        self.assertFalse(gate.observe(-14900, 104, 104))
        self.assertFalse(gate.observe(-15000, 105, 105))
        self.assertTrue(gate.observe(-15100, 106, 106))


class DrawdownTrackerTests(unittest.TestCase):
    def test_positive_peak_drop_exact_limit_and_single_alert(self):
        tracker = DrawdownTracker(40000)
        today = date(2026, 9, 25)
        self.assertEqual(tracker.observe(-10000, today), (None, None, False))
        self.assertEqual(tracker.observe(80000, today), (80000, 0, False))
        self.assertEqual(tracker.observe(40000, today), (80000, 40000, True))
        self.assertEqual(tracker.observe(30000, today), (80000, 50000, False))
        self.assertEqual(tracker.observe(90000, today), (90000, 0, False))
        self.assertEqual(tracker.observe(40000, today), (90000, 50000, False))

    def test_new_day_resets_peak_and_alert(self):
        tracker = DrawdownTracker(40000)
        first = date(2026, 9, 25)
        tracker.observe(80000, first)
        tracker.observe(30000, first)
        self.assertEqual(tracker.observe(-10000, date(2026, 9, 26)),
                         (None, None, False))
        self.assertEqual(tracker.observe(50000, date(2026, 9, 26)),
                         (50000, 0, False))
        self.assertEqual(tracker.observe(10000, date(2026, 9, 26)),
                         (50000, 40000, True))


if __name__ == "__main__":
    unittest.main()
