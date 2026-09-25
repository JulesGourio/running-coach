"""Race-day plan: pace for every km at an even effort over the course profile, corrected for heat and wind,
with split times. Course from a GPX file, a past activity or flat; weather from Open-Meteo (forecast within
16 days, otherwise the weather observed on the same date in previous years)."""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from datetime import date, datetime

import httpx
import numpy as np
import pandas as pd

from coach.metrics.session import minetti_factor

FORECAST = "https://api.open-meteo.com/v1/forecast"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
HOURLY = "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m"


# ---- course ----------------------------------------------------------------------------------------------

def _haversine(la1, lo1, la2, lo2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def course_from_gpx(data: bytes) -> pd.DataFrame:
    """Points (lat, lon, alt, dist in m) from a GPX track or route."""
    root = ET.fromstring(data)
    pts = [e for e in root.iter() if e.tag.endswith("trkpt") or e.tag.endswith("rtept")]
    rows, d = [], 0.0
    for i, e in enumerate(pts):
        la, lo = float(e.get("lat")), float(e.get("lon"))
        ele = next((float(x.text) for x in e if x.tag.endswith("ele") and x.text), np.nan)
        if i:
            d += _haversine(rows[-1]["lat"], rows[-1]["lon"], la, lo)
        rows.append({"lat": la, "lon": lo, "alt": ele, "dist": d})
    return pd.DataFrame(rows)


def course_from_records(rec: pd.DataFrame) -> pd.DataFrame:
    g = rec.dropna(subset=["distance"])
    return pd.DataFrame({"lat": g["lat"], "lon": g["lon"], "alt": g["altitude"], "dist": g["distance"] - g["distance"].iloc[0]})


def flat_course(distance_m: float) -> pd.DataFrame:
    return pd.DataFrame({"lat": np.nan, "lon": np.nan, "alt": 0.0, "dist": np.linspace(0, distance_m, 200)})


def km_profile(course: pd.DataFrame, distance_m: float) -> pd.DataFrame:
    """One row per km (last one partial): length, mean grade, net climb and bearing (degrees, for the wind)."""
    c = course.copy()
    if c["dist"].iloc[-1] > 0:
        c["dist"] = c["dist"] * distance_m / c["dist"].iloc[-1]  # the course may be a few % off the official distance
    c["alt"] = c["alt"].interpolate(limit_direction="both").fillna(0).rolling(9, min_periods=1, center=True).mean()
    edges = list(np.arange(0, distance_m, 1000)) + [distance_m]
    out = []
    for a, b in zip(edges, edges[1:]):
        seg = c[(c["dist"] >= a) & (c["dist"] <= b)]
        if len(seg) < 2:
            seg = c.iloc[[int(np.searchsorted(c["dist"], a)) - 1, min(len(c) - 1, int(np.searchsorted(c["dist"], b)))]]
        alt_a = np.interp(a, c["dist"], c["alt"])
        alt_b = np.interp(b, c["dist"], c["alt"])
        # grade from the km's own ups and downs, not just start/end (a hill in the middle still costs)
        x = np.r_[a, seg["dist"].to_numpy(), b]
        y = np.r_[alt_a, seg["alt"].to_numpy(), alt_b]
        grades = np.diff(y) / np.maximum(np.diff(x), 1)
        cost = float(np.average(minetti_factor(np.clip(grades, -0.3, 0.3)), weights=np.maximum(np.diff(x), 1e-6)))
        bearing = None
        if seg["lat"].notna().sum() >= 2:
            la1, lo1, la2, lo2 = seg["lat"].dropna().iloc[0], seg["lon"].dropna().iloc[0], seg["lat"].dropna().iloc[-1], seg["lon"].dropna().iloc[-1]
            y_ = math.sin(math.radians(lo2 - lo1)) * math.cos(math.radians(la2))
            x_ = math.cos(math.radians(la1)) * math.sin(math.radians(la2)) - math.sin(math.radians(la1)) * math.cos(math.radians(la2)) * math.cos(math.radians(lo2 - lo1))
            bearing = (math.degrees(math.atan2(y_, x_)) + 360) % 360
        out.append({"km": len(out) + 1, "length": b - a, "grade": (alt_b - alt_a) / (b - a), "climb": alt_b - alt_a,
                    "cost": cost, "bearing": bearing, "alt_end": alt_b})
    return pd.DataFrame(out)


# ---- weather ---------------------------------------------------------------------------------------------

def weather(lat: float, lon: float, day: date, hour: int, today: date | None = None, years: int = 3) -> dict:
    """Temperature, humidity, wind at race time: forecast if within 16 days, else the mean of the same date and
    hour over the previous `years` years (with their spread)."""
    today = today or date.today()
    params = {"latitude": lat, "longitude": lon, "hourly": HOURLY, "timezone": "auto", "wind_speed_unit": "ms"}
    if 0 <= (day - today).days <= 15:
        r = httpx.get(FORECAST, params={**params, "start_date": day.isoformat(), "end_date": day.isoformat()}, timeout=20)
        r.raise_for_status()
        h = r.json()["hourly"]
        return {"source": "prévision", "temp": h["temperature_2m"][hour], "humidity": h["relative_humidity_2m"][hour],
                "wind": h["wind_speed_10m"][hour], "wind_dir": h["wind_direction_10m"][hour]}
    rows = []
    for k in range(1, years + 1):
        d = date(day.year - k, day.month, min(day.day, 28 if day.month == 2 else day.day))
        if d >= today:
            continue
        r = httpx.get(ARCHIVE, params={**params, "start_date": d.isoformat(), "end_date": d.isoformat()}, timeout=20)
        r.raise_for_status()
        h = r.json()["hourly"]
        rows.append((h["temperature_2m"][hour], h["relative_humidity_2m"][hour], h["wind_speed_10m"][hour], h["wind_direction_10m"][hour]))
    if not rows:
        raise ValueError("Pas de données météo historiques.")
    a = np.array(rows, dtype=float)
    # mean wind direction as a vector average
    wd = math.degrees(math.atan2(np.mean(np.sin(np.radians(a[:, 3]))), np.mean(np.cos(np.radians(a[:, 3]))))) % 360
    return {"source": f"moyenne des {len(rows)} dernières années à cette date", "temp": float(a[:, 0].mean()),
            "humidity": float(a[:, 1].mean()), "wind": float(a[:, 2].mean()), "wind_dir": wd,
            "temp_range": (float(a[:, 0].min()), float(a[:, 0].max()))}


# ---- pacing ----------------------------------------------------------------------------------------------

def heat_penalty(temp: float, humidity: float = 60) -> float:
    """Fraction of time lost to heat: none up to ~12 °C, then ~0.3 %/°C, more when humid (dew point proxy)."""
    extra = max(0.0, temp - 12)
    return extra * (0.003 + 0.00003 * max(0, humidity - 50))


def wind_factor(wind_ms: float, wind_from_deg: float | None, bearing: float | None) -> float:
    """Time factor for one km: a headwind costs ~2 % per m/s, a tailwind gives back about half of that."""
    if wind_from_deg is None or bearing is None or not wind_ms:
        return 1.0
    head = wind_ms * math.cos(math.radians(wind_from_deg - bearing))  # > 0: wind in the face
    return 1 + (0.02 * head if head > 0 else 0.01 * head)


def plan(profile: pd.DataFrame, target_s: float, wx: dict | None = None, start_conservative: bool = True,
         weather_adjusted: bool = True) -> dict:
    """Per-km pace at even effort. With `weather_adjusted`, the target is the time on a cool calm day and the
    plan adds what heat and wind cost (the realistic time); otherwise it keeps the target and the effort goes up."""
    p = profile.copy()
    wf = [wind_factor((wx or {}).get("wind", 0), (wx or {}).get("wind_dir"), b) for b in p["bearing"]] if wx else [1.0] * len(p)
    p["factor"] = p["cost"] * np.array(wf)
    if start_conservative and len(p) >= 5:
        p.loc[p.index[0], "factor"] *= 1.012  # first km ~3 s/km slower: the race is won in the second half
    heat = heat_penalty(wx["temp"], wx.get("humidity", 60)) if wx else 0.0
    # net wind cost: a headwind costs more than a tailwind gives back, so it adds time overall
    wind_mult = float(np.average(wf, weights=p["length"]))
    total = target_s * (1 + heat) * wind_mult if weather_adjusted else target_s
    base = total / float((p["factor"] * p["length"] / 1000).sum())  # s/km on flat, calm ground
    p["pace"] = base * p["factor"]
    p["time"] = p["pace"] * p["length"] / 1000
    p["split"] = p["time"].cumsum()
    return {"rows": p, "total": float(p["time"].sum()), "base_pace": base, "heat": heat,
            "wind_effect": wind_mult - 1}


def watch_course(result: dict, goal_label: str, tolerance: int = 4) -> dict:
    """COROS workout for race day: one section per km at the planned pace (± tolerance s/km)."""
    from coach.plan_edit import section
    secs = [section("work", "distance", r["length"], (round(r["pace"]) - tolerance, round(r["pace"]) + tolerance))
            for _, r in result["rows"].iterrows()]
    t = result["total"]
    return {"sportType": 1, "courseName": f"COURSE - {goal_label} (plan km par km)",
            "courseDescription": f"Allure prévue km par km selon le profil et la météo, objectif {int(t // 60)}:{int(t % 60):02d}. "
                                 "Premier km prudent, garde des forces pour la seconde moitié.", "sections": secs}
