import unittest
from datetime import datetime, timedelta

from profit_alert.core import ActionGate, AlertGate, format_brl, parse_result, parse_threshold


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


if __name__ == "__main__":
    unittest.main()
