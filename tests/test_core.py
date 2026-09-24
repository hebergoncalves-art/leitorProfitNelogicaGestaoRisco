import unittest
from datetime import datetime, timedelta

from profit_alert.core import AlertGate, format_brl, parse_result, parse_threshold


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


if __name__ == "__main__":
    unittest.main()

