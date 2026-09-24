"""Entrada gráfica e diagnóstico de OCR em uma imagem local."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Leitor local do Res. Dia do Profit")
    parser.add_argument("--image", type=Path, help="Testa OCR em uma captura PNG sem abrir a interface")
    parser.add_argument("--scan-height", type=int, default=220)
    args = parser.parse_args()
    if args.image is not None:
        import numpy as np
        from PIL import Image
        from rapidocr import RapidOCR

        from .core import format_brl
        from .readers import read_image

        reading = read_image(RapidOCR(), np.array(Image.open(args.image)), args.scan_height)
        if reading is None:
            raise SystemExit("Res. Dia monetário não encontrado na imagem.")
        print(f"Res. Dia: {format_brl(reading.cents)}")
        return
    from .app import ProfitAlertApp

    ProfitAlertApp().run()


if __name__ == "__main__":
    main()

