import queue
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import call, patch

from profit_alert.action_store import ActionStore
from profit_alert.monitor import Monitor, MonitorConfig
from profit_alert.readers import Reading


def reading(cents, captured_at, account="Sim 123", source="OCR"):
    return Reading(cents, source, "Res. Dia", captured_at, account)


class DrawdownMonitorTests(unittest.TestCase):
    def test_alert_at_exact_drop_once_without_action(self):
        events = queue.Queue()
        monitor = Monitor(MonitorConfig(1, -15000, drawdown_threshold_cents=40000,
                                        drawdown_alert=True), events)
        now = time.time()
        for cents in (80000, 40000, 30000, 90000, 40000):
            monitor._observe(reading(cents, now, source="UIA"))
        items = list(events.queue)
        alerts = [event for event in items if event.kind == "drawdown_alert"]
        self.assertEqual(len(alerts), 1)
        self.assertIn("pico R$ 800,00", alerts[0].message)
        self.assertIn("recuo R$ 400,00", alerts[0].message)
        self.assertIn("Pico: R$ 900,00", [event.message for event in items
                                         if event.kind == "drawdown_state"][-1])
        self.assertNotIn("action", [event.kind for event in items])

    def test_action_only_requires_two_fresh_distinct_frames(self):
        events = queue.Queue()
        monitor = Monitor(MonitorConfig(1, -15000, pid=10,
                                        drawdown_threshold_cents=40000,
                                        drawdown_auto_action=True), events)
        monitor.capture = object()
        frame = object()
        engine = object()
        now = time.time()
        with patch("profit_alert.monitor.ActionStore.reserve", return_value=True), patch(
            "profit_alert.monitor.ProfitAction.execute"
        ) as execute:
            monitor._observe(reading(80000, now), frame, engine)
            monitor._observe(reading(40000, now + 0.1), frame, engine)
            monitor._observe(reading(30000, now + 0.1), frame, engine)
            execute.assert_not_called()
            monitor._observe(reading(30000, now - 10), frame, engine)
            execute.assert_not_called()
            monitor._observe(reading(30000, now + 0.2), frame, engine)
            execute.assert_not_called()
            monitor._observe(reading(29900, now + 0.3), frame, engine)
            execute.assert_called_once()
        self.assertNotIn("drawdown_alert", [event.kind for event in list(events.queue)])

    def test_new_peak_resets_pending_action_confirmation(self):
        monitor = Monitor(MonitorConfig(1, -15000, drawdown_threshold_cents=40000,
                                        drawdown_auto_action=True), queue.Queue())
        monitor.capture = object()
        frame = object()
        engine = object()
        now = time.time()
        with patch("profit_alert.monitor.ActionStore.reserve", return_value=True), patch(
            "profit_alert.monitor.ProfitAction.execute"
        ) as execute:
            for cents, offset in ((80000, 0), (40000, 0.1), (90000, 0.2),
                                  (50000, 0.3)):
                monitor._observe(reading(cents, now + offset), frame, engine)
            execute.assert_not_called()
            monitor._observe(reading(40000, now + 0.4), frame, engine)
            execute.assert_called_once()

    def test_account_filter_prevents_peak_from_other_account(self):
        events = queue.Queue()
        monitor = Monitor(MonitorConfig(1, -15000, expected_account="123",
                                        drawdown_threshold_cents=40000,
                                        drawdown_alert=True), events)
        now = time.time()
        monitor._observe(reading(80000, now, "Sim 456"))
        monitor._observe(reading(30000, now + 0.1, "Sim 123"))
        self.assertEqual(monitor.drawdown_tracker.peak_cents, 30000)
        self.assertNotIn("drawdown_alert", [event.kind for event in list(events.queue)])

    def test_drawdown_and_standard_actions_have_independent_daily_attempts(self):
        with tempfile.TemporaryDirectory() as folder:
            standard_path = Path(folder) / "action-state.json"
            drawdown_path = Path(folder) / "drawdown-action-state.json"

            def store_factory(*, kind="standard"):
                return ActionStore(drawdown_path if kind == "drawdown" else standard_path)

            config = MonitorConfig(1, -15000, auto_action=True, pid=10,
                                   drawdown_threshold_cents=40000,
                                   drawdown_auto_action=True)
            frame = object()
            engine = object()
            now = time.time()
            with patch("profit_alert.monitor.ActionStore", side_effect=store_factory), patch(
                "profit_alert.monitor.ProfitAction.execute",
                side_effect=[RuntimeError("falhou"), None]
            ) as execute:
                first_events = queue.Queue()
                first = Monitor(config, first_events)
                first.capture = object()
                for cents, offset in ((80000, 0), (40000, 0.05), (30000, 0.1),
                                      (-14900, 0.15), (-15000, 0.2), (-15100, 0.25)):
                    first._observe(reading(cents, now + offset), frame, engine)
                self.assertEqual(execute.call_count, 2)
                self.assertTrue(any(event.kind == "action_failed" and "drawdown" in event.message
                                    for event in list(first_events.queue)))
                self.assertTrue(standard_path.exists())
                self.assertTrue(drawdown_path.exists())

                restarted_events = queue.Queue()
                restarted = Monitor(config, restarted_events)
                restarted.capture = object()
                for cents, offset in ((80000, 0.3), (40000, 0.35), (30000, 0.4),
                                      (-14900, 0.45), (-15000, 0.5), (-15100, 0.55)):
                    restarted._observe(reading(cents, now + offset), frame, engine)
                self.assertEqual(execute.call_count, 2)
                denied = [event.message for event in list(restarted_events.queue)
                          if "já houve uma tentativa" in event.message]
                self.assertTrue(any("drawdown" in message for message in denied))
                self.assertTrue(any("perda" in message for message in denied))

    def test_simultaneous_loss_precedes_drawdown_and_drawdown_requires_recross(self):
        events = queue.Queue()
        monitor = Monitor(MonitorConfig(1, -15000, auto_action=True, pid=10,
                                        drawdown_threshold_cents=95000,
                                        drawdown_auto_action=True), events)
        monitor.capture = object()
        now = time.time()
        with patch("profit_alert.monitor.ActionStore") as store, patch(
            "profit_alert.monitor.ProfitAction.execute"
        ) as execute:
            store.return_value.reserve.return_value = True
            for cents, offset in ((80000, 0), (-15000, 0.1), (-15100, 0.2),
                                  (-15200, 0.3)):
                monitor._observe(reading(cents, now + offset), object(), object())
            self.assertEqual(execute.call_count, 1)
            self.assertEqual(store.call_args_list, [call()])
            for cents, offset in ((-14900, 0.4), (-15000, 0.5), (-15100, 0.6)):
                monitor._observe(reading(cents, now + offset), object(), object())
            self.assertEqual(execute.call_count, 2)
            self.assertEqual(store.call_args_list, [call(), call(kind="drawdown")])

    def test_simultaneous_gain_precedes_drawdown(self):
        monitor = Monitor(MonitorConfig(1, -15000, pid=10, gain_threshold_cents=10000,
                                        gain_auto_action=True,
                                        drawdown_threshold_cents=70000,
                                        drawdown_auto_action=True), queue.Queue())
        monitor.capture = object()
        with patch.object(monitor, "_prepare_standard_action", return_value=True), patch.object(
            monitor.drawdown_action_gate, "observe", return_value=True
        ), patch.object(monitor.drawdown_action_gate, "defer_until_recross") as defer, patch.object(
            monitor, "_execute_action"
        ) as execute:
            monitor._observe(reading(10000, time.time()), object(), object())
        self.assertEqual(execute.call_args.args[:2], ("ganho", "standard"))
        defer.assert_called_once()

    def test_drawdown_action_forces_ocr_full_frame(self):
        monitor = Monitor(MonitorConfig(1, -15000, mode="auto",
                                        drawdown_threshold_cents=40000,
                                        drawdown_auto_action=True), queue.Queue())
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

    def test_active_drawdown_requires_positive_configured_limit(self):
        for value in (None, 0, -1):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "limite positivo"):
                Monitor(MonitorConfig(1, -15000, drawdown_threshold_cents=value,
                                      drawdown_auto_action=True), queue.Queue())


if __name__ == "__main__":
    unittest.main()
