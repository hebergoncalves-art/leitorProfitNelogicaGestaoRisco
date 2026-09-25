import queue
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from profit_alert.app import ProfitAlertApp, _beep
from profit_alert.monitor import MonitorEvent


def variable(value):
    return Mock(get=Mock(return_value=value))


class TracedVariable:
    def __init__(self, value):
        self.value = value
        self.callbacks = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        for callback in self.callbacks:
            callback()

    def trace_add(self, _mode, callback):
        self.callbacks.append(callback)


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
        app.drawdown_threshold_var = variable("450,00")
        app.scan_height_var = variable("220")
        app.account_var = variable("")
        app.mode_var = variable("Automático: acessibilidade, depois OCR")
        app.auto_action_var = variable(loss_action)
        app.gain_auto_action_var = variable(gain_action)
        app.drawdown_alert_var = variable(False)
        app.drawdown_auto_action_var = variable(False)
        app.suspension_enabled_var = variable(False)
        app.suspension_rows = []
        app.suspension_summary_var = variable("Nenhum intervalo configurado.")
        app.action_var = Mock()
        app.drawdown_state_var = Mock()
        app.status_var = Mock()
        app.start_button = Mock()
        app.stop_button = Mock()
        app.auto_checkbox = Mock()
        app.gain_auto_checkbox = Mock()
        app.drawdown_alert_checkbox = Mock()
        app.drawdown_auto_checkbox = Mock()
        app.suspension_checkbox = Mock()
        app.suspension_button = Mock()
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
        app.drawdown_alert_checkbox = Mock()
        app.drawdown_auto_checkbox = Mock()
        app.suspension_checkbox = Mock()
        app.suspension_button = Mock()
        app._log = Mock()
        app._drain_events()
        app.auto_checkbox.configure.assert_called_once_with(state="normal")
        app.gain_auto_checkbox.configure.assert_called_once_with(state="normal")
        app.drawdown_alert_checkbox.configure.assert_called_once_with(state="normal")
        app.drawdown_auto_checkbox.configure.assert_called_once_with(state="normal")
        app.suspension_checkbox.configure.assert_called_once_with(state="normal")
        app.suspension_button.configure.assert_called_once_with(state="normal")

    def test_suspension_intervals_can_be_added_edited_and_removed(self):
        app = object.__new__(ProfitAlertApp)
        app.suspension_rows = []
        app.suspension_summary_var = Mock()
        app._save_suspension_interval("10:00", "10:05")
        app._save_suspension_interval("15:00", "15:15")
        app._save_suspension_interval("10:01", "10:10", 0)
        self.assertEqual(app.suspension_rows, [("10:01", "10:10"), ("15:00", "15:15")])
        self.assertIn("10:01–10:10", app.suspension_summary_var.set.call_args.args[0])
        app._remove_suspension_interval(1)
        self.assertEqual(app.suspension_rows, [("10:01", "10:10")])

    def test_start_requires_intervals_when_suspension_enabled_and_merges_them(self):
        app = self.app_for_start("", True, False)
        app.suspension_enabled_var = variable(True)
        with patch("profit_alert.app.messagebox.showerror") as showerror, patch(
            "profit_alert.app.Monitor"
        ) as monitor:
            app.start_monitor()
        showerror.assert_called_once()
        monitor.assert_not_called()

        app.suspension_rows = [("10:00", "10:05"), ("10:04", "10:10"),
                               ("15:00", "15:15")]
        with patch("profit_alert.app.Monitor") as monitor:
            app.start_monitor()
        schedule = monitor.call_args.args[0].suspension
        self.assertEqual(schedule.intervals, ((600, 610), (900, 915)))
        app.suspension_checkbox.configure.assert_called_once_with(state="disabled")
        app.suspension_button.configure.assert_called_once_with(state="disabled")

    def test_drawdown_default_tracks_loss_until_manual_edit(self):
        app = object.__new__(ProfitAlertApp)
        app.threshold_var = TracedVariable("-150,00")
        app.drawdown_threshold_var = TracedVariable("450,00")
        app._drawdown_manually_edited = False
        app._updating_drawdown = False
        app.threshold_var.trace_add("write", app._update_drawdown_default)
        app.drawdown_threshold_var.trace_add("write", app._mark_drawdown_edited)
        app.threshold_var.set("-200,00")
        self.assertEqual(app.drawdown_threshold_var.get(), "600,00")
        self.assertFalse(app._drawdown_manually_edited)
        app.drawdown_threshold_var.set("700,00")
        self.assertTrue(app._drawdown_manually_edited)
        app.threshold_var.set("-300,00")
        self.assertEqual(app.drawdown_threshold_var.get(), "700,00")

    def test_drawdown_option_rejects_empty_or_invalid_limit_immediately(self):
        for value in ("", "0", "-50", "abc"):
            with self.subTest(value=value):
                app = object.__new__(ProfitAlertApp)
                app.drawdown_threshold_var = variable(value)
                selected = variable(True)
                with patch("profit_alert.app.messagebox.showerror") as showerror:
                    app._validate_drawdown_selection(selected)
                selected.set.assert_called_once_with(False)
                showerror.assert_called_once()

    def test_start_revalidates_drawdown_and_independent_modes(self):
        app = self.app_for_start("", False, False)
        app.drawdown_threshold_var = variable("")
        app.drawdown_alert_var = variable(True)
        with patch("profit_alert.app.messagebox.showerror") as showerror, patch(
            "profit_alert.app.Monitor"
        ) as monitor:
            app.start_monitor()
        showerror.assert_called_once()
        monitor.assert_not_called()

        for alert, action in ((True, False), (False, True), (True, True)):
            with self.subTest(alert=alert, action=action):
                app = self.app_for_start("", False, False)
                app.drawdown_alert_var = variable(alert)
                app.drawdown_auto_action_var = variable(action)
                with patch("profit_alert.app.Monitor") as monitor:
                    app.start_monitor()
                config = monitor.call_args.args[0]
                self.assertEqual(config.drawdown_threshold_cents, 45000)
                self.assertEqual(config.drawdown_alert, alert)
                self.assertEqual(config.drawdown_auto_action, action)
                app.drawdown_alert_checkbox.configure.assert_called_once_with(state="disabled")
                app.drawdown_auto_checkbox.configure.assert_called_once_with(state="disabled")
                self.assertIn("aguardando pico", app.drawdown_state_var.set.call_args.args[0])

    def test_drawdown_alert_has_distinct_popup_and_state(self):
        app = object.__new__(ProfitAlertApp)
        app.events = queue.Queue()
        app.events.put(MonitorEvent("drawdown_state", "Pico: R$ 800,00 · Recuo: R$ 500,00"))
        app.events.put(MonitorEvent("drawdown_alert", "Drawdown atingido"))
        app.drawdown_state_var = Mock()
        app.status_var = Mock()
        app.root = Mock()
        app._log = Mock()
        app._show_notice = Mock()
        app._drain_events()
        app.drawdown_state_var.set.assert_called_once()
        app._show_notice.assert_called_once_with(
            "LIMITE DE DRAWDOWN ATINGIDO", "Drawdown atingido\nConfira o Profit.",
            "drawdown",
        )

    def test_drawdown_has_warning_sound(self):
        with patch("profit_alert.app.threading.Thread") as thread, patch(
            "profit_alert.app.winsound.Beep"
        ) as beep:
            _beep("drawdown")
            thread.call_args.kwargs["target"]()
        self.assertEqual(beep.call_args_list, [call(650, 220), call(650, 220)])


if __name__ == "__main__":
    unittest.main()
