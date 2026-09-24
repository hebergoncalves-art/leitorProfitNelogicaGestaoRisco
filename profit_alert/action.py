"""Acionamento dirigido à janela do Profit, sem mouse global ou troca de foco."""

from __future__ import annotations

import ctypes
import re
import threading
import time
import unicodedata
from ctypes import wintypes

import cv2
import numpy as np
import uiautomation as auto
from rapidocr import RapidOCR

from .readers import WindowCapture
from .windows import on_current_virtual_desktop, target_state, window_process, window_title


class ActionError(RuntimeError):
    pass


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in value if not unicodedata.combining(c))).strip()


def locate_red_button(engine: RapidOCR, frame: np.ndarray) -> tuple[int, int]:
    """Localiza o texto único no botão vermelho, em pixels da captura."""
    height, width = frame.shape[:2]
    if width < 1200 or height < 200:
        raise ActionError("A captura do Profit não contém a faixa do botão vermelho.")
    left, top = width - 750, 45
    roi = frame[top: min(150, height), left:width]
    result = engine(cv2.resize(roi, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
    matches: list[tuple[int, int]] = []
    if result.boxes is None:
        raise ActionError("Botão Pausar + Zerar posições não reconhecido.")
    for box, label, confidence in zip(result.boxes, result.txts, result.scores):
        if normalize(str(label)) != "pausar zerar posicoes" or float(confidence) < 0.93:
            continue
        x = left + round(float(np.mean(box[:, 0])) / 2)
        y = top + round(float(np.mean(box[:, 1])) / 2)
        if x < width - 340 or not 55 <= y <= 135:
            continue
        patch = frame[max(0, y - 8): min(height, y + 9), max(0, x - 25): min(width, x + 26), :3]
        if patch.size == 0:
            continue
        b, g, r = np.median(patch.reshape(-1, 3), axis=0)
        if r < 110 or r < max(b, g) + 55:
            continue
        matches.append((x, y))
    if len(matches) != 1:
        raise ActionError("Botão vermelho ausente ou ambíguo; nenhum clique realizado.")
    return matches[0]


def valid_confirmation(text: str) -> bool:
    normalized = normalize(text)
    return all(fragment in normalized for fragment in (
        "cancelar todas as ordens", "encerrar todas as posicoes", "todas as contas"
    ))


user32 = ctypes.WinDLL("user32", use_last_error=True)


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
user32.ScreenToClient.restype = wintypes.BOOL
user32.ChildWindowFromPointEx.argtypes = [wintypes.HWND, POINT, wintypes.UINT]
user32.ChildWindowFromPointEx.restype = wintypes.HWND
user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                      wintypes.LPARAM, wintypes.UINT, wintypes.UINT,
                                      ctypes.POINTER(ctypes.c_size_t)]
user32.SendMessageTimeoutW.restype = wintypes.LPARAM


def _rect(hwnd: int) -> RECT:
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ActionError("Não foi possível obter a posição da janela do Profit.")
    return rect


def _walk(control: object, max_depth: int = 8) -> list[object]:
    queue = [(control, 0)]
    found = []
    while queue and len(found) < 400:
        item, depth = queue.pop(0)
        found.append(item)
        if depth < max_depth:
            try:
                queue.extend((child, depth + 1) for child in item.GetChildren())
            except Exception:
                pass
    return found


def _dialog(hwnd: int, pid: int):
    root = auto.ControlFromHandle(hwnd)
    if root is None:
        raise ActionError("Janela do Profit indisponível para conferir a confirmação.")
    found = [item for item in _walk(root, 3)
             if str(item.Name or "") == "ProfitMessageBox"]
    if len(found) > 1:
        raise ActionError("Há mais de uma caixa de confirmação do Profit.")
    if not found:
        return None
    candidate = found[0]
    child_hwnd = int(candidate.NativeWindowHandle)
    if not child_hwnd or window_process(child_hwnd)[0] != pid:
        raise ActionError("A confirmação não pertence ao processo selecionado.")
    return candidate


def _message_click(hwnd: int, screen_x: int, screen_y: int, pid: int) -> None:
    """Envia mouse down/up ao HWND filho, jamais ao cursor global."""
    current = hwnd
    for _ in range(8):
        point = POINT(screen_x, screen_y)
        if not user32.ScreenToClient(current, ctypes.byref(point)):
            raise ActionError("Falha ao converter posição do controle.")
        child = user32.ChildWindowFromPointEx(current, point, 0x0001 | 0x0002)
        if not child or int(child) == int(current):
            break
        current = int(child)
    if window_process(current)[0] != pid:
        raise ActionError("O destino do clique não pertence ao Profit selecionado.")
    bounds = _rect(current)
    if not bounds.left <= screen_x < bounds.right or not bounds.top <= screen_y < bounds.bottom:
        raise ActionError("A posição do controle saiu da janela selecionada.")
    point = POINT(screen_x, screen_y)
    if not user32.ScreenToClient(current, ctypes.byref(point)):
        raise ActionError("Falha ao converter posição do clique.")
    position = (point.y & 0xFFFF) << 16 | (point.x & 0xFFFF)
    output = ctypes.c_size_t()
    for message, flags in ((0x0201, 0x0001), (0x0202, 0)):
        if not user32.SendMessageTimeoutW(current, message, flags, position,
                                          0x0002, 750, ctypes.byref(output)):
            raise ActionError("O Profit não confirmou o recebimento do clique dirigido.")


def _dialog_text(engine: RapidOCR, frame: np.ndarray) -> str:
    if frame.shape[1] < 450 or frame.shape[0] < 100:
        raise ActionError("Área da confirmação inválida.")
    for scale in (2, 3):
        image = cv2.resize(frame[:, :, :3], None, fx=scale, fy=scale,
                           interpolation=cv2.INTER_CUBIC)
        result = engine(image)
        text = " ".join(str(label) for label, score in zip(result.txts or [], result.scores or [])
                        if float(score) >= 0.85)
        if valid_confirmation(text):
            return text
    raise ActionError("Texto da confirmação não corresponde à operação para todas as contas.")


class ProfitAction:
    def __init__(self, hwnd: int, pid: int, capture: WindowCapture,
                 engine: RapidOCR, stop_event: threading.Event) -> None:
        self.hwnd = hwnd
        self.pid = pid
        self.capture = capture
        self.engine = engine
        self.stop_event = stop_event

    def _check(self) -> None:
        if self.stop_event.is_set():
            raise ActionError("Monitoramento interrompido antes da confirmação.")
        if target_state(self.hwnd) is not None or window_process(self.hwnd)[0] != self.pid:
            raise ActionError("A janela selecionada do Profit mudou ou ficou indisponível.")
        if not window_title(self.hwnd).casefold().startswith(("profitpro", "profit pro")):
            raise ActionError("Título da janela do Profit mudou.")

    def execute(self, frame: np.ndarray, captured_at: float) -> None:
        self._check()
        if not on_current_virtual_desktop(self.hwnd):
            raise ActionError("Profit em outra área de trabalho: acionamento ainda não validado nessa condição.")
        if time.time() - captured_at > 5:
            raise ActionError("Captura antiga; botão vermelho não acionado.")
        if _dialog(self.hwnd, self.pid) is not None:
            raise ActionError("Já existe uma confirmação aberta no Profit; nenhum clique realizado.")
        x, y = locate_red_button(self.engine, frame)
        bounds = _rect(self.hwnd)
        if abs(frame.shape[1] - (bounds.right - bounds.left)) > 10 or abs(frame.shape[0] - (bounds.bottom - bounds.top)) > 10:
            raise ActionError("A escala da captura mudou; botão não acionado.")
        screen_x, screen_y = bounds.left + x, bounds.top + y
        self._check()
        click_error = None
        try:
            _message_click(self.hwnd, screen_x, screen_y, self.pid)
        except ActionError as exc:
            # Alguns controles entram em um diálogo modal antes de a última
            # mensagem retornar. O estado da janela decide, sem repetir o clique.
            click_error = exc

        dialog = None
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            self._check()
            dialog = _dialog(self.hwnd, self.pid)
            if dialog is not None:
                break
            self.stop_event.wait(0.15)
        if dialog is None:
            if click_error is not None:
                raise click_error
            raise ActionError("O Profit não abriu a confirmação após o botão vermelho.")

        self.confirm_dialog(dialog)

    def confirm_dialog(self, dialog: object) -> None:
        """Confirma uma caixa recém-aberta, após validar o conteúdo por captura própria."""
        dialog_hwnd = int(dialog.NativeWindowHandle)
        if not dialog_hwnd or window_process(dialog_hwnd)[0] != self.pid:
            raise ActionError("Caixa de confirmação não pertence ao Profit selecionado.")
        dialog_capture = WindowCapture(dialog_hwnd, full_frame=True)
        dialog_capture.start()
        try:
            last_error = ActionError("Sem captura recente da confirmação do Profit.")
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                self._check()
                item = dialog_capture.read_frame(timeout=0.7)
                if item is None or time.time() - item[1] > 5:
                    continue
                try:
                    _dialog_text(self.engine, item[0])
                    break
                except ActionError as exc:
                    last_error = exc
            else:
                raise last_error
        finally:
            dialog_capture.stop()

        buttons = [item for item in _walk(dialog, 3)
                   if normalize(str(item.Name or "")) in ("sim", "nao")]
        yes = [item for item in buttons if normalize(str(item.Name or "")) == "sim"]
        no = [item for item in buttons if normalize(str(item.Name or "")) == "nao"]
        if len(yes) != 1 or len(no) != 1:
            raise ActionError("Botões Sim/Não da confirmação estão ambíguos.")
        yes_control = yes[0]
        yes_hwnd = int(yes_control.NativeWindowHandle)
        if not yes_control.IsEnabled or not yes_hwnd or window_process(yes_hwnd)[0] != self.pid:
            raise ActionError("Controle Sim inválido ou desabilitado.")
        invoke = yes_control.GetPattern(auto.PatternId.InvokePattern)
        self._check()
        if invoke is not None:
            invoke.Invoke()
        else:
            rectangle = yes_control.BoundingRectangle
            try:
                _message_click(yes_hwnd, rectangle.xcenter(), rectangle.ycenter(), self.pid)
            except ActionError:
                # A janela modal pode fechar antes do retorno da mensagem.
                if _dialog(self.hwnd, self.pid) is not None:
                    raise
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if _dialog(self.hwnd, self.pid) is None:
                return
            self.stop_event.wait(0.15)
        raise ActionError("A confirmação permaneceu aberta; confira o Profit.")
