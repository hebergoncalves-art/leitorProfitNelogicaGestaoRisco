"""Ciclo de monitoramento e avisos, executado fora da thread gráfica."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime

import comtypes
from rapidocr import RapidOCR

from .core import AlertGate, format_brl
from .readers import Reading, UIAReader, WindowCapture, read_image
from .windows import target_state


@dataclass(frozen=True)
class MonitorConfig:
    hwnd: int
    threshold_cents: int
    mode: str = "auto"  # auto, uia, ocr
    expected_account: str = ""
    scan_height: int = 220


@dataclass(frozen=True)
class MonitorEvent:
    kind: str  # status, reading, alert, warning, stopped
    message: str
    reading: Reading | None = None


class Monitor:
    def __init__(self, config: MonitorConfig, events: queue.Queue[MonitorEvent]) -> None:
        self.config = config
        self.events = events
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.capture: WindowCapture | None = None
        self.gate = AlertGate(config.threshold_cents)
        self.last_value: int | None = None
        self.last_report = 0.0
        self.warning_times: dict[str, float] = {}

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="ProfitMonitor", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def _emit(self, kind: str, message: str, reading: Reading | None = None) -> None:
        if kind == "warning":
            now = time.monotonic()
            if now - self.warning_times.get(message, -1000) < 30:
                return
            self.warning_times[message] = now
        self.events.put(MonitorEvent(kind, message, reading))

    def _valid_account(self, reading: Reading) -> bool:
        expected = self.config.expected_account.strip()
        return not expected or expected in reading.header_text

    def _observe(self, reading: Reading) -> None:
        if not self._valid_account(reading):
            self._emit("warning", "A conta configurada não foi identificada no cabeçalho. Leitura ignorada.")
            return
        now = time.time()
        if reading.cents != self.last_value or now - self.last_report >= 15:
            self._emit("reading", f"{format_brl(reading.cents)} · {reading.source}", reading)
            self.last_value = reading.cents
            self.last_report = now
        if self.gate.observe(reading.cents, reading.source, datetime.now()):
            self._emit("alert", f"Limite atingido: {format_brl(reading.cents)}", reading)

    def _check_window(self) -> bool:
        problem = target_state(self.config.hwnd)
        if problem is None:
            return True
        self._emit("warning", problem)
        return False

    def _run_uia(self) -> bool:
        """Retorna False se o modo automático deve tentar captura + OCR."""
        self._emit("status", "Procurando Res. Dia pela acessibilidade do Windows...")
        reader = UIAReader(self.config.hwnd)
        misses = 0
        has_read = False
        while not self.stop_event.is_set():
            if not self._check_window():
                return True
            try:
                reading = reader.read()
            except Exception:
                reading = None
            if reading is not None and self._valid_account(reading):
                if not has_read:
                    self._emit("status", "Leitura direta (UI Automation) ativa.")
                    has_read = True
                misses = 0
                self._observe(reading)
            else:
                misses += 1
                if misses >= 3:
                    if self.config.mode == "auto":
                        self._emit("status", "Campo indisponível na acessibilidade; iniciando OCR da janela.")
                        return False
                    self._emit("warning", "Não foi possível ler o campo pela acessibilidade.")
                    misses = 0
            self.stop_event.wait(0.7)
        return True

    def _run_ocr(self) -> None:
        self._emit("status", "Iniciando captura da janela do Profit...")
        engine = RapidOCR()
        capture = WindowCapture(self.config.hwnd, self.config.scan_height)
        self.capture = capture
        capture.start()
        self._emit("status", "Captura da janela ativa. O Profit pode ficar atrás de outras janelas.")
        unreadable_since = time.monotonic()
        unreadable_warning = False
        while not self.stop_event.is_set():
            if not self._check_window():
                break
            if capture.closed or (capture.control and capture.control.is_finished()):
                self._emit("warning", "A captura da janela terminou.")
                break
            item = capture.read_frame(timeout=1.0)
            if item is None:
                if unreadable_since is not None and time.monotonic() - unreadable_since >= 10 and not unreadable_warning:
                    self._emit("warning", "Não foi possível confirmar o campo Res. Dia nos últimos 10 segundos. Confira o Profit e a altura de leitura.")
                    unreadable_warning = True
                continue
            image, captured_at = item
            reading = read_image(engine, image, self.config.scan_height)
            if reading is None:
                if unreadable_since is None:
                    unreadable_since = time.monotonic()
                continue
            if unreadable_warning:
                self._emit("status", "Leitura OCR restaurada.")
            unreadable_since = None
            unreadable_warning = False
            self._observe(replace(reading, captured_at=captured_at))

    def _run(self) -> None:
        comtypes.CoInitialize()
        try:
            if not self._check_window():
                return
            if self.config.mode in ("auto", "uia"):
                finished = self._run_uia()
                if finished:
                    return
            self._run_ocr()
        except Exception as exc:
            self._emit("warning", f"Erro no monitoramento: {type(exc).__name__}: {exc}")
        finally:
            if self.capture is not None:
                self.capture.stop()
            comtypes.CoUninitialize()
            self._emit("stopped", "Monitoramento parado.")
