"""Per-activity metrics computed from the 1 Hz record stream."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from coach.metrics.zones import HR_ZONES, PACE_ZONES, Athlete, hr_zone_index, speed_zone_index

MOVING_SPEED = 1.2  # m/s; below this the athlete is walking or stopped
BEST_DISTANCES = [400, 1000, 1609, 3000, 5000, 10000, 21097]
BEST_DURATIONS = [180, 360, 720, 1200, 1800]


def minetti_factor(grade: np.ndarray) -> np.ndarray:
    """Energy cost of running on a slope relative to flat ground (Minetti et al. 2002)."""
    g = np.clip(grade, -0.45, 0.45)
    cost = 155.4 * g**5 - 30.4 * g**4 - 43.3 * g**3 + 46.3 * g**2 + 19.5 * g + 3.6
    return cost / 3.6


def grade_series(df: pd.DataFrame) -> np.ndarray:
    if df["altitude"].isna().all():
        return np.zeros(len(df))
    alt = df["altitude"].interpolate(limit_direction="both").rolling(15, center=True, min_periods=1).mean()
    dist = df["distance"]
    d_alt = alt.diff(10)
    d_dist = dist.diff(10)
    grade = (d_alt / d_dist.where(d_dist > 5)).fillna(0).clip(-0.4, 0.4)
    return grade.rolling(10, center=True, min_periods=1).mean().to_numpy()


def trimp(hr: np.ndarray, a: Athlete) -> float:
    hr = hr[~np.isnan(hr)]
    if not len(hr):
        return 0.0
    k, b = (0.64, 1.92) if a.sex.upper().startswith("M") else (0.86, 1.67)
    hrr = np.clip((hr - a.hr_rest) / (a.hr_max - a.hr_rest), 0, 1.1)
    return float(np.sum(hrr * k * np.exp(b * hrr)) / 60.0)


def trimp_hour_at_lthr(a: Athlete) -> float:
    return trimp(np.full(3600, float(a.lt_hr)), a)


def best_efforts(t: np.ndarray, dist: np.ndarray) -> dict[str, float]:
    """Fastest time (s) to cover each standard distance anywhere in the activity."""
    out = {}
    if len(dist) < 2:
        return out
    for d in BEST_DISTANCES:
        if dist[-1] - dist[0] < d:
            continue
        j = np.searchsorted(dist, dist + d)
        ok = j < len(dist)
        if not ok.any():
            continue
        times = t[j[ok]] - t[ok]
        out[str(d)] = float(times.min())
    return out


def best_durations(speed: np.ndarray) -> dict[str, float]:
    """Best average speed (m/s) held for each duration."""
    out = {}
    s = pd.Series(np.nan_to_num(speed))
    for w in BEST_DURATIONS:
        if len(s) >= w:
            out[str(w)] = float(s.rolling(w).mean().max())
    return out


def decoupling(df: pd.DataFrame, gap_speed: np.ndarray, moving: np.ndarray) -> dict | None:
    """Aerobic decoupling (Pa:HR) and heart-rate drift over the steady part of the run."""
    n = len(df)
    start = max(600, int(0.1 * n))
    end = n - 120
    idx = np.arange(n)
    sel = moving & (idx >= start) & (idx < end) & ~np.isnan(df["hr"].to_numpy())
    if sel.sum() < 1200:
        return None
    pos = np.flatnonzero(sel)
    half = pos[len(pos) // 2]
    first, second = sel & (idx < half), sel & (idx >= half)
    hr = df["hr"].to_numpy()
    ef1 = gap_speed[first].mean() / hr[first].mean()
    ef2 = gap_speed[second].mean() / hr[second].mean()
    return {
        "decoupling_pct": float((ef1 - ef2) / ef1 * 100),
        "hr_first": float(hr[first].mean()),
        "hr_second": float(hr[second].mean()),
        "pace_first": float(1000 / gap_speed[first].mean()),
        "pace_second": float(1000 / gap_speed[second].mean()),
    }


def compute_session_metrics(df: pd.DataFrame, a: Athlete, session: dict | None = None) -> dict:
    session = session or {}
    if df.empty:
        return {}
    speed = df["speed"].fillna(0).to_numpy()
    hr = df["hr"].to_numpy(dtype=float)
    t = df["elapsed"].to_numpy()
    dist = df["distance"].to_numpy()
    moving = speed > MOVING_SPEED
    grade = grade_series(df)
    gap_speed = speed * minetti_factor(grade)

    moving_s = float(moving.sum())
    distance_m = float(session.get("distance_m") or (dist[-1] - dist[0]))
    ngp = 0.0
    if moving.any():
        rolled = pd.Series(np.where(moving, gap_speed, 0.0)).rolling(30, min_periods=1).mean().to_numpy()[moving]
        ngp = float(np.mean(rolled**4) ** 0.25)
    intensity = ngp / a.threshold_speed if ngp else 0.0
    rtss = moving_s / 3600 * intensity**2 * 100
    tr = trimp(hr[moving] if moving.any() else hr, a)
    hrtss = tr / trimp_hour_at_lthr(a) * 100 if tr else 0.0
    has_hr = not np.isnan(hr).all()
    avg_hr = float(np.nanmean(hr[moving])) if has_hr and moving.any() else None

    zones_hr, zones_pace = {}, {}
    if has_hr and moving.any():
        zi = hr_zone_index(hr[moving & ~np.isnan(hr)], a)
        tot = len(zi) or 1
        zones_hr = {HR_ZONES[i][0]: float((zi == i).sum() / tot) for i in range(len(HR_ZONES))}
    if moving.any():
        zi = speed_zone_index(gap_speed[moving], a)
        zones_pace = {PACE_ZONES[i][0]: float((zi == i).sum() / len(zi)) for i in range(len(PACE_ZONES))}

    cad = df["cadence"].to_numpy(dtype=float)
    cad_m = cad[moving & ~np.isnan(cad)] if moving.any() else np.array([])
    avg_cad = float(cad_m.mean()) if len(cad_m) else None
    alt = df["altitude"]
    ascent = session.get("ascent_m")
    if ascent is None and alt.notna().any():
        sm = alt.interpolate(limit_direction="both").rolling(15, center=True, min_periods=1).mean().diff()
        ascent = float(sm[sm > 0].sum())

    rolling_speed = pd.Series(speed).rolling(60, min_periods=30).mean()[moving]
    avg_speed = distance_m / moving_s if moving_s else 0.0
    return {
        "distance_m": distance_m,
        "moving_s": moving_s,
        "elapsed_s": float(t[-1] - t[0]) if len(t) else 0.0,
        "avg_pace": 1000 / avg_speed if avg_speed else None,
        "ngp_pace": 1000 / ngp if ngp else None,
        "avg_hr": avg_hr,
        "max_hr": float(np.nanmax(hr)) if has_hr else None,
        "hr_p99": float(np.nanpercentile(hr, 99)) if has_hr else None,
        "intensity_factor": intensity,
        "rtss": rtss,
        "trimp": tr,
        "hrtss": hrtss,
        "load": rtss if ngp and not math.isnan(rtss) else hrtss,
        "ef": (ngp * 60 / avg_hr) if avg_hr and ngp else None,
        "decoupling": decoupling(df, gap_speed, moving) if has_hr else None,
        "zones_hr": zones_hr,
        "zones_pace": zones_pace,
        "cadence": avg_cad,
        "stride_m": (avg_speed * 60 / avg_cad) if avg_cad else None,
        "ascent_m": ascent,
        "pace_cv": float(rolling_speed.std() / rolling_speed.mean()) if len(rolling_speed.dropna()) > 60 else None,
        "best_efforts": best_efforts(t, dist),
        "best_durations": best_durations(speed),
    }
