import tempfile
import threading
import time
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from profit_alert.action import (
    ActionError, ProfitAction, locate_confirmation_yes, locate_red_button, valid_confirmation,
)
from profit_alert.action_store import ActionStore


class ActionTests(unittest.TestCase):
    def confirmation_ocr(self, *, labels=("Sim", "Não"), scores=(0.99, 0.99), y=140):
        message = ("cancelar todas as ordens e encerrar todas as posições "
                   "para todas as contas")
        boxes = [np.array([[10, 60], [550, 60], [550, 90], [10, 90]]) * 2]
        for x in (430, 520)[:len(labels)]:
            boxes.append(np.array([[x, y], [x + 30, y], [x + 30, y + 15], [x, y + 15]]) * 2)
        return SimpleNamespace(boxes=np.array(boxes), txts=[message, *labels], scores=[0.99, *scores])

    def test_visual_confirmation_requires_unique_confident_pair_and_correct_message(self):
        frame = np.zeros((180, 600, 4), dtype=np.uint8)
        self.assertEqual(locate_confirmation_yes(lambda _: self.confirmation_ocr(), frame), (445, 148))
        bad_results = [self.confirmation_ocr(labels=("Sim",)),
                       self.confirmation_ocr(labels=("Sim", "Sim")),
                       self.confirmation_ocr(scores=(0.8, 0.99)),
                       self.confirmation_ocr(y=60)]
        wrong_message = self.confirmation_ocr()
        wrong_message.txts[0] = "Cancelar ordens desta conta?"
        bad_results.append(wrong_message)
        reversed_pair = self.confirmation_ocr(labels=("Não", "Sim"))
        bad_results.append(reversed_pair)
        for result in bad_results:
            with self.subTest(labels=result.txts), self.assertRaises(ActionError):
                locate_confirmation_yes(lambda _: result, frame)

    def test_custom_dialog_uses_visual_pair_with_directed_click(self):
        action = ProfitAction(1, 10, None, lambda _: self.confirmation_ocr(), threading.Event())
        dialog = SimpleNamespace(NativeWindowHandle=2)
        frame = np.zeros((180, 600, 4), dtype=np.uint8)
        capture = SimpleNamespace(start=Mock(), stop=Mock(),
                                  read_frame=Mock(return_value=(frame, time.time())))
        bounds = SimpleNamespace(left=100, top=200, right=700, bottom=380)
        with patch.object(action, "_check"), patch(
            "profit_alert.action.window_process", return_value=(10, "profitchart.exe")
        ), patch("profit_alert.action.WindowCapture", return_value=capture), patch(
            "profit_alert.action._rect", return_value=bounds
        ), patch("profit_alert.action._walk", return_value=[]), patch(
            "profit_alert.action._dialog", side_effect=[dialog, None]
        ), patch("profit_alert.action._message_click") as click:
            action.confirm_dialog(dialog)
            click.assert_called_once_with(2, 545, 348, 10)
        capture.stop.assert_called_once()

    def test_button_labels_do_not_duplicate_buttons_and_invoke_needs_no_child_hwnd(self):
        action = ProfitAction(1, 10, None, None, threading.Event())
        dialog = SimpleNamespace(NativeWindowHandle=2)
        invoke = Mock()
        yes = SimpleNamespace(Name="Sim", ControlTypeName="ButtonControl", NativeWindowHandle=0,
                              IsEnabled=True, GetPattern=Mock(return_value=invoke))
        no = SimpleNamespace(Name="Não", ControlTypeName="ButtonControl")
        capture = SimpleNamespace(start=Mock(), stop=Mock(), read_frame=Mock(return_value=(
            np.zeros((180, 600, 4), dtype=np.uint8), time.time())))
        with patch.object(action, "_check"), patch(
            "profit_alert.action.window_process", return_value=(10, "profitchart.exe")
        ), patch("profit_alert.action.WindowCapture", return_value=capture), patch(
            "profit_alert.action._rect"
        ), patch("profit_alert.action._dialog_text"), patch(
            "profit_alert.action._walk", return_value=[yes, no,
                SimpleNamespace(Name="Sim", ControlTypeName="TextControl"),
                SimpleNamespace(Name="Não", ControlTypeName="TextControl")]
        ), patch("profit_alert.action._dialog", return_value=None), patch(
            "profit_alert.action._message_click"
        ) as click:
            action.confirm_dialog(dialog)
            invoke.Invoke.assert_called_once()
            click.assert_not_called()

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

    def test_visual_confirmation_rejects_moved_stale_or_replaced_dialog(self):
        bounds = SimpleNamespace(left=100, top=200, right=700, bottom=380)
        moved = SimpleNamespace(left=101, top=200, right=701, bottom=380)
        dialog = SimpleNamespace(NativeWindowHandle=2)
        for rects, age, current in (([bounds, moved], 0, dialog),
                                    ([bounds, bounds], 10, dialog),
                                    ([bounds, bounds], 0, SimpleNamespace(NativeWindowHandle=9))):
            action = ProfitAction(1, 10, None, lambda _: self.confirmation_ocr(), threading.Event())
            capture = SimpleNamespace(start=Mock(), stop=Mock(), read_frame=Mock(return_value=(
                np.zeros((180, 600, 4), dtype=np.uint8), time.time())))
            with patch.object(action, "_check"), patch(
                "profit_alert.action.window_process", return_value=(10, "profitchart.exe")
            ), patch("profit_alert.action.WindowCapture", return_value=capture), patch(
                "profit_alert.action._rect", side_effect=rects
            ), patch("profit_alert.action._walk", return_value=[]), patch(
                "profit_alert.action._dialog", return_value=current
            ), patch("profit_alert.action._dialog_text"), patch(
                "profit_alert.action.locate_confirmation_yes", return_value=(445, 148)
            ), patch("profit_alert.action.time.time", side_effect=[time.time(), time.time() + age]), patch(
                "profit_alert.action._message_click"
            ) as click:
                with self.assertRaises(ActionError):
                    action.confirm_dialog(dialog)
                click.assert_not_called()

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
        ), patch("profit_alert.action._rect"), patch("profit_alert.action.WindowCapture", return_value=capture), patch(
            "profit_alert.action._dialog_text", side_effect=ActionError("texto diferente")
        ), patch("profit_alert.action.time.monotonic", side_effect=[0, 1, 9]), patch(
            "profit_alert.action._message_click"
        ) as click:
            with self.assertRaises(ActionError):
                action.confirm_dialog(dialog)
            click.assert_not_called()

    def test_suspension_beginning_during_dialog_prevents_final_confirmation(self):
        allowed = Mock(side_effect=[True, False])
        action = ProfitAction(1, 10, None, None, threading.Event(), action_allowed=allowed)
        dialog = SimpleNamespace(NativeWindowHandle=2)
        invoke = Mock()
        yes = SimpleNamespace(Name="Sim", ControlTypeName="ButtonControl", NativeWindowHandle=3, IsEnabled=True,
                              GetPattern=Mock(return_value=invoke))
        no = SimpleNamespace(Name="Não", ControlTypeName="ButtonControl", NativeWindowHandle=4)
        capture = SimpleNamespace(
            start=Mock(),
            read_frame=Mock(return_value=(np.zeros((158, 598, 4), dtype=np.uint8), time.time())),
            stop=Mock(),
        )
        with patch("profit_alert.action._rect"), patch("profit_alert.action.WindowCapture", return_value=capture), patch(
            "profit_alert.action.window_process", return_value=(10, "profitchart.exe")
        ), patch("profit_alert.action.window_title", return_value="ProfitPro"), patch(
            "profit_alert.action.target_state", return_value=None
        ), patch("profit_alert.action._dialog_text"), patch(
            "profit_alert.action._walk", return_value=[yes, no,
                SimpleNamespace(Name="Sim", ControlTypeName="TextControl"),
                SimpleNamespace(Name="Não", ControlTypeName="TextControl")]
        ), patch("profit_alert.action._message_click") as click:
            with self.assertRaisesRegex(ActionError, "suspensão iniciado"):
                action.confirm_dialog(dialog)
        self.assertEqual(allowed.call_count, 2)
        invoke.Invoke.assert_not_called()
        click.assert_not_called()
