"""Progress indicators and race predictions."""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd


def riegel(t1: float, d1: float, d2: float, k: float = 1.06) -> float:
    return t1 * (d2 / d1) ** k


def _vo2(v: float) -> float:
    return -4.60 + 0.182258 * v + 0.000104 * v * v


def _pct_max(t_min: float) -> float:
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)


def vdot(distance_m: float, time_s: float) -> float:
    """Jack Daniels' VDOT for a race performance."""
    t = time_s / 60
    return _vo2(distance_m / t) / _pct_max(t)


def time_for_vdot(v: float, distance_m: float) -> float:
    lo, hi = 60.0, 36000.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if vdot(distance_m, mid) > v:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def critical_speed(best_durations: dict[int, float]) -> dict | None:
    """Fit distance = CS * t + D' on best efforts between 3 and 20 minutes."""
    pts = [(t, v * t) for t, v in best_durations.items() if 150 <= t <= 1500 and v > 0]
    if len(pts) < 3:
        return None
    t, d = np.array([p[0] for p in pts], float), np.array([p[1] for p in pts], float)
    cs, dprime = np.polyfit(t, d, 1)
    if cs <= 0 or dprime < 0:
        return None
    return {"cs": float(cs), "d_prime": float(dprime), "cs_pace": 1000 / cs}


def predict_from_cs(cs: dict, distance_m: float) -> float:
    # The CS model is valid for roughly 2-30 min; beyond that apply Riegel from the 30-minute point.
    t = (distance_m - cs["d_prime"]) / cs["cs"]
    if t <= 1800:
        return t
    d30 = cs["cs"] * 1800 + cs["d_prime"]
    return riegel(1800, d30, distance_m)


def speed_at_hr(ef_rows: list[dict], ref_hr: float, window: float = 15) -> pd.DataFrame:
    """Aerobic efficiency: speed each run would sustain at ref_hr, from runs whose average HR is near it."""
    rows = [r for r in ef_rows if r.get("avg_hr") and r.get("ngp_speed") and abs(r["avg_hr"] - ref_hr) <= window]
    if not rows:
        return pd.DataFrame(columns=["date", "pace_at_hr"])
    df = pd.DataFrame(rows)
    df["pace_at_hr"] = 1000 / (df["ngp_speed"] * ref_hr / df["avg_hr"])
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date")[["date", "pace_at_hr", "avg_hr"]]


def projection(series: list[tuple[date, float]], target_day: date, max_gain_per_week: float = 0.01) -> dict | None:
    """Linear trend of a race-time series extrapolated to race day, capped at max_gain_per_week."""
    if len(series) < 3:
        return None
    x = np.array([(d - series[0][0]).days for d, _ in series], float)
    y = np.array([v for _, v in series], float)
    if x[-1] - x[0] < 14:
        return None
    slope, intercept = np.polyfit(x, y, 1)
    last = y[-1]
    weeks = max(0.0, (target_day - series[-1][0]).days / 7)
    cap = -last * max_gain_per_week / 7
    slope_c = max(slope, cap)
    proj = last + slope_c * (target_day - series[-1][0]).days
    resid = float(np.std(y - (slope * x + intercept)))
    spread = resid + last * 0.004 * weeks
    return {"projected": float(proj), "low": float(proj - spread), "high": float(proj + spread),
            "slope_s_per_week": float(slope * 7), "capped": bool(slope < cap)}


def prob_under(target: float, proj: dict) -> float:
    sd = max(1.0, (proj["high"] - proj["low"]) / 2)
    z = (target - proj["projected"]) / sd
    return float(0.5 * (1 + math.erf(z / math.sqrt(2))))
