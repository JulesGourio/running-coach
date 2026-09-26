"""Sleep: what is advised for the coming night, debt, regularity, phases and averages by period."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

TARGET_MIN = 480  # 8 h: the usual advice for an endurance athlete in training (adults in general: 7-9 h)
PHASE_REF = {"deep_pct": (13, 23), "light_pct": (45, 60), "rem_pct": (20, 25), "awake_pct": (0, 5)}
PHASE_FR = {"deep_pct": "Profond", "light_pct": "Léger", "rem_pct": "Paradoxal (REM)", "awake_pct": "Éveil"}
WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["night"] = df["date"] - pd.Timedelta(days=1)  # rows are dated by the wake-up morning
    # The long-history summaries only give bed and wake times: rebuild the durations from them.
    window = (pd.to_datetime(df["waketime"]) - pd.to_datetime(df["bedtime"])).dt.total_seconds() / 60
    window = window.where((window > 60) & (window < 16 * 60))
    df["main_period_min"] = df["main_period_min"].fillna(window)
    df["main_min"] = df["main_min"].fillna(window - df["awake_min"].fillna(window * df["awake_pct"].fillna(0) / 100))
    df["total_min"] = df["total_min"].fillna(df["main_min"] + df["naps_min"].fillna(0))
    for k in ("deep", "light", "rem", "awake"):
        df[f"{k}_min"] = df["main_period_min"].fillna(df["main_min"]) * df[f"{k}_pct"] / 100
    df["naps_min"] = df["naps_min"].fillna(0)
    df["n_naps"] = df["naps"].map(len)
    df["bed_h"] = df["bedtime"].map(_clock_evening)
    df["wake_h"] = df["waketime"].map(_clock)
    return df


def _clock(ts: str | None) -> float | None:
    if not ts:
        return None
    t = datetime.strptime(ts, "%Y-%m-%d %H:%M")
    return t.hour + t.minute / 60


def _clock_evening(ts: str | None) -> float | None:
    """Bedtime as hours after noon of the evening before (23:30 -> 11.5, 01:42 -> 13.7), so it averages right."""
    h = _clock(ts)
    return None if h is None else (h - 12 if h >= 12 else h + 12)


def hhmm(h: float | None, evening: bool = False) -> str:
    if h is None or h != h:
        return "—"
    if evening:
        h = h + 12
    h %= 24
    return f"{int(h):02d}:{int(round((h % 1) * 60)) % 60:02d}"


def debt(df: pd.DataFrame, days: int = 7, target: float = TARGET_MIN) -> float:
    """Minutes short of the target over the last `days` nights (naps count), never negative per night."""
    last = df.tail(days)
    return float(np.clip(target - last["total_min"].fillna(0), 0, None).sum()) if len(last) else 0.0


def recommended(df: pd.DataFrame, hard_yesterday: bool, load_ratio: float | None, today: date) -> dict:
    """Sleep advised for the coming night and the matching bedtime, from the usual wake-up time."""
    mins, why = TARGET_MIN, ["8 h de base pour un coureur à l'entraînement."]
    if hard_yesterday:
        mins += 30
        why.append("+30 min : séance dure aujourd'hui.")
    if load_ratio and load_ratio >= 1.3:
        mins += 30
        why.append(f"+30 min : charge élevée (ratio {load_ratio:.2f}).".replace(".", ",", 1))
    d = debt(df)
    if d >= 180:
        mins += 30
        why.append(f"+30 min : dette de {d / 60:.1f} h sur 7 nuits.".replace(".", ","))
    mins = min(mins, 600)
    wake = float(np.nanmedian(df.tail(14)["wake_h"])) if len(df) and df.tail(14)["wake_h"].notna().any() else 7.5
    bed = (wake - mins / 60 - 0.25) % 24  # + ~15 min to fall asleep
    return {"minutes": mins, "reasons": why, "wake": wake, "bedtime": bed, "debt_min": d}


def by_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Average per night, grouped by 'weekday' (of the night), 'month' or 'year'."""
    if df.empty:
        return df
    g = df.copy()
    if period == "weekday":
        g["key"] = g["night"].dt.dayofweek
    elif period == "month":
        g["key"] = g["night"].dt.to_period("M").dt.to_timestamp()
    else:
        g["key"] = g["night"].dt.year
    out = g.groupby("key").agg(total=("total_min", "mean"), main=("main_min", "mean"), naps=("naps_min", "mean"),
                               score=("score", "mean"), deep=("deep_pct", "mean"), rem=("rem_pct", "mean"),
                               nights=("date", "count"), nap_days=("n_naps", lambda s: float((s > 0).mean())))
    return out.reset_index()


def regularity(df: pd.DataFrame) -> dict:
    """Spread of bed and wake-up times (standard deviation, minutes): under ~30 min is regular."""
    return {"bed_sd": float(df["bed_h"].std() * 60) if df["bed_h"].notna().sum() > 3 else None,
            "wake_sd": float(df["wake_h"].std() * 60) if df["wake_h"].notna().sum() > 3 else None,
            "bed_mean": float(df["bed_h"].mean()) if df["bed_h"].notna().any() else None,
            "wake_mean": float(df["wake_h"].mean()) if df["wake_h"].notna().any() else None}


def since(period: str, today: date, first: date | None) -> date:
    return {"30 jours": today - timedelta(days=30), "3 mois": today - timedelta(days=91), "6 mois": today - timedelta(days=182),
            "1 an": today - timedelta(days=365)}.get(period, first or today - timedelta(days=3650))
