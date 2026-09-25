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


# Fraction of VMA a well-executed interval repetition is run at, by rep duration (s) — the usual
# coaching targets (400 m ~105 %, 1000 m ~98 %, 2000 m ~93 %, 20 min ~88 %).
REP_VMA_FRACTION = [(60, 1.07), (90, 1.05), (180, 1.00), (300, 0.97), (600, 0.93), (1200, 0.88)]
# Fraction of threshold pace speed vs VMA (threshold ≈ 85-88 % VMA for trained runners).
THRESHOLD_VMA_FRACTION = 0.87


def rep_vma_fraction(duration_s: float) -> float:
    pts = REP_VMA_FRACTION
    if duration_s <= pts[0][0]:
        return pts[0][1]
    if duration_s >= pts[-1][0]:
        return pts[-1][1]
    for (t0, f0), (t1, f1) in zip(pts, pts[1:]):
        if t0 <= duration_s <= t1:
            w = math.log(duration_s / t0) / math.log(t1 / t0)
            return f0 + (f1 - f0) * w
    return 1.0


def race_vma_fraction(duration_s: float) -> float:
    """Fraction of VMA sustainable over a race of this duration: 100 % at 6 min, ~94 % at 20 min,
    ~90 % at 40 min, ~86 % at 1h30 (log decline, the classic endurance-index shape)."""
    t_min = duration_s / 60
    return 1.0 if t_min <= 6 else 1 - 0.05 * math.log(t_min / 6)


def predict_from_vma(vma: float, distance_m: float) -> float:
    """Race time (s) for a distance given VMA in m/s."""
    t = distance_m / (vma * 0.9)
    for _ in range(40):
        t = distance_m / (vma * race_vma_fraction(t))
    return t


def session_vma(reps: list[dict], threshold_pace: float, hr_max: float | None = None) -> float | None:
    """VMA (m/s) implied by one interval session: each real rep (faster than threshold pace, 45 s to
    25 min, no GPS glitch) is scaled by the fraction of VMA a rep of that length is normally run at;
    the session's value is the median, so one odd rep doesn't drive it. Easy-effort sessions (HR never
    near max) are skipped: they say little about capacity."""
    reps = [r for r in reps if r.get("avg_pace") and 45 <= r["duration_s"] <= 1500
            and r["avg_pace"] < threshold_pace and 1000 / r["avg_pace"] < 7.0]
    if len(reps) < 3:
        return None
    if hr_max:
        hrs = [r["avg_hr"] for r in reps if r.get("avg_hr")]
        if hrs and max(hrs) < 0.88 * hr_max:
            return None
    ests = sorted(1000 / r["avg_pace"] / rep_vma_fraction(r["duration_s"]) for r in reps)
    return float(np.median(ests))


def estimate_vma(sessions: list[tuple[date, list[dict]]], threshold_pace: float, hr_max: float | None,
                 end: date, window_days: int = 42) -> dict | None:
    """VMA from the best interval sessions in the window: the mean of the top two session estimates
    (the athlete's capacity shows in their best-executed sessions, not in the easy ones)."""
    per = []
    for d, reps in sessions:
        if 0 <= (end - d).days < window_days:
            v = session_vma(reps, threshold_pace, hr_max)
            if v:
                per.append((v, d))
    if not per:
        return None
    per.sort(reverse=True)
    top = per[:2]
    return {"vma": float(np.mean([v for v, _ in top])), "sessions": [d.isoformat() for _, d in top]}


def projection_from_current(current: float, series: list[tuple[date, float]], target_day: date, today: date,
                            default_gain: float = 0.004, max_gain: float = 0.008) -> dict:
    """Race-day projection from today's estimate. The weekly improvement rate comes from the recent trend
    when there is enough of it, clamped to [0, max_gain] (a training block doesn't make you slower, and
    >0.8 %/week over months isn't realistic); otherwise a typical 0.4 %/week. The range spans ±0.3 %/week."""
    gain, basis = default_gain, "typique"
    if len(series) >= 4 and (series[-1][0] - series[0][0]).days >= 21:
        x = np.array([(d - series[0][0]).days for d, _ in series], float)
        y = np.array([v for _, v in series], float)
        coef = np.polyfit(x, y, 1)
        resid = y - np.polyval(coef, x)
        r2 = 1 - float(np.sum(resid**2)) / float(np.sum((y - y.mean()) ** 2) or 1)
        # Only trust a clean trend: a noisy series mostly reflects which sessions fall in the window.
        if r2 >= 0.5:
            gain, basis = min(max_gain, max(0.0, -coef[0] * 7 / y[-1])), "tendance"
    weeks = max(0.0, (target_day - today).days / 7)
    at = lambda g: current * (1 - g) ** weeks  # noqa: E731
    return {"current": current, "projected": at(gain), "low": at(min(max_gain + 0.002, gain + 0.003)),
            "high": at(max(0.0, gain - 0.003)), "gain_per_week": gain, "basis": basis, "weeks": weeks}


def prob_under(target: float, proj: dict) -> float:
    sd = max(1.0, (proj["high"] - proj["low"]) / 2)
    z = (target - proj["projected"]) / sd
    return float(0.5 * (1 + math.erf(z / math.sqrt(2))))
