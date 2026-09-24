import unittest
from unittest.mock import patch

from profit_alert.windows import WindowTarget, list_profit_windows, target_state


class ProfitWindowSelectionTests(unittest.TestCase):
    def test_ignores_own_profit_warning_and_other_applications(self):
        windows = [
            WindowTarget(1, "LEITURA DO PROFIT INDISPONÍVEL", 10, "leitorprofit.exe"),
            WindowTarget(2, "ProfitPro - 5.0.4.26 - Registrado", 20, "profitchart.exe"),
            WindowTarget(3, "ProfitPro - documentação", 30, "chrome.exe"),
        ]
        with patch("profit_alert.windows.list_windows", return_value=windows):
            self.assertEqual(list_profit_windows(), [windows[1]])

    def test_rejects_reused_handle_from_wrong_process(self):
        with patch("profit_alert.windows.user32.IsWindow", return_value=True), patch(
            "profit_alert.windows.window_process", return_value=(10, "leitorprofit.exe")
        ):
            self.assertIn("não pertence", target_state(1))


if __name__ == "__main__":
    unittest.main()
