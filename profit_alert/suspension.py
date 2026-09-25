"""Intervalos locais que suspendem apenas certos acionamentos automáticos."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable


_CLOCK = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
Interval = tuple[int, int]


def parse_clock(value: str) -> int:
    match = _CLOCK.fullmatch(value.strip())
    if match is None:
        raise ValueError("Informe o horário no formato HH:MM, entre 00:00 e 23:59.")
    return int(match.group(1)) * 60 + int(match.group(2))


def parse_interval(start: str, end: str) -> Interval:
    first, last = parse_clock(start), parse_clock(end)
    if first >= last:
        raise ValueError("O início do intervalo deve ser anterior ao fim, no mesmo dia.")
    return first, last


def format_clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def normalize_intervals(intervals: Iterable[Interval]) -> tuple[Interval, ...]:
    ordered = sorted(intervals)
    merged: list[Interval] = []
    for start, end in ordered:
        if not 0 <= start < end < 1440:
            raise ValueError("O intervalo deve ter horários válidos no mesmo dia.")
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


@dataclass(frozen=True)
class SuspensionSchedule:
    day: date
    intervals: tuple[Interval, ...]

    def __post_init__(self) -> None:
        if not self.intervals:
            raise ValueError("Adicione ao menos um intervalo de suspensão.")
        object.__setattr__(self, "intervals", normalize_intervals(self.intervals))

    def active(self, at: datetime) -> bool:
        if at.date() != self.day:
            return False
        minute = at.hour * 60 + at.minute
        return any(start <= minute < end for start, end in self.intervals)
