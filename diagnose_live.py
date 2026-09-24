"""Diagnóstico somente de leitura da janela real do Profit."""

from __future__ import annotations

import time

import comtypes
from rapidocr import RapidOCR

from profit_alert.core import format_brl
from profit_alert.readers import UIAReader, WindowCapture, read_image
from profit_alert.windows import list_profit_windows


def main() -> None:
    windows = list_profit_windows()
    if not windows:
        raise SystemExit("Nenhuma janela do Profit encontrada.")
    target = windows[0]
    print(f"Janela: {target.title} (HWND {target.hwnd})")
    comtypes.CoInitialize()
    try:
        started = time.monotonic()
        direct = UIAReader(target.hwnd).read()
        print("UIA:", format_brl(direct.cents) if direct else "campo indisponível",
              f"em {time.monotonic() - started:.1f}s")
    finally:
        comtypes.CoUninitialize()
    capture = WindowCapture(target.hwnd)
    capture.start()
    try:
        item = capture.read_frame(timeout=10)
        if item is None:
            print("Captura: nenhum quadro em 10 segundos")
            return
        frame, _timestamp = item
        started = time.monotonic()
        recognized = read_image(RapidOCR(), frame)
        print("OCR:", format_brl(recognized.cents) if recognized else "campo indisponível",
              f"em {time.monotonic() - started:.1f}s")
        count = 1
        end = time.monotonic() + 10
        while time.monotonic() < end:
            if capture.read_frame(timeout=1) is not None:
                count += 1
        print(f"Novos quadros em cerca de 10s: {count}")
    finally:
        capture.stop()


if __name__ == "__main__":
    main()
