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


# Finestra e emivita' (in giorni) per la tendenza: i punti oltre WINDOW_DAYS
# dal presente vengono ignorati, quelli dentro la finestra pesano sempre meno
# quanto piu' sono vecchi (dimezzano ogni HALF_LIFE_DAYS).
WINDOW_DAYS = 14.0
HALF_LIFE_DAYS = 7.0

# Costante di sintonia standard per il peso robusto di Tukey (biweight).
_TUKEY_C = 4.685


def linear_regression(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    """Ritorna (slope, intercept) su base least-squares, None se punti insufficienti."""
    return weighted_linear_regression(xs, ys, [1.0] * len(xs))


def weighted_linear_regression(
    xs: list[float], ys: list[float], weights: list[float]
) -> tuple[float, float] | None:
    """Come linear_regression, ma con un peso per punto (weighted least squares)."""
    n = len(xs)
    if n < 2:
        return None
    sum_w = sum(weights)
    if sum_w <= 0:
        return None
    mean_x = sum(w * x for w, x in zip(weights, xs)) / sum_w
    mean_y = sum(w * y for w, y in zip(weights, ys)) / sum_w
    denom = sum(w * (x - mean_x) ** 2 for w, x in zip(weights, xs))
    if denom == 0:
        return None
    slope = sum(w * (x - mean_x) * (y - mean_y) for w, x, y in zip(weights, xs, ys)) / denom
    intercept = mean_y - slope * mean_x
    return slope, intercept


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _recency_weights(xs: list[float], now_x: float, half_life: float) -> list[float]:
    """Peso 0.5**(eta'/half_life): dimezza ogni 'half_life' unita' di distanza da now_x."""
    if half_life <= 0:
        return [1.0] * len(xs)
    return [0.5 ** (max(0.0, now_x - x) / half_life) for x in xs]


def _robust_weights(residuals: list[float]) -> list[float]:
    """Downweight degli outlier: peso di Tukey biweight sui residui, scalati
    tramite la deviazione assoluta mediana (MAD). Punti con residuo enorme
    rispetto agli altri pesano ~0, i punti "normali" restano quasi a peso 1."""
    mad = _median([abs(r) for r in residuals])
    if mad == 0:
        return [1.0] * len(residuals)
    scale = mad * 1.4826  # rende MAD comparabile a una deviazione standard
    weights = []
    for r in residuals:
        u = r / (scale * _TUKEY_C)
        weights.append((1 - u**2) ** 2 if abs(u) < 1 else 0.0)
    return weights


def _windowed(
    xs: list[float], ys: list[float], now_x: float, window: float
) -> tuple[list[float], list[float]]:
    if window is None:
        return xs, ys
    cutoff = now_x - window
    filtered = [(x, y) for x, y in zip(xs, ys) if x >= cutoff]
    if len(filtered) < 2:
        return xs, ys  # finestra troppo stretta per questi dati: usa tutto
    fxs, fys = zip(*filtered)
    return list(fxs), list(fys)


def _prepare_trend_series(
    xs: list[float],
    ys: list[float],
    now_x: float,
    window: float,
    half_life: float,
) -> tuple[list[float], list[float], list[float]] | None:
    """Filtra per finestra temporale, pesa per recenza ed effettua un downweight
    degli outlier basato sui residui di un primo fit. Ritorna (xs, ys, weights)
    pronti per weighted_linear_regression, o None se i dati sono insufficienti."""
    if len(xs) < 2:
        return None
    fxs, fys = _windowed(xs, ys, now_x, window)
    weights = _recency_weights(fxs, now_x, half_life)
    if len(fxs) >= 3:
        reg = weighted_linear_regression(fxs, fys, weights)
        if reg is not None:
            slope0, intercept0 = reg
            residuals = [y - (slope0 * x + intercept0) for x, y in zip(fxs, fys)]
            robust = _robust_weights(residuals)
            weights = [w * r for w, r in zip(weights, robust)]
    return fxs, fys, weights


def trend_regression(
    xs: list[float],
    ys: list[float],
    now_x: float,
    window_days: float = WINDOW_DAYS,
    half_life_days: float = HALF_LIFE_DAYS,
    day_length: float = 1.0,
) -> tuple[float, float] | None:
    """Come linear_regression, ma pesata per dare piu' peso ai punti recenti
    (emivita' half_life_days), limitata a una finestra di window_days, e con
    downweight automatico degli outlier. 'day_length' converte i giorni nelle
    unita' usate da xs/now_x (1.0 se xs e' gia' in giorni, 86400 se in secondi)."""
    prepared = _prepare_trend_series(
        xs, ys, now_x, window_days * day_length, half_life_days * day_length
    )
    if prepared is None:
        return None
    fxs, fys, weights = prepared
    return weighted_linear_regression(fxs, fys, weights)


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
    window_days: float = WINDOW_DAYS,
    half_life_days: float = HALF_LIFE_DAYS,
    day_length: float = 1.0,
) -> float | None:
    """Valore da assegnare al punto in x=now_ts tale che la retta di tendenza
    (pesata per recenza, con outlier scartati, come trend_regression), ricalcolata
    includendolo, valga esattamente 'target' in x=end_ts.

    None se non calcolabile (nessun dato precedente, o retta degenere).
    """
    if not xs:
        return None

    prepared = _prepare_trend_series(
        xs, ys, now_ts, window_days * day_length, half_life_days * day_length
    )
    if prepared is None:
        fxs, fys = xs, ys
        weights = _recency_weights(xs, now_ts, half_life_days * day_length)
    else:
        fxs, fys, weights = prepared

    # Il punto ipotetico "adesso" non e' un outlier storico da scartare: pesa
    # come il presente (peso di recenza massimo, nessun downweight robusto).
    candidate_weight = 1.0

    def predicted_at_end(value: float) -> float | None:
        reg = weighted_linear_regression(
            fxs + [now_ts], fys + [value], weights + [candidate_weight]
        )
        if reg is None:
            return None
        slope, intercept = reg
        return slope * end_ts + intercept

    p0 = predicted_at_end(0.0)
    p100 = predicted_at_end(100.0)
    if p0 is None or p100 is None or p100 == p0:
        return None
    return 100.0 * (target - p0) / (p100 - p0)
