"""Per-activity metrics computed from the 1 Hz record stream."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from coach.metrics.intervals import quality_segments
from coach.metrics.zones import HR_ZONES, PACE_ZONES, Athlete, hr_zone_index, speed_zone_index

MOVING_SPEED = 0.8  # m/s of effort (grade-adjusted): below this the athlete is stopped. Low enough that a steep
# hike or a walked recovery counts as moving, like the COROS timer does; a stop with GPS drift doesn't.
GRADE_BINS = [(-1, -0.15, "< -15 %"), (-0.15, -0.08, "-15 à -8 %"), (-0.08, -0.03, "-8 à -3 %"), (-0.03, 0.03, "plat"),
              (0.03, 0.08, "3 à 8 %"), (0.08, 0.15, "8 à 15 %"), (0.15, 0.25, "15 à 25 %"), (0.25, 1, "> 25 %")]
BEST_DISTANCES = [400, 1000, 1609, 3000, 5000, 10000, 21097]
RECORD_DISTANCES = [400, 1000, 1609, 3000, 5000, 10000, 15000, 21097, 30000, 42195]
BEST_DURATIONS = [180, 360, 720, 1200, 1800]


def minetti_factor(grade: np.ndarray) -> np.ndarray:
    """Energy cost of running on a slope relative to flat ground (Minetti et al. 2002)."""
    g = np.clip(grade, -0.45, 0.45)
    cost = 155.4 * g**5 - 30.4 * g**4 - 43.3 * g**3 + 46.3 * g**2 + 19.5 * g + 3.6
    return cost / 3.6


def effort_factor(grade: np.ndarray) -> np.ndarray:
    """Cost of running on a slope relative to flat ground, fitted on real runners' heart rate (the curve behind
    Strava's grade-adjusted pace): +40 % at +10 %, about -12 % at -10 %, and steep descents cost again (braking).
    Minetti's lab curve overstates what a steep descent gives back, so it isn't used for the effort pace."""
    g = np.clip(np.asarray(grade, dtype=float) * 100, -20, 40)
    return 1 + 0.0275 * g + 0.0015 * g**2


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


def best_efforts(t: np.ndarray, dist: np.ndarray, segments: list[dict]) -> dict[str, float]:
    """Fastest time (s) to cover each standard distance, searched within a single quality segment at a
    time — never across the recovery between two reps. On a broken-up interval session this is the
    difference between a real best 1 km and a fake "best 10 km" that's actually the whole session average,
    recovery jogs included."""
    out: dict[str, float] = {}
    for seg in segments:
        if seg.get("source") == "tour":  # a watch lap of (about) that distance: its own time, as in the COROS app
            for d in BEST_DISTANCES:
                if abs(seg["distance_m"] - d) <= 0.03 * d:
                    k, best_t = str(d), seg["duration_s"] * d / seg["distance_m"]
                    if k not in out or best_t < out[k]:
                        out[k] = best_t
        s0, e0 = seg["start_idx"], seg["end_idx"] + 1
        tt, dd = t[s0:e0], dist[s0:e0]
        if len(dd) < 2:
            continue
        for d in BEST_DISTANCES:
            if dd[-1] - dd[0] < d:
                continue
            j = np.searchsorted(dd, dd + d)
            ok = j < len(dd)
            if not ok.any():
                continue
            best_t = float((tt[j[ok]] - tt[ok]).min())
            k = str(d)
            if k not in out or best_t < out[k]:
                out[k] = best_t
    return out


def track(df: pd.DataFrame, max_points: int = 400) -> list[list[float]]:
    """Downsampled route [lat, lon, altitude, km] for maps (the full FIT isn't read to draw every route)."""
    g = df.dropna(subset=["lat", "lon"]) if "lat" in df else df.iloc[0:0]
    if g.empty:
        return []
    g = g.iloc[:: max(1, len(g) // max_points)]
    alt = g["altitude"].fillna(-1) if "altitude" in g else pd.Series(-1, index=g.index)
    return [[round(la, 5), round(lo, 5), round(float(al), 1), round(float(d or 0) / 1000, 3)]
            for la, lo, al, d in zip(g["lat"], g["lon"], alt, g["distance"].fillna(0))]


def records(t: np.ndarray, dist: np.ndarray, cad: np.ndarray | None = None, alt: np.ndarray | None = None) -> dict[str, float]:
    """Personal-record style bests: fastest time over each distance anywhere in the run, on the continuous stream
    (like Strava or COROS best efforts). Not used for fitness estimates (a broken-up interval session would be
    diluted), only as records: a race or a tempo run sets them."""
    out: dict[str, float] = {}
    if len(dist) < 2:
        return out
    # GPS jumps: more than 8 m covered in one second (29 km/h). A window containing one isn't a record.
    step = np.diff(dist, prepend=dist[0]) / np.maximum(np.diff(t, prepend=t[0] - 1), 1)
    bad = step > 8.0
    if cad is not None and len(cad) == len(dist):
        # fast but not at a running cadence: a car, a bike or a lift recorded in running mode
        fast = pd.Series(step).rolling(10, min_periods=1, center=True).mean().to_numpy() > 5.5
        bad |= fast & ~(np.nan_to_num(cad, nan=0) >= 150)
    glitches = np.cumsum(bad)
    for d in RECORD_DISTANCES:
        if dist[-1] - dist[0] < d:
            continue
        j = np.searchsorted(dist, dist + d)
        ok = np.flatnonzero(j < len(dist))
        if not len(ok):
            continue
        clean = glitches[j[ok]] == glitches[ok]
        if alt is not None and len(alt) == len(dist) and not np.all(np.isnan(alt)):
            a_f = pd.Series(alt).interpolate(limit_direction="both").to_numpy()
            clean &= (a_f[ok] - a_f[j[ok]]) / d <= 0.015  # net descent over 1.5 %: downhill-aided, not a record
        times = (t[j[ok]] - t[ok])[clean]
        # and no average faster than 23 km/h beyond 400 m (8 m/s over 400 m): beyond any amateur, so bad data
        cap = d / (8.0 if d <= 400 else 6.4)
        times = times[times >= cap]
        if len(times):
            out[str(d)] = float(times.min())
    return out


def best_durations(speed: np.ndarray, segments: list[dict]) -> dict[str, float]:
    """Best average speed (m/s) held for each duration, within a single quality segment at a time (see
    best_efforts)."""
    out: dict[str, float] = {}
    for seg in segments:
        s0, e0 = seg["start_idx"], seg["end_idx"] + 1
        sp = pd.Series(np.nan_to_num(speed[s0:e0]))
        for w in BEST_DURATIONS:
            if len(sp) >= w:
                v = float(sp.rolling(w).mean().max())
                k = str(w)
                if k not in out or v > out[k]:
                    out[k] = v
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


def hr_speed_fit(hr: np.ndarray, gap_speed: np.ndarray, moving: np.ndarray, segments: list[dict]) -> dict | None:
    """Grade-adjusted speed against heart rate within one interval session: 60 s steady windows of the warm-up
    (after 5 min, before the first rep) and the second half of each rep of 2 min or more (heart rate lags at the
    start of an effort). Same day, same conditions: the line is clean enough to extrapolate towards max HR, which
    gives the speed at VO2max even when the reps weren't run flat out."""
    reps = [g for g in segments if g["duration_s"] >= 120]
    if len(reps) < 2 or np.isnan(hr).all():
        return None
    pts = []
    for st in range(300, reps[0]["start_idx"] - 60, 60):
        w = slice(st, st + 60)
        if moving[w].mean() > 0.95 and np.std(gap_speed[w]) < 0.3 and np.isnan(hr[w]).mean() < 0.2:
            pts.append((float(np.nanmean(hr[w])), float(np.mean(gap_speed[w]))))
    n_wu = len(pts)
    for g in reps:
        n = g["end_idx"] - g["start_idx"]
        w = slice(g["start_idx"] + n // 2, g["end_idx"] + 1)
        if np.isnan(hr[w]).mean() < 0.2:
            pts.append((float(np.nanmean(hr[w])), float(np.mean(gap_speed[w]))))
    if n_wu < 3 or len(pts) - n_wu < 2:
        return None
    x, y = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
    if x.max() - x.min() < 25:
        return None
    slope, intercept = np.polyfit(x, y, 1)
    r2 = float(np.corrcoef(x, y)[0, 1] ** 2)
    return {"slope": float(slope), "intercept": float(intercept), "r2": r2, "n": len(pts),
            "hr_top": float(x.max()), "hr_low": float(x.min())}


def compute_session_metrics(df: pd.DataFrame, a: Athlete, session: dict | None = None,
                            laps: list[dict] | None = None) -> dict:
    session = session or {}
    if df.empty:
        return {}
    speed = df["speed"].fillna(0).to_numpy()
    hr = df["hr"].to_numpy(dtype=float)
    t = df["elapsed"].to_numpy()
    dist = df["distance"].to_numpy()
    grade = grade_series(df)
    gap_speed = speed * effort_factor(grade)
    moving = np.maximum(speed, gap_speed) > MOVING_SPEED

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
    descent = session.get("descent_m")
    climb_rate = None
    if alt.notna().any():
        sm = alt.interpolate(limit_direction="both").rolling(15, center=True, min_periods=1).mean().diff().fillna(0)
        if ascent is None:
            ascent = float(sm[sm > 0].sum())
        if descent is None:
            descent = float(-sm[sm < 0].sum())
        up = moving & (grade > 0.05)
        if up.sum() > 300:  # vertical metres per hour while climbing
            climb_rate = float(sm.to_numpy()[up].clip(min=0).sum() / up.sum() * 3600)
    flat_equiv = float(gap_speed[moving].sum()) if moving.any() else 0.0  # distance on flat ground for the same effort

    rolling_speed = pd.Series(speed).rolling(60, min_periods=30).mean()[moving]
    avg_speed = distance_m / moving_s if moving_s else 0.0
    segments = quality_segments(df, a.threshold_pace, laps=laps)
    for sg in segments:  # mean slope of each rep, to recognise hill repeats
        sg["grade"] = float(np.mean(grade[sg["start_idx"]:sg["end_idx"] + 1])) if sg["end_idx"] >= sg["start_idx"] else 0.0
    flat = [sg for sg in segments if sg["grade"] > -0.03]  # a downhill stretch isn't a best effort
    return {
        "distance_m": distance_m,
        "moving_s": moving_s,
        "elapsed_s": float(t[-1] - t[0]) if len(t) else 0.0,
        "avg_pace": 1000 / avg_speed if avg_speed else None,
        "ngp_pace": 1000 / ngp if ngp else None,
        "avg_hr": avg_hr,
        # max over 5 s: a one-second optical spike isn't a max heart rate
        "max_hr": float(pd.Series(hr).rolling(5, min_periods=3).median().max()) if has_hr else None,
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
        "descent_m": descent,
        "climb_rate": climb_rate,
        "effort_pace": moving_s * 1000 / flat_equiv if flat_equiv > 100 else None,
        "splits": km_splits(df, grade, moving),
        "grade_bins": grade_bins(speed, grade, moving),
        "pace_cv": float(rolling_speed.std() / rolling_speed.mean()) if len(rolling_speed.dropna()) > 60 else None,
        "best_efforts": best_efforts(t, dist, flat),
        "records": records(t, dist, cad, df["altitude"].to_numpy(dtype=float)),
        "track": track(df),
        "best_durations": best_durations(speed, flat),
        "quality_segments": segments,
        "hr_speed": hr_speed_fit(hr, gap_speed, moving, segments) if has_hr else None,
    }


def km_splits(df: pd.DataFrame, grade: np.ndarray, moving: np.ndarray) -> list[dict]:
    """One row per km: moving time, pace, effort pace (grade-adjusted), climb, descent, mean grade, HR."""
    dist = df["distance"].ffill().fillna(0).to_numpy()
    if not len(dist) or dist[-1] < 500:
        return []
    speed = df["speed"].fillna(0).to_numpy()
    gap = speed * effort_factor(grade)
    alt = df["altitude"].interpolate(limit_direction="both").rolling(15, center=True, min_periods=1).mean().diff().fillna(0).to_numpy()         if df["altitude"].notna().any() else np.zeros(len(df))
    hr = df["hr"].to_numpy(dtype=float)
    km = (dist // 1000).astype(int)
    out = []
    for k in range(int(km.max()) + 1):
        w = (km == k)
        mv = w & moving
        length = float(min(dist[w].max(), (k + 1) * 1000) - k * 1000) if w.any() else 0
        if length < 200 or mv.sum() < 30:
            continue
        t_ = float(mv.sum())
        flat = float(gap[mv].sum())
        out.append({"km": k + 1, "length": length, "time_s": t_, "pace": t_ * 1000 / length,
                    "effort_pace": t_ * 1000 / flat if flat > 50 else None,
                    "up": float(alt[w].clip(min=0).sum()), "down": float(-alt[w].clip(max=0).sum()),
                    "grade": float(alt[w].sum() / length), "hr": float(np.nanmean(hr[mv])) if not np.isnan(hr[mv]).all() else None})
    return out


def grade_bins(speed: np.ndarray, grade: np.ndarray, moving: np.ndarray) -> list[dict]:
    """Time share and average speed by slope class: how fast you climb and descend."""
    tot = moving.sum()
    if tot < 300:
        return []
    out = []
    for lo, hi, name in GRADE_BINS:
        w = moving & (grade >= lo) & (grade < hi)
        if w.sum() >= 30:
            out.append({"name": name, "share": float(w.sum() / tot), "speed": float(speed[w].mean()),
                        "vert_m_h": float((speed[w] * grade[w]).mean() * 3600)})
    return out
