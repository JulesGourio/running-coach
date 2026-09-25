"""Match the steps of a planned COROS workout to what was actually run, and detect quality efforts
(fast contiguous stretches) directly from the data — the same idea whether or not there's a plan."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

TOLERANCE_S = 3  # s/km of slack around a target pace range
QUALITY_GATE = 0.88  # fraction of threshold speed a stretch must sustain to count as a "quality" effort (Z3+)


@dataclass
class Step:
    kind: str  # warmup | work | recovery | cooldown
    target_type: int  # 1 distance (m), 2 time (s), 4 free
    target_value: float | None
    pace_lo: float | None  # fastest allowed pace, s/km
    pace_hi: float | None  # slowest allowed pace, s/km
    group: int | None = None
    rep: int | None = None


KINDS = {1: "warmup", 2: "work", 3: "recovery", 4: "cooldown"}


def _pace_range(s: dict) -> tuple[float | None, float | None]:
    if s.get("intensityType") == 2 and s.get("intensityValueStart"):
        a, b = s["intensityValueStart"], s.get("intensityValueEnd", s["intensityValueStart"])
        return float(min(a, b)), float(max(a, b))
    return None, None


def flatten_course(course: dict) -> list[Step]:
    steps: list[Step] = []
    for gi, s in enumerate(course.get("sections") or []):
        if s.get("intervalGroup"):
            for r in range(int(s.get("repeats") or 1)):
                for m in s.get("sets") or []:
                    lo, hi = _pace_range(m)
                    steps.append(Step(KINDS.get(m.get("sectionType"), "work"), m.get("targetType"),
                                      m.get("targetValue"), lo, hi, gi, r + 1))
        else:
            lo, hi = _pace_range(s)
            steps.append(Step(KINDS.get(s.get("sectionType"), "work"), s.get("targetType"), s.get("targetValue"), lo, hi))
    return steps


def is_stride(step: Step) -> bool:
    """Short accelerations tacked onto an easy run (under 200 m or 40 s): not a quality rep."""
    return bool(step.target_value) and ((step.target_type == 1 and step.target_value < 200)
                                        or (step.target_type == 2 and step.target_value < 40))


def is_quality(step: Step, threshold_pace: float) -> bool:
    """A work step whose target is faster than easy running (about 115 % of threshold pace), strides excluded."""
    return (step.kind == "work" and step.pace_hi is not None and step.pace_hi < threshold_pace * 1.15
            and not is_stride(step))


def _fits(lap: dict, st: Step) -> bool:
    if st.target_type == 1 and st.target_value:
        return lap.get("distance_m") is not None and abs(lap["distance_m"] - st.target_value) <= 0.2 * st.target_value + 30
    if st.target_type == 2 and st.target_value:
        dur = lap.get("timer_s") or lap.get("elapsed_s")
        return dur is not None and abs(dur - st.target_value) <= 0.2 * st.target_value + 10
    return True


def _from_laps(steps: list[Step], laps: list[dict]) -> list[dict] | None:
    """Structured workouts on the watch create one lap per step; use them when they line up."""
    if len(laps) < len(steps):
        return None
    offset_ok = None
    for off in range(0, len(laps) - len(steps) + 1):
        if all(_fits(laps[off + i], st) for i, st in enumerate(steps) if st.kind in ("work", "recovery")):
            offset_ok = off
            break
    if offset_ok is None:
        return None
    out = []
    for i, st in enumerate(steps):
        lap = laps[offset_ok + i]
        dur = lap.get("timer_s") or lap.get("elapsed_s")
        d = lap.get("distance_m")
        out.append({"duration_s": dur, "distance_m": d, "avg_hr": lap.get("avg_hr"),
                    "pace": dur / d * 1000 if dur and d else None, "source": "tour"})
    return out


def _window_len(st: Step, speed_hint: float) -> int:
    if st.target_type == 2 and st.target_value:
        return int(st.target_value)
    if st.target_type == 1 and st.target_value:
        return int(st.target_value / max(speed_hint, 1.5))
    return 0


def _from_stream(steps: list[Step], df: pd.DataFrame, threshold_pace: float) -> list[dict | None]:
    """Find the fastest non-overlapping windows matching each quality step, in chronological order."""
    out: list[dict | None] = [None] * len(steps)
    speed = df["speed"].fillna(0).to_numpy()
    dist = df["distance"].to_numpy()
    hr = df["hr"].to_numpy(dtype=float)
    taken = np.zeros(len(speed), dtype=bool)
    quality = [i for i, st in enumerate(steps) if is_quality(st, threshold_pace)]
    found = []
    for i in quality:
        st = steps[i]
        hint = 1000 / ((st.pace_lo + st.pace_hi) / 2) if st.pace_lo else 3.5
        w = _window_len(st, hint)
        if w < 20 or w >= len(speed):
            continue
        avg = pd.Series(speed).rolling(w).mean().to_numpy(copy=True)
        blocked = pd.Series(taken.astype(float)).rolling(w).max().to_numpy() > 0
        avg[blocked | np.isnan(avg)] = -1
        end = int(np.argmax(avg))
        if avg[end] <= 0:
            continue
        start = end - w + 1
        taken[max(0, start - 30):end + 30] = True
        d = float(dist[end] - dist[start])
        found.append((start, i, {"duration_s": float(w), "distance_m": d,
                                 "avg_hr": float(np.nanmean(hr[start:end + 1])) if not np.isnan(hr[start:end + 1]).all() else None,
                                 "pace": w / d * 1000 if d > 0 else None, "source": "flux"}))
    found.sort()
    for (_, i, res), j in zip(found, sorted(i for _, i, _ in found)):
        out[j] = res
    return out


def rep_score(delta_s: float | None) -> float:
    """1 inside the target (with tolerance), then decreasing with the gap to the range."""
    if delta_s is None:
        return 0.0
    gap = abs(delta_s)
    for limit, value in ((TOLERANCE_S, 1.0), (6, 0.75), (10, 0.5), (15, 0.25)):
        if gap <= limit:
            return value
    return 0.0


def evaluate_steps(course: dict, df: pd.DataFrame, laps: list[dict], threshold_pace: float) -> dict:
    steps = flatten_course(course)
    matched = _from_laps(steps, laps) or _from_stream(steps, df, threshold_pace)
    reps = []
    for st, m in zip(steps, matched):
        if not is_quality(st, threshold_pace):
            continue
        row = {"step": asdict(st), "done": m, "status": "non trouvée", "delta_s": None}
        if m and m.get("pace"):
            p = m["pace"]
            if p < st.pace_lo - TOLERANCE_S:
                row["status"], row["delta_s"] = "trop rapide", p - st.pace_lo
            elif p > st.pace_hi + TOLERANCE_S:
                row["status"], row["delta_s"] = "trop lente", p - st.pace_hi
            else:
                row["status"], row["delta_s"] = "dans la cible", 0.0
        row["rep_score"] = rep_score(row["delta_s"]) if m and m.get("pace") else 0.0
        reps.append(row)
    paces = [r["done"]["pace"] for r in reps if r["done"] and r["done"].get("pace")]
    return {
        "reps": reps,
        "n_planned": len(reps),
        "n_found": sum(1 for r in reps if r["done"]),
        "n_on_target": sum(1 for r in reps if r["status"] == "dans la cible"),
        "score": round(10 * sum(r["rep_score"] for r in reps) / len(reps), 1) if reps else None,
        "pace_sd": float(np.std(paces)) if len(paces) > 1 else None,
        "fade_s": float(paces[-1] - paces[0]) if len(paces) > 1 else None,
        "method": next((m["source"] for m in matched if m), None),
    }


LAP_ACTIVE, LAP_REST, LAP_WARMUP, LAP_COOLDOWN = 0, 1, 2, 3  # FIT lap "intensity"


def _hr_mean(hr: np.ndarray, s: int, e: int) -> float | None:
    seg = hr[s:e + 1]
    return float(np.nanmean(seg)) if len(seg) and not np.all(np.isnan(seg)) else None


def segments_from_laps(df: pd.DataFrame, laps: list[dict], threshold_pace: float,
                       max_ratio: float = 1.14) -> list[dict] | None:
    """Reps straight from the watch laps, when the laps describe them: a structured workout (laps tagged
    warm-up / active / rest / cool-down) or manual laps. Distance and time are the watch's own, the numbers
    shown in the COROS app — GPS-stream detection trims reps a few metres short and blurs their edges. A lap
    is a rep if it's faster than 114 % of threshold pace (and active, when laps are tagged); consecutive fast
    laps are one continuous effort. Auto-laps every km (or mile) say nothing about reps: returns None."""
    if len(laps) < 3 or df.empty:
        return None
    body = [lp.get("distance_m") or 0 for lp in laps[:-1]]
    if all(abs(d - 1000) < 40 for d in body) or all(abs(d - 1609) < 60 for d in body):
        return None
    tagged = any(lp.get("intensity") in (LAP_REST, LAP_WARMUP, LAP_COOLDOWN) for lp in laps)
    ts = df["timestamp"]
    hr = df["hr"].to_numpy(dtype=float)
    groups: list[list[dict]] = []
    prev_fast = False
    for lp in laps:
        d, t = lp.get("distance_m") or 0, lp.get("timer_s") or lp.get("elapsed_s") or 0
        fast = (d >= 100 and t >= 20 and t / d * 1000 < threshold_pace * max_ratio
                and (not tagged or lp.get("intensity") in (LAP_ACTIVE, None)))
        if fast:
            if prev_fast:
                groups[-1].append(lp)
            else:
                groups.append([lp])
        prev_fast = fast
    if len(groups) < 1 or (len(groups) == 1 and not tagged and len(laps) > 3):
        return None
    out = []
    for g in groups:
        d = sum(lp["distance_m"] for lp in g)
        t = sum(lp.get("timer_s") or lp.get("elapsed_s") for lp in g)
        s_i = int(ts.searchsorted(pd.Timestamp(g[0]["start_time"])))
        end_t = g[-1].get("end_time") or (pd.Timestamp(g[-1]["start_time"]) + pd.Timedelta(seconds=g[-1].get("elapsed_s") or t))
        e_i = max(s_i, min(len(df) - 1, int(ts.searchsorted(pd.Timestamp(end_t))) - 1))
        lap_hr = [lp["avg_hr"] for lp in g if lp.get("avg_hr")]
        out.append({"start_idx": s_i, "end_idx": e_i, "duration_s": float(t), "distance_m": float(d),
                    "avg_pace": t / d * 1000, "source": "tour",
                    "avg_hr": float(np.average(lap_hr, weights=[lp.get("timer_s") or 1 for lp in g if lp.get("avg_hr")]))
                    if lap_hr else _hr_mean(hr, s_i, e_i)})
    return out


def quality_segments(df: pd.DataFrame, threshold_pace: float, gate: float = QUALITY_GATE,
                      min_dur_s: float = 15, merge_gap_s: float = 20, laps: list[dict] | None = None) -> list[dict]:
    """The real repetitions of a session, whether or not a plan course exists — how an off-plan session gets
    typed and evaluated, and how best-effort extraction (session.py) avoids diluting fast reps with the
    recovery between them. Watch laps first (segments_from_laps); otherwise contiguous stretches of sustained
    fast running (at or under `gate` fraction of threshold pace) in the GPS stream, merging brief dips and
    trimmed to the steady core of each rep (the acceleration and slowing-down at its edges would otherwise
    make every rep look several s/km slower than it was)."""
    if df.empty:
        return []
    if laps:
        from_laps = segments_from_laps(df, laps, threshold_pace)
        if from_laps is not None:
            return [s for s in from_laps if s["duration_s"] >= min_dur_s]
    speed = df["speed"].fillna(0).to_numpy()
    t = df["elapsed"].to_numpy()
    dist = df["distance"].to_numpy()
    hr = df["hr"].to_numpy(dtype=float)
    # a short rolling smooth so one noisy GPS sample doesn't split a rep in two
    sm = pd.Series(speed).rolling(5, min_periods=1, center=True).mean().to_numpy()
    gate_speed = gate * 1000 / threshold_pace
    idx = np.flatnonzero(sm >= gate_speed)
    if not len(idx):
        return []
    spans, start, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if t[i] - t[prev] > merge_gap_s:
            spans.append((start, prev))
            start = i
        prev = i
    spans.append((start, prev))
    out = []
    for s, e in spans:
        if t[e] - t[s] >= 20:  # trim the ramps: keep from first to last second at >= 94 % of the rep's median speed
            core = np.median(sm[s:e + 1])
            ok = np.flatnonzero(sm[s:e + 1] >= 0.94 * core)
            if len(ok):
                s, e = s + int(ok[0]), s + int(ok[-1])
        dur = float(t[e] - t[s])
        if dur < min_dur_s:
            continue
        d = float(dist[e] - dist[s])
        if d > 150 and dur / d * 1000 < 170:  # > 21 km/h held over 150 m: a GPS jump, not a rep
            continue
        out.append({"start_idx": int(s), "end_idx": int(e), "duration_s": dur, "distance_m": d,
                    "avg_pace": dur / d * 1000 if d > 0 else None, "source": "flux",
                    "avg_hr": _hr_mean(hr, s, e)})
    return out


def planned_distance(course: dict, easy_pace: float = 360) -> float:
    total = 0.0
    for st in flatten_course(course):
        if st.target_type == 1 and st.target_value:
            total += st.target_value
        elif st.target_type == 2 and st.target_value:
            pace = (st.pace_lo + st.pace_hi) / 2 if st.pace_lo else easy_pace
            total += st.target_value / pace * 1000
    return total
