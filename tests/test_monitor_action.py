import queue
import time
import unittest
from unittest.mock import patch

from profit_alert.monitor import Monitor, MonitorConfig
from profit_alert.readers import Reading


class MonitorActionTests(unittest.TestCase):
    def test_alert_remains_independent_of_two_capture_action(self):
        events = queue.Queue()
        monitor = Monitor(MonitorConfig(1, -15000, auto_action=True, pid=10), events)
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


if __name__ == "__main__":
    unittest.main()
