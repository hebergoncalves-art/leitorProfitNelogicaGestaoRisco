"""Conversão monetária e controle de disparo, sem dependências de interface."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime


_NUMBER = r"(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}"
_RESULT = re.compile(
    rf"\bRes\s*\.?\s*Dia\s*(?P<before>[-−]?)\s*R\s*\$\s*"
    rf"(?P<after>[-−]?)\s*(?P<number>{_NUMBER})(?![\d,])",
    re.IGNORECASE,
)
_THRESHOLD = re.compile(rf"^\s*(?P<before>[-−]?)\s*(?:R\s*\$)?\s*"
                        rf"(?P<after>[-−]?)\s*(?P<number>{_NUMBER}|\d+)\s*$", re.IGNORECASE)


def _to_cents(number: str, negative: bool) -> int:
    whole, cents = number.replace(".", "").split(",")
    value = int(whole) * 100 + int(cents)
    return -value if negative else value


def parse_result(text: str) -> int | None:
    """Lê apenas o campo monetário 'Res. Dia R$ ...', nunca 'Res. Dia (%)'."""
    match = _RESULT.search(text)
    if match is None:
        return None
    if match.group("before") and match.group("after"):
        return None
    return _to_cents(match.group("number"), bool(match.group("before") or match.group("after")))


def parse_threshold(text: str) -> int:
    match = _THRESHOLD.fullmatch(text)
    if match is None or (match.group("before") and match.group("after")):
        raise ValueError("Digite um valor em reais, por exemplo -150,00.")
    number = match.group("number")
    if "," not in number:
        number += ",00"
    value = _to_cents(number, bool(match.group("before") or match.group("after")))
    if value >= 0:
        raise ValueError("O limite de perda deve ser negativo.")
    return value


def format_brl(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    absolute = abs(cents)
    whole = f"{absolute // 100:,}".replace(",", ".")
    return f"{sign}R$ {whole},{absolute % 100:02d}"


@dataclass
class AlertGate:
    threshold_cents: int
    # A captura só gera um novo quadro quando a imagem muda. Um quadro válido
    # pode ser o único disponível no momento em que o limite é atingido.
    ocr_confirmations: int = 1
    triggered_day: str | None = None
    consecutive: int = 0

    def observe(self, cents: int | None, source: str, at: datetime) -> bool:
        day = at.date().isoformat()
        if self.triggered_day is not None and self.triggered_day != day:
            self.triggered_day = None
            self.consecutive = 0
        if cents is None or cents > self.threshold_cents:
            self.consecutive = 0
            return False
        if self.triggered_day == day:
            return False
        self.consecutive += 1
        required = self.ocr_confirmations if source == "OCR" else 1
        if self.consecutive < required:
            return False
        self.triggered_day = day
        return True

    def reset(self) -> None:
        self.triggered_day = None
        self.consecutive = 0


@dataclass
class ActionGate:
    """Exige cruzamento observado e duas leituras recentes e distintas."""

    threshold_cents: int
    armed: bool = False
    first_below_at: float | None = None
    last_frame_at: float | None = None
    attempted: bool = False
    observed_day: date | None = None

    def observe(self, cents: int | None, captured_at: float, now: float) -> bool:
        day = date.fromtimestamp(now)
        if self.observed_day != day:
            self.observed_day = day
            self.armed = False
            self.first_below_at = None
            self.last_frame_at = None
            self.attempted = False
        if self.attempted:
            return False
        if cents is None or captured_at > now + 1 or now - captured_at > 5:
            self.first_below_at = None
            self.last_frame_at = None
            return False
        if cents > self.threshold_cents:
            self.armed = True
            self.first_below_at = None
            self.last_frame_at = None
            return False
        if not self.armed:
            return False
        if self.first_below_at is None or now - self.first_below_at > 10:
            self.first_below_at = now
            self.last_frame_at = captured_at
            return False
        if captured_at <= (self.last_frame_at or 0):
            return False
        self.attempted = True
        return True
