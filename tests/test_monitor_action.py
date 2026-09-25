import queue
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from profit_alert.action_store import ActionStore
from profit_alert.monitor import Monitor, MonitorConfig
from profit_alert.readers import Reading


class MonitorActionTests(unittest.TestCase):
    @staticmethod
    def reading(cents, captured_at):
        return Reading(cents, "OCR", "Res. Dia", captured_at, "Sim 123")

    def test_alert_remains_independent_of_two_capture_action(self):
        events = queue.Queue()
        monitor = Monitor(MonitorConfig(1, -15000, auto_action=True, pid=10,
                                        gain_threshold_cents=15000), events)
        monitor.capture = object()
        frame = object()
        engine = object()

        def reading(cents, captured_at):
            return Reading(cents, "OCR", "Res. Dia", captured_at, "Sim 123")

        with patch("profit_alert.monitor.ActionStore.reserve", return_value=True), patch(
            "profit_alert.monitor.ProfitAction.execute"
        ) as execute:
            now = time.time()
            monitor._observe(reading(-15100, now), frame, engine)
            monitor._observe(reading(-14900, now + 0.1), frame, engine)
            monitor._observe(reading(-15000, now + 0.2), frame, engine)
            execute.assert_not_called()
            monitor._observe(reading(-15200, now + 0.3), frame, engine)
            execute.assert_called_once()

        kinds = [event.kind for event in list(events.queue)]
        self.assertEqual(kinds.count("alert"), 1)
        self.assertEqual(kinds.count("action"), 4)

    def test_gain_only_actions_after_crossing_without_loss_action(self):
        events = queue.Queue()
        monitor = Monitor(MonitorConfig(1, -15000, pid=10,
                                        gain_threshold_cents=15000,
                                        gain_auto_action=True), events)
        monitor.capture = object()
        frame = object()
        engine = object()
        now = time.time()
        with patch("profit_alert.monitor.ActionStore.reserve", return_value=True), patch(
            "profit_alert.monitor.ProfitAction.execute"
        ) as execute:
            monitor._observe(self.reading(16000, now), frame, engine)
            execute.assert_not_called()  # resultado inicial já acima
            monitor._observe(self.reading(14900, now + 0.1), frame, engine)
            monitor._observe(self.reading(15000, now + 0.2), frame, engine)
            execute.assert_not_called()
            monitor._observe(self.reading(15100, now + 0.3), frame, engine)
            execute.assert_called_once()
        messages = [event.message for event in list(events.queue)]
        self.assertTrue(any("ganho: tentativa iniciada" in message for message in messages))
        self.assertEqual([event.kind for event in list(events.queue)].count("gain_alert"), 1)

    def test_both_limits_share_one_persistent_attempt_even_after_failure_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            store_path = Path(folder) / "action-state.json"
            config = MonitorConfig(1, -15000, auto_action=True, pid=10,
                                   gain_threshold_cents=15000, gain_auto_action=True)
            frame = object()
            engine = object()
            now = time.time()
            with patch("profit_alert.monitor.ActionStore",
                       side_effect=lambda: ActionStore(store_path)), patch(
                "profit_alert.monitor.ProfitAction.execute", side_effect=RuntimeError("falhou")
            ) as execute:
                first_events = queue.Queue()
                first = Monitor(config, first_events)
                first.capture = object()
                for cents, offset in ((14900, 0), (15000, 0.1), (15100, 0.2),
                                      (-14900, 0.3), (-15000, 0.4), (-15100, 0.5)):
                    first._observe(self.reading(cents, now + offset), frame, engine)
                self.assertEqual(execute.call_count, 1)
                self.assertTrue(any(event.kind == "action_failed" and "ganho" in event.message
                                    for event in list(first_events.queue)))
                self.assertTrue(any("perda: não acionado; já houve" in event.message
                                    for event in list(first_events.queue)))

                restarted_events = queue.Queue()
                restarted = Monitor(config, restarted_events)
                restarted.capture = object()
                for cents, offset in ((-14900, 0.6), (-15000, 0.7), (-15100, 0.8)):
                    restarted._observe(self.reading(cents, now + offset), frame, engine)
                self.assertEqual(execute.call_count, 1)
                self.assertTrue(any("perda: não acionado; já houve" in event.message
                                    for event in list(restarted_events.queue)))

    def test_loss_action_prevents_later_gain_action_same_day(self):
        events = queue.Queue()
        monitor = Monitor(MonitorConfig(1, -15000, auto_action=True, pid=10,
                                        gain_threshold_cents=15000,
                                        gain_auto_action=True), events)
        monitor.capture = object()
        now = time.time()
        with patch("profit_alert.monitor.ActionStore.reserve", return_value=True) as reserve, patch(
            "profit_alert.monitor.ProfitAction.execute"
        ) as execute:
            for cents, offset in ((-14900, 0), (-15000, 0.1), (-15100, 0.2),
                                  (14900, 0.3), (15000, 0.4), (15100, 0.5)):
                monitor._observe(self.reading(cents, now + offset), object(), object())
        reserve.assert_called_once()
        execute.assert_called_once()
        messages = [event.message for event in list(events.queue)]
        self.assertTrue(any("perda: confirmação aceita" in message for message in messages))
        self.assertTrue(any("ganho: não acionado; já houve" in message for message in messages))

    def test_gain_action_forces_ocr_and_full_frame(self):
        monitor = Monitor(MonitorConfig(1, -15000, mode="auto",
                                        gain_threshold_cents=15000,
                                        gain_auto_action=True), queue.Queue())
        with patch("profit_alert.monitor.comtypes.CoInitialize"), patch(
            "profit_alert.monitor.comtypes.CoUninitialize"
        ), patch.object(monitor, "_check_window", return_value=True), patch.object(
            monitor, "_run_uia"
        ) as run_uia, patch.object(monitor, "_run_ocr") as run_ocr:
            monitor._run()
            run_uia.assert_not_called()
            run_ocr.assert_called_once()
        monitor.stop_event.set()
        with patch("profit_alert.monitor.RapidOCR"), patch(
            "profit_alert.monitor.WindowCapture"
        ) as capture:
            monitor._run_ocr()
            self.assertTrue(capture.call_args.kwargs["full_frame"])

    def test_gain_action_requires_configured_threshold(self):
        with self.assertRaisesRegex(ValueError, "exige um limite de ganho"):
            Monitor(MonitorConfig(1, -15000, gain_auto_action=True), queue.Queue())


if __name__ == "__main__":
    unittest.main()
