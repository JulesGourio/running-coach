"""Training load model: fitness (CTL), fatigue (ATL), freshness (TSB), ACWR, monotony and polarization."""
from __future__ import annotations

import numpy as np
import pandas as pd


def daily_load(items: list[tuple[str, float]], start: str | None = None, end: str | None = None) -> pd.Series:
    """Sum of session loads per calendar day, with zero-load days filled in."""
    if not items:
        return pd.Series(dtype=float)
    s = pd.DataFrame(items, columns=["date", "load"]).groupby("date")["load"].sum()
    s.index = pd.to_datetime(s.index)
    idx = pd.date_range(start or s.index.min(), end or s.index.max(), freq="D")
    return s.reindex(idx, fill_value=0.0)


def fitness_model(load: pd.Series) -> pd.DataFrame:
    """Banister impulse-response with 42-day fitness and 7-day fatigue constants."""
    if load.empty:
        return pd.DataFrame(columns=["load", "ctl", "atl", "tsb", "acwr"])
    # Seed both averages at zero: history starts untrained rather than at the first session's load.
    seeded = pd.concat([pd.Series([0.0]), load.reset_index(drop=True)])
    ctl = pd.Series(seeded.ewm(alpha=1 - np.exp(-1 / 42), adjust=False).mean().iloc[1:].to_numpy(), index=load.index)
    atl = pd.Series(seeded.ewm(alpha=1 - np.exp(-1 / 7), adjust=False).mean().iloc[1:].to_numpy(), index=load.index)
    acute = load.rolling(7, min_periods=1).mean()
    chronic = load.rolling(28, min_periods=7).mean()
    return pd.DataFrame({"load": load, "ctl": ctl, "atl": atl, "tsb": ctl.shift(1) - atl.shift(1),
                         "acwr": acute / chronic.replace(0, np.nan)})


def monotony_strain(load: pd.Series) -> dict:
    last = load.tail(7)
    if len(last) < 7 or last.std() == 0:
        return {"monotony": None, "strain": None}
    mono = float(last.mean() / last.std())
    return {"monotony": mono, "strain": float(last.sum() * mono)}


def weekly_summary(rows: list[dict]) -> pd.DataFrame:
    """rows: {date, distance_m, moving_s, load, zones_hr}. Monday-based weeks."""
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["week"] = df["date"] - pd.to_timedelta(df["date"].dt.weekday, unit="D")

    def split(z: dict | None, part: str) -> float:
        z = z or {}
        if part == "low":
            return z.get("Z1 récup", 0) + z.get("Z2 endurance", 0)
        if part == "mid":
            return z.get("Z3 tempo", 0)
        return z.get("Z4 seuil", 0) + z.get("Z5 VO2max", 0)

    for part in ("low", "mid", "high"):
        df[f"t_{part}"] = [split(z, part) * t for z, t in zip(df["zones_hr"], df["moving_s"])]
    w = df.groupby("week").agg(km=("distance_m", lambda x: x.sum() / 1000), hours=("moving_s", lambda x: x.sum() / 3600),
                               load=("load", "sum"), sessions=("date", "count"),
                               t_low=("t_low", "sum"), t_mid=("t_mid", "sum"), t_high=("t_high", "sum"))
    tot = (w["t_low"] + w["t_mid"] + w["t_high"]).replace(0, np.nan)
    for part in ("low", "mid", "high"):
        w[f"pct_{part}"] = w[f"t_{part}"] / tot
    return w.drop(columns=["t_low", "t_mid", "t_high"])
