import tempfile
import threading
import time
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from profit_alert.action import ActionError, ProfitAction, locate_red_button, valid_confirmation
from profit_alert.action_store import ActionStore


class ActionTests(unittest.TestCase):
    def test_locates_unique_red_button_in_top_right(self):
        frame = np.zeros((800, 2500, 4), dtype=np.uint8)
        frame[:, :, :3] = (50, 50, 50)
        frame[70:115, 2300:2500, :3] = (40, 40, 200)
        box = np.array([[[1000, 55], [1390, 55], [1390, 95], [1000, 95]]])
        result = SimpleNamespace(boxes=box, txts=["Pausar + Zerar posições"], scores=[0.99])
        self.assertEqual(locate_red_button(lambda _image: result, frame), (2348, 83))
        frame[70:115, 2300:2500, :3] = (50, 50, 50)
        with self.assertRaises(ActionError):
            locate_red_button(lambda _image: result, frame)

    def test_confirmation_requires_global_operation_wording(self):
        self.assertTrue(valid_confirmation(
            "Você tem certeza que deseja cancelar todas as ordens e encerrar todas as "
            "posições de automação? Essa operação será feita para todas as contas."
        ))
        self.assertFalse(valid_confirmation("Sim, cancelar ordens desta conta?"))

    def test_persistent_one_attempt_per_day(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ActionStore(Path(folder) / "state.json")
            day = date(2026, 9, 24)
            self.assertTrue(store.reserve(day, 10))
            self.assertFalse(ActionStore(store.path).reserve(day, 20))
            self.assertTrue(store.reserve(date(2026, 9, 25), 20))

    def test_drawdown_attempt_has_separate_daily_state(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            "os.environ", {"LOCALAPPDATA": folder}
        ):
            standard = ActionStore()
            drawdown = ActionStore(kind="drawdown")
            day = date(2026, 9, 25)
            self.assertNotEqual(standard.path, drawdown.path)
            self.assertTrue(standard.reserve(day, 10))
            self.assertTrue(drawdown.reserve(day, 10))
            self.assertFalse(ActionStore(kind="drawdown").reserve(day, 20))
            self.assertFalse(ActionStore().reserve(day, 20))

    def test_corrupt_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            path.write_text("invalid", encoding="utf-8")
            with self.assertRaises(ValueError):
                ActionStore(path).reserve(date(2026, 9, 24), 10)

    def test_existing_dialog_blocks_red_click(self):
        action = ProfitAction(1, 10, None, None, threading.Event())
        frame = np.zeros((800, 2500, 4), dtype=np.uint8)
        with patch.object(action, "_check"), patch(
            "profit_alert.action.on_current_virtual_desktop", return_value=True
        ), patch("profit_alert.action._dialog", return_value=object()), patch(
            "profit_alert.action._message_click"
        ) as click:
            with self.assertRaises(ActionError):
                action.execute(frame, time.time())
            click.assert_not_called()

    def test_modal_opened_during_click_return_is_not_clicked_twice(self):
        action = ProfitAction(1, 10, None, None, threading.Event())
        frame = np.zeros((800, 2500, 4), dtype=np.uint8)
        modal = object()
        with patch.object(action, "_check"), patch(
            "profit_alert.action.on_current_virtual_desktop", return_value=True
        ), patch.object(action, "confirm_dialog") as confirm, patch(
            "profit_alert.action._dialog", side_effect=[None, modal]
        ), patch("profit_alert.action.locate_red_button", return_value=(2400, 90)), patch(
            "profit_alert.action._rect", return_value=SimpleNamespace(left=0, top=0, right=2500, bottom=800)
        ), patch("profit_alert.action._message_click", side_effect=ActionError("timeout")) as click:
            action.execute(frame, time.time())
            click.assert_called_once()
            confirm.assert_called_once_with(modal)

    def test_other_virtual_desktop_fails_before_any_click(self):
        action = ProfitAction(1, 10, None, None, threading.Event())
        frame = np.zeros((800, 2500, 4), dtype=np.uint8)
        with patch.object(action, "_check"), patch(
            "profit_alert.action.on_current_virtual_desktop", return_value=False
        ), patch("profit_alert.action._message_click") as click:
            with self.assertRaisesRegex(ActionError, "outra área"):
                action.execute(frame, time.time())
            click.assert_not_called()

    def test_unknown_confirmation_text_never_clicks_sim(self):
        action = ProfitAction(1, 10, None, None, threading.Event())
        dialog = SimpleNamespace(NativeWindowHandle=2)
        capture = SimpleNamespace(
            start=lambda: None,
            read_frame=lambda timeout: (np.zeros((158, 598, 4), dtype=np.uint8), time.time()),
            stop=lambda: None,
        )
        with patch.object(action, "_check"), patch(
            "profit_alert.action.window_process", return_value=(10, "profitchart.exe")
        ), patch("profit_alert.action.WindowCapture", return_value=capture), patch(
            "profit_alert.action._dialog_text", side_effect=ActionError("texto diferente")
        ), patch("profit_alert.action.time.monotonic", side_effect=[0, 1, 9]), patch(
            "profit_alert.action._message_click"
        ) as click:
            with self.assertRaises(ActionError):
                action.confirm_dialog(dialog)
            click.assert_not_called()
