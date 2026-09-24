"""Leitores independentes de foco: UI Automation e captura de janela + OCR."""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass

import cv2
import numpy as np
from rapidocr import RapidOCR
from windows_capture import Frame, InternalCaptureControl, WindowsCapture

from .core import parse_result


@dataclass(frozen=True)
class Reading:
    cents: int
    source: str
    raw: str
    captured_at: float
    header_text: str


def _ocr_lines(engine: RapidOCR, image: np.ndarray) -> list[tuple[str, float]]:
    if image.ndim == 3 and image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    image = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    result = engine(image)
    return [(str(text), float(score)) for text, score in zip(result.txts or [], result.scores or [])]


def read_image(engine: RapidOCR, image: np.ndarray, scan_height: int = 220) -> Reading | None:
    """Procura somente o resultado monetário na faixa superior da janela."""
    height, width = image.shape[:2]
    if height < 120 or width < 450:
        return None
    header = image[: min(scan_height, height), : min(1000, width)]
    lines = _ocr_lines(engine, header)
    candidates: list[tuple[int, str, float]] = []
    for text, confidence in lines:
        cents = parse_result(text)
        if cents is not None and confidence >= 0.90:
            candidates.append((cents, text, confidence))
    # O OCR pode dividir o rótulo e o valor em trechos. Juntamos os trechos
    # somente quando não apareceu um resultado completo em uma linha.
    if not candidates:
        combined = " ".join(text for text, confidence in lines if confidence >= 0.90)
        cents = parse_result(combined)
        if cents is not None:
            candidates.append((cents, combined, 0.90))
    # Dois resultados distintos na mesma faixa são ambíguos; não alertar.
    if len({item[0] for item in candidates}) != 1:
        return None
    cents, raw, _confidence = candidates[0]
    return Reading(cents, "OCR", raw, time.time(), " | ".join(text for text, _ in lines))


class UIAReader:
    """Lê texto de acessibilidade; retorna None quando o Profit não o expõe."""

    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd

    def read(self) -> Reading | None:
        import uiautomation as auto

        root = auto.ControlFromHandle(self.hwnd)
        if root is None:
            return None
        pending: list[tuple[object, int]] = [(root, 0)]
        seen = 0
        candidates: list[tuple[int, int, str]] = []
        header_parts: list[str] = []
        while pending and seen < 1500:
            control, depth = pending.pop()
            seen += 1
            try:
                names: list[str] = []
                if control.Name:
                    names.append(str(control.Name))
                pattern = control.GetPattern(auto.PatternId.ValuePattern)
                if pattern is not None and pattern.Value:
                    names.append(str(pattern.Value))
                rect = control.BoundingRectangle
                y = int(rect.top) if rect is not None else 999999
                for value in names:
                    if len(header_parts) < 100:
                        header_parts.append(value)
                    cents = parse_result(value)
                    if cents is not None:
                        candidates.append((y, cents, value))
                if depth < 8:
                    pending.extend((child, depth + 1) for child in control.GetChildren())
            except Exception:
                continue
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        top_y = candidates[0][0]
        top_values = {cents for y, cents, _ in candidates if abs(y - top_y) < 24}
        if len(top_values) != 1:
            return None
        _y, cents, raw = candidates[0]
        return Reading(cents, "UIA", raw, time.time(), " | ".join(header_parts))


class WindowCapture:
    """Mantém apenas o último quadro da faixa superior, sem capturar a tela ativa."""

    def __init__(self, hwnd: int, scan_height: int = 220, full_frame: bool = False) -> None:
        self.frames: queue.Queue[tuple[np.ndarray, float]] = queue.Queue(maxsize=1)
        self.closed = False
        self.scan_height = scan_height
        self.full_frame = full_frame
        self.capture = WindowsCapture(
            cursor_capture=False,
            window_hwnd=hwnd,
            minimum_update_interval=250,
        )

        @self.capture.event
        def on_frame_arrived(frame: Frame, _control: InternalCaptureControl) -> None:
            # frame_buffer pertence ao quadro nativo: copiar antes do retorno.
            array = (frame.frame_buffer.copy() if self.full_frame
                     else frame.frame_buffer[: self.scan_height, :1000].copy())
            while self.frames.full():
                try:
                    self.frames.get_nowait()
                except queue.Empty:
                    break
            self.frames.put_nowait((array, time.time()))

        @self.capture.event
        def on_closed() -> None:
            self.closed = True

        self.control = None

    def start(self) -> None:
        self.control = self.capture.start_free_threaded()

    def read_frame(self, timeout: float = 1.0) -> tuple[np.ndarray, float] | None:
        try:
            return self.frames.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self) -> None:
        if self.control is not None:
            self.control.stop()
