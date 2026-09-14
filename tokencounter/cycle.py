"""Calcolo del ciclo di reset mensile e statistiche (regressione, proiezione)."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta


def _clamp_day(year: int, month: int, day: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = (month - 1) + delta
    return year + idx // 12, idx % 12 + 1


@dataclass
class Cycle:
    start: date
    end: date

    @property
    def total_days(self) -> float:
        return (self.end - self.start).total_seconds() / 86400 if isinstance(self.end - self.start, timedelta) else (self.end - self.start).days

    def days_left(self, today: date) -> int:
        return (self.end - today).days


def current_cycle(reset_day: int, today: date | None = None) -> Cycle:
    """Ciclo [start, end) che contiene 'today'. 'reset_day' e' il giorno del mese in cui i token si azzerano."""
    today = today or date.today()
    candidate = _clamp_day(today.year, today.month, reset_day)
    if candidate <= today:
        start = candidate
        end = _clamp_day(*_add_months(today.year, today.month, 1), reset_day)
    else:
        start = _clamp_day(*_add_months(today.year, today.month, -1), reset_day)
        end = candidate
    return Cycle(start=start, end=end)


def linear_regression(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    """Ritorna (slope, intercept) su base least-squares, None se punti insufficienti."""
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    intercept = mean_y - slope * mean_x
    return slope, intercept


def projected_exhaustion(slope: float, intercept: float, target: float = 100.0) -> float | None:
    """Ascissa (timestamp) stimata in cui la retta di tendenza raggiunge 'target'. None se non convergente."""
    if slope <= 0:
        return None
    return (target - intercept) / slope


def max_value_to_stay_on_pace(
    xs: list[float],
    ys: list[float],
    now_ts: float,
    end_ts: float,
    target: float = 100.0,
) -> float | None:
    """Valore da assegnare al punto in x=now_ts tale che la retta di tendenza,
    ricalcolata includendolo, valga esattamente 'target' in x=end_ts.

    None se non calcolabile (nessun dato precedente, o retta degenere).
    """
    if not xs:
        return None

    def predicted_at_end(value: float) -> float | None:
        reg = linear_regression(xs + [now_ts], ys + [value])
        if reg is None:
            return None
        slope, intercept = reg
        return slope * end_ts + intercept

    p0 = predicted_at_end(0.0)
    p100 = predicted_at_end(100.0)
    if p0 is None or p100 is None or p100 == p0:
        return None
    return 100.0 * (target - p0) / (p100 - p0)
