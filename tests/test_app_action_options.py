import queue
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from profit_alert.app import ProfitAlertApp
from profit_alert.monitor import MonitorEvent


def variable(value):
    return Mock(get=Mock(return_value=value))


class ActionOptionTests(unittest.TestCase):
    def test_gain_option_rejects_empty_or_invalid_limit_when_checked(self):
        for value in ("", "  ", "abc"):
            with self.subTest(value=value):
                app = object.__new__(ProfitAlertApp)
                app.gain_auto_action_var = variable(True)
                app.gain_threshold_var = variable(value)
                with patch("profit_alert.app.messagebox.showerror") as showerror:
                    app._validate_gain_action_selection()
                app.gain_auto_action_var.set.assert_called_once_with(False)
                showerror.assert_called_once()

    def test_gain_option_accepts_positive_limit(self):
        app = object.__new__(ProfitAlertApp)
        app.gain_auto_action_var = variable(True)
        app.gain_threshold_var = variable("150,00")
        with patch("profit_alert.app.messagebox.showerror") as showerror:
            app._validate_gain_action_selection()
        app.gain_auto_action_var.set.assert_not_called()
        showerror.assert_not_called()

    @staticmethod
    def app_for_start(gain_limit, loss_action, gain_action):
        app = object.__new__(ProfitAlertApp)
        app.targets = {"Profit": SimpleNamespace(hwnd=1, pid=10, title="Profit")}
        app.window_var = variable("Profit")
        app.threshold_var = variable("-150,00")
        app.gain_threshold_var = variable(gain_limit)
        app.scan_height_var = variable("220")
        app.account_var = variable("")
        app.mode_var = variable("Automático: acessibilidade, depois OCR")
        app.auto_action_var = variable(loss_action)
        app.gain_auto_action_var = variable(gain_action)
        app.action_var = Mock()
        app.status_var = Mock()
        app.start_button = Mock()
        app.stop_button = Mock()
        app.auto_checkbox = Mock()
        app.gain_auto_checkbox = Mock()
        app.events = queue.Queue()
        app._log = Mock()
        return app

    def test_start_revalidates_gain_limit_after_field_is_cleared(self):
        app = self.app_for_start("", False, True)
        with patch("profit_alert.app.messagebox.showerror") as showerror, patch(
            "profit_alert.app.Monitor"
        ) as monitor:
            app.start_monitor()
        showerror.assert_called_once()
        self.assertIn("limite de ganho", showerror.call_args.args[1])
        monitor.assert_not_called()

    def test_start_passes_independent_options_and_disables_both_checkboxes(self):
        cases = (
            ("", False, False, "não acionado"),
            ("", True, False, "(perda)"),
            ("150,00", False, True, "(ganho)"),
            ("150,00", True, True, "(perda e ganho)"),
        )
        for gain_limit, loss_action, gain_action, state in cases:
            with self.subTest(loss=loss_action, gain=gain_action):
                app = self.app_for_start(gain_limit, loss_action, gain_action)
                with patch("profit_alert.app.Monitor") as monitor:
                    app.start_monitor()
                config = monitor.call_args.args[0]
                self.assertEqual(config.auto_action, loss_action)
                self.assertEqual(config.gain_auto_action, gain_action)
                self.assertEqual(config.gain_threshold_cents,
                                 15000 if gain_limit else None)
                self.assertIn(state, app.action_var.set.call_args.args[0])
                app.auto_checkbox.configure.assert_called_once_with(state="disabled")
                app.gain_auto_checkbox.configure.assert_called_once_with(state="disabled")

    def test_stop_reenables_both_action_options(self):
        app = object.__new__(ProfitAlertApp)
        app.events = queue.Queue()
        app.events.put(MonitorEvent("stopped", "Monitoramento parado."))
        app.root = Mock()
        app.start_button = Mock()
        app.stop_button = Mock()
        app.auto_checkbox = Mock()
        app.gain_auto_checkbox = Mock()
        app._log = Mock()
        app._drain_events()
        app.auto_checkbox.configure.assert_called_once_with(state="normal")
        app.gain_auto_checkbox.configure.assert_called_once_with(state="normal")


if __name__ == "__main__":
    unittest.main()
