import queue
import time
import unittest
from datetime import date, datetime, time as clock_time
from unittest.mock import patch

from profit_alert.core import ActionGate
from profit_alert.action import ActionError
from profit_alert.monitor import Monitor, MonitorConfig
from profit_alert.readers import Reading
from profit_alert.suspension import (SuspensionSchedule, normalize_intervals,
                                     parse_clock, parse_interval)


class SuspensionScheduleTests(unittest.TestCase):
    def test_parsing_rejects_invalid_or_overnight_times(self):
        self.assertEqual(parse_interval("10:00", "10:05"), (600, 605))
        for invalid in ("9:00", "24:00", "10:60", "abc", "10:00:00"):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                parse_clock(invalid)
        for start, end in (("10:00", "10:00"), ("23:00", "01:00")):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                parse_interval(start, end)

    def test_merges_overlaps_and_uses_half_open_same_day_bounds(self):
        day = date(2026, 9, 25)
        schedule = SuspensionSchedule(day, ((900, 915), (600, 605), (604, 610)))
        self.assertEqual(schedule.intervals, ((600, 610), (900, 915)))
        self.assertTrue(schedule.active(datetime(2026, 9, 25, 10, 0)))
        self.assertTrue(schedule.active(datetime(2026, 9, 25, 10, 9, 59)))
        self.assertFalse(schedule.active(datetime(2026, 9, 25, 10, 10)))
        self.assertFalse(schedule.active(datetime(2026, 9, 26, 10, 0)))
        self.assertEqual(normalize_intervals(((600, 605), (605, 610))), ((600, 610),))
        with self.assertRaises(ValueError):
            SuspensionSchedule(day, ())


class SuspendedActionGateTests(unittest.TestCase):
    def test_retains_crossing_but_requires_two_new_captures(self):
        gate = ActionGate(-15000)
        now = time.time()
        gate.observe(-14900, now, now)
        gate.observe_suspended(-15000, now + 1, now + 1)
        gate.observe_suspended(-15100, now + 2, now + 2)
        self.assertFalse(gate.observe(-15100, now + 3, now + 3))
        self.assertFalse(gate.observe(-15100, now + 3, now + 4))
        self.assertTrue(gate.observe(-15200, now + 5, now + 5))

    def test_starting_at_limit_without_crossing_still_does_not_fire(self):
        gate = ActionGate(-15000)
        now = time.time()
        gate.observe_suspended(-15000, now, now)
        self.assertFalse(gate.observe(-15100, now + 1, now + 1))
        self.assertFalse(gate.observe(-15100, now + 2, now + 2))


class MonitorSuspensionTests(unittest.TestCase):
    def setUp(self):
        self.day = date.today()
        self.schedule = SuspensionSchedule(self.day, ((600, 605),))

        class ClockDateTime(datetime):
            current = datetime.combine(self.day, clock_time(9, 59, 50))

            @classmethod
            def now(cls, tz=None):
                return cls.current

        self.clock = ClockDateTime

    def observe(self, monitor, cents, hour, minute, second, *, capture=None):
        self.clock.current = datetime.combine(self.day, clock_time(hour, minute, second))
        captured_at = capture if capture is not None else self.clock.current.timestamp()
        monitor._observe(Reading(cents, "OCR", "Res. Dia", captured_at, "Sim 123"),
                         object(), object())

    def test_loss_alerts_during_suspension_and_acts_after_fresh_confirmations(self):
        events = queue.Queue()
        monitor = Monitor(MonitorConfig(1, -15000, auto_action=True, pid=10,
                                       suspension=self.schedule), events)
        with patch("profit_alert.monitor.datetime", self.clock), patch(
            "profit_alert.monitor.time.time", side_effect=lambda: self.clock.current.timestamp()
        ), patch("profit_alert.monitor.ActionStore.reserve", return_value=True) as reserve, patch(
            "profit_alert.monitor.ProfitAction.execute"
        ) as execute:
            self.observe(monitor, -14900, 9, 59, 50)
            self.observe(monitor, -15000, 10, 0, 1)
            self.observe(monitor, -15100, 10, 0, 2)
            self.assertEqual([event.kind for event in list(events.queue)].count("alert"), 1)
            reserve.assert_not_called()
            execute.assert_not_called()
            self.observe(monitor, -15100, 10, 5, 0,
                         capture=datetime.combine(self.day, clock_time(10, 4, 59)).timestamp())
            self.observe(monitor, -15100, 10, 5, 1)
            execute.assert_not_called()
            self.observe(monitor, -15200, 10, 5, 2)
            execute.assert_called_once()
            reserve.assert_called_once()

    def test_drawdown_alerts_during_suspension_and_acts_afterward(self):
        events = queue.Queue()
        monitor = Monitor(MonitorConfig(1, -15000, drawdown_threshold_cents=40000,
                                       drawdown_alert=True, drawdown_auto_action=True,
                                       suspension=self.schedule), events)
        with patch("profit_alert.monitor.datetime", self.clock), patch(
            "profit_alert.monitor.time.time", side_effect=lambda: self.clock.current.timestamp()
        ), patch("profit_alert.monitor.ActionStore.reserve", return_value=True) as reserve, patch(
            "profit_alert.monitor.ProfitAction.execute"
        ) as execute:
            self.observe(monitor, 80000, 9, 59, 50)
            self.observe(monitor, 40000, 10, 0, 1)
            self.observe(monitor, 30000, 10, 0, 2)
            self.assertEqual([event.kind for event in list(events.queue)].count("drawdown_alert"), 1)
            reserve.assert_not_called()
            self.observe(monitor, 30000, 10, 5, 0)
            execute.assert_not_called()
            self.observe(monitor, 29900, 10, 5, 1)
            execute.assert_called_once()
            reserve.assert_called_once()

    def test_gain_action_is_not_suspended(self):
        monitor = Monitor(MonitorConfig(1, -15000, gain_threshold_cents=15000,
                                       gain_auto_action=True, suspension=self.schedule), queue.Queue())
        with patch("profit_alert.monitor.datetime", self.clock), patch(
            "profit_alert.monitor.time.time", side_effect=lambda: self.clock.current.timestamp()
        ), patch("profit_alert.monitor.ActionStore.reserve", return_value=True), patch(
            "profit_alert.monitor.ProfitAction.execute"
        ) as execute:
            self.observe(monitor, 14900, 9, 59, 50)
            self.observe(monitor, 15000, 10, 0, 1)
            self.observe(monitor, 15100, 10, 0, 2)
            execute.assert_called_once()

    def test_starting_monitor_inside_interval_needs_prior_crossing(self):
        monitor = Monitor(MonitorConfig(1, -15000, auto_action=True,
                                       suspension=self.schedule), queue.Queue())
        with patch("profit_alert.monitor.datetime", self.clock), patch(
            "profit_alert.monitor.time.time", side_effect=lambda: self.clock.current.timestamp()
        ), patch("profit_alert.monitor.ActionStore.reserve") as reserve:
            self.observe(monitor, -15100, 10, 0, 1)
            self.observe(monitor, -15100, 10, 5, 0)
            self.observe(monitor, -15200, 10, 5, 1)
            reserve.assert_not_called()

    def test_interval_begins_during_action_and_reserved_attempt_remains_consumed(self):
        events = queue.Queue()
        monitor = Monitor(MonitorConfig(1, -15000, auto_action=True,
                                       suspension=self.schedule), events)
        self.clock.current = datetime.combine(self.day, clock_time(9, 59, 59))

        def execute_during_transition(action, _frame, _captured_at):
            self.clock.current = datetime.combine(self.day, clock_time(10, 0))
            if not action.action_allowed():
                raise ActionError("Intervalo de suspensão iniciado; zeramento não confirmado.")

        with patch("profit_alert.monitor.datetime", self.clock), patch(
            "profit_alert.monitor.ActionStore.reserve", return_value=True
        ) as reserve, patch("profit_alert.monitor.ProfitAction.execute",
                            autospec=True, side_effect=execute_during_transition):
            monitor._execute_action("perda", "standard", object(), object(),
                                    self.clock.current.timestamp())
        reserve.assert_called_once()
        self.assertEqual(monitor.action_attempted_day, self.day)
        self.assertTrue(any(event.kind == "action_failed" and "suspensão" in event.message
                            for event in list(events.queue)))


if __name__ == "__main__":
    unittest.main()
