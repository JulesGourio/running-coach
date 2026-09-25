"""Statistics over the whole running history (activity summaries, FIT or not): totals, volume by period,
year by year, records, and the best run at each classic distance."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from coach.db import DB

DISTANCES = [("5 km", 4.9, 5.4), ("10 km", 9.8, 10.7), ("Semi-marathon", 20.9, 21.8), ("Marathon", 41.8, 43.0)]


def frame(db: DB) -> pd.DataFrame:
    an = db.analyses()
    rows = []
    for a in db.activities():
        v = (an.get(a["label_id"]) or {}).get("verdict") or {}
        rows.append({**a, "category": v.get("type_fr") or ("Trail" if a.get("type") == "Trail" else "Non analysée"),
                     "structure": v.get("structure"), "headline": v.get("headline")})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["hours"] = df["duration_s"].fillna(0) / 3600
    df["distance_km"] = df["distance_km"].fillna(0)
    return df.sort_values("date")


def window(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    return df[(df["date"].dt.date >= start) & (df["date"].dt.date <= end)]


def totals(df: pd.DataFrame, start: date, end: date) -> dict:
    w = window(df, start, end)
    weeks = max(1.0, ((end - start).days + 1) / 7)
    km, secs = w["distance_km"].sum(), w["duration_s"].fillna(0).sum()
    return {"km": float(km), "sessions": int(len(w)), "hours": float(secs / 3600), "km_week": float(km / weeks),
            "sessions_week": float(len(w) / weeks), "pace": float(secs / km) if km else None,
            "longest": w.loc[w["distance_km"].idxmax()].to_dict() if len(w) else None}


def previous(start: date, end: date) -> tuple[date, date]:
    span = end - start
    return start - span - timedelta(days=1), start - timedelta(days=1)


def volume(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """km per week ('W') or month ('M'), split by session type."""
    g = df.copy()
    g["period"] = g["date"].dt.to_period(freq).dt.start_time
    return g.pivot_table(index="period", columns="category", values="distance_km", aggfunc="sum", fill_value=0).sort_index()


def per_year(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(df["date"].dt.year)
    out = g.agg(km=("distance_km", "sum"), sessions=("label_id", "count"), hours=("hours", "sum"),
                longest=("distance_km", "max"), secs=("duration_s", "sum")).reset_index().rename(columns={"date": "year"})
    out["pace"] = out["secs"] / out["km"]
    return out


def best_by_distance(df: pd.DataFrame) -> list[dict]:
    """Fastest average pace among runs of each classic distance (whole-run average: races or runs of that length)."""
    out = []
    for name, lo, hi in DISTANCES:
        w = df[(df["distance_km"] >= lo) & (df["distance_km"] <= hi) & df["avg_pace"].notna()]
        if len(w):
            b = w.loc[w["avg_pace"].idxmin()]
            out.append({"distance": name, "date": b["date"].date(), "km": b["distance_km"], "time": b["duration_s"],
                        "pace": b["avg_pace"], "name": b.get("name")})
    return out


def records(df: pd.DataFrame) -> dict:
    wk = df.groupby(df["date"].dt.to_period("W").dt.start_time)["distance_km"].sum()
    mo = df.groupby(df["date"].dt.to_period("M").dt.start_time)["distance_km"].sum()
    longest = df.loc[df["distance_km"].idxmax()]
    return {"longest": longest.to_dict(), "best_week": (wk.idxmax().date(), float(wk.max())),
            "best_month": (mo.idxmax().date(), float(mo.max())), "first": df["date"].min().date(),
            "total_km": float(df["distance_km"].sum()), "total_sessions": int(len(df))}
