"""Teste manual, somente leitura, do fluxo completo com Profit aberto."""

from __future__ import annotations

import queue
import time

from profit_alert.monitor import Monitor, MonitorConfig
from profit_alert.windows import list_profit_windows


windows = list_profit_windows()
if not windows:
    raise SystemExit("Abra o Profit antes do teste.")
events = queue.Queue()
monitor = Monitor(MonitorConfig(windows[0].hwnd, -100000000, "auto"), events)
monitor.start()
deadline = time.monotonic() + 10
try:
    while time.monotonic() < deadline:
        try:
            event = events.get(timeout=1)
        except queue.Empty:
            continue
        print(event.kind, event.message)
finally:
    monitor.stop()
    if monitor.thread is not None:
        monitor.thread.join(timeout=5)
    while not events.empty():
        event = events.get_nowait()
        print(event.kind, event.message)
