"""Entrada simples para empacotamento como executável Windows."""

import os
import queue
import sys
import tempfile
import time
import traceback
from pathlib import Path


if __name__ == "__main__":
    try:
        if getattr(sys, "frozen", False):
            bundled = Path(sys._MEIPASS) / "tcl"
            os.environ["TCL_LIBRARY"] = str(bundled / "tcl8.6")
            os.environ["TK_LIBRARY"] = str(bundled / "tk8.6")
        if "--smoke-live" in sys.argv:
            from profit_alert.monitor import Monitor, MonitorConfig
            from profit_alert.windows import list_profit_windows

            targets = list_profit_windows()
            if not targets:
                raise RuntimeError("Profit não está aberto")
            events = queue.Queue()
            monitor = Monitor(MonitorConfig(targets[0].hwnd, -100000000, "auto"), events)
            monitor.start()
            found = False
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    try:
                        found = events.get(timeout=1).kind == "reading"
                    except queue.Empty:
                        pass
                    if found:
                        break
            finally:
                monitor.stop()
                if monitor.thread is not None:
                    monitor.thread.join(timeout=3)
            if not found:
                raise RuntimeError("O executável não recebeu leitura do Profit")
        else:
            from profit_alert.app import ProfitAlertApp

            app = ProfitAlertApp()
            if "--smoke" in sys.argv:
                app.root.withdraw()
                app.root.after(2000, app.exit)
            app.run()
    except Exception:
        path = Path(tempfile.gettempdir()) / "LeitorProfit-error.log"
        path.write_text(traceback.format_exc(), encoding="utf-8")
        raise
