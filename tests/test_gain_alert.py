import queue
import time
import unittest
from unittest.mock import Mock, call, patch

from profit_alert.app import ProfitAlertApp, _beep
from profit_alert.monitor import Monitor, MonitorConfig, MonitorEvent
from profit_alert.readers import Reading


class GainAlertTests(unittest.TestCase):
    def test_gain_is_disabled_by_default(self):
        events = queue.Queue()
        monitor = Monitor(MonitorConfig(1, -15000), events)
        monitor._observe(Reading(20000, "OCR", "Res. Dia", time.time(), "Sim 123"))
        self.assertNotIn("gain_alert", [event.kind for event in list(events.queue)])

    def test_gain_and_loss_alerts_are_independent(self):
        events = queue.Queue()
        monitor = Monitor(MonitorConfig(1, -15000, gain_threshold_cents=15000), events)
        now = time.time()
        for cents in (-15000, 15000, -20000, 20000):
            monitor._observe(Reading(cents, "OCR", "Res. Dia", now, "Sim 123"))
        kinds = [event.kind for event in list(events.queue)]
        self.assertEqual(kinds.count("alert"), 1)
        self.assertEqual(kinds.count("gain_alert"), 1)

    def test_gain_alert_does_not_reserve_or_execute_action(self):
        events = queue.Queue()
        config = MonitorConfig(1, -15000, auto_action=True, pid=10,
                               gain_threshold_cents=15000)
        monitor = Monitor(config, events)
        now = time.time()
        with patch("profit_alert.monitor.ActionStore.reserve") as reserve, patch(
            "profit_alert.monitor.ProfitAction.execute"
        ) as execute:
            monitor._observe(Reading(15000, "OCR", "Res. Dia", now, "Sim 123"),
                             object(), object())
            monitor._observe(Reading(20000, "OCR", "Res. Dia", now + 1, "Sim 123"),
                             object(), object())
        kinds = [event.kind for event in list(events.queue)]
        self.assertEqual(kinds.count("gain_alert"), 1)
        self.assertNotIn("alert", kinds)
        reserve.assert_not_called()
        execute.assert_not_called()

    def test_account_filter_applies_to_gain(self):
        events = queue.Queue()
        monitor = Monitor(MonitorConfig(1, -15000, expected_account="123",
                                        gain_threshold_cents=15000), events)
        monitor._observe(Reading(20000, "OCR", "Res. Dia", time.time(), "Sim 456"))
        self.assertNotIn("gain_alert", [event.kind for event in list(events.queue)])

    def test_gain_event_opens_its_own_popup(self):
        app = object.__new__(ProfitAlertApp)
        app.events = queue.Queue()
        app.events.put(MonitorEvent("gain_alert", "Limite de ganho atingido: R$ 150,00"))
        app.status_var = Mock()
        app.root = Mock()
        app._log = Mock()
        app._show_notice = Mock()
        app._drain_events()
        app._show_notice.assert_called_once_with(
            "LIMITE DE GANHO ATINGIDO",
            "Limite de ganho atingido: R$ 150,00\nConfira o Profit.", "gain",
        )

    def test_gain_sound_is_distinct_from_loss(self):
        with patch("profit_alert.app.threading.Thread") as thread, patch(
            "profit_alert.app.winsound.Beep"
        ) as beep:
            _beep("gain")
            thread.call_args.kwargs["target"]()
            self.assertEqual(beep.call_args_list,
                             [call(700, 180), call(900, 180), call(1100, 180)])
            beep.reset_mock()
            _beep("loss")
            thread.call_args.kwargs["target"]()
            self.assertEqual(beep.call_args_list, [call(1250, 350)] * 3)


if __name__ == "__main__":
    unittest.main()
