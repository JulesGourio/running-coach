"""FIT file decoding into a per-second DataFrame plus laps and session summary."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import fitdecode
import numpy as np
import pandas as pd

SEMI = 180 / 2**31


@dataclass
class FitActivity:
    records: pd.DataFrame
    laps: list[dict] = field(default_factory=list)
    session: dict = field(default_factory=dict)

    @property
    def start(self) -> datetime | None:
        st = self.session.get("start_time")
        if st is not None:
            return st
        return self.records["timestamp"].iloc[0].to_pydatetime() if len(self.records) else None


def _v(frame, *names):
    for n in names:
        if frame.has_field(n):
            v = frame.get_value(n, fallback=None)
            if v is not None:
                return v
    return None


def _utc(ts):
    if isinstance(ts, datetime) and ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def read_fit(path: Path | str) -> FitActivity:
    rows, laps, session = [], [], {}
    with fitdecode.FitReader(str(path), check_crc=fitdecode.CrcCheck.WARN) as fit:
        for fr in fit:
            if fr.frame_type != fitdecode.FIT_FRAME_DATA:
                continue
            if fr.name == "record":
                cad = _v(fr, "cadence")
                frac = _v(fr, "fractional_cadence") or 0
                lat, lon = _v(fr, "position_lat"), _v(fr, "position_long")
                rows.append({
                    "timestamp": _utc(_v(fr, "timestamp")),
                    "distance": _v(fr, "distance"),
                    "speed": _v(fr, "enhanced_speed", "speed"),
                    "hr": _v(fr, "heart_rate"),
                    "cadence": (cad + frac) * 2 if cad is not None else None,
                    "altitude": _v(fr, "enhanced_altitude", "altitude"),
                    "power": _v(fr, "power"),
                    "lat": lat * SEMI if isinstance(lat, (int, float)) else None,
                    "lon": lon * SEMI if isinstance(lon, (int, float)) else None,
                })
            elif fr.name == "lap":
                laps.append({
                    "start_time": _utc(_v(fr, "start_time")),
                    "end_time": _utc(_v(fr, "timestamp")),
                    "elapsed_s": _v(fr, "total_elapsed_time"),
                    "timer_s": _v(fr, "total_timer_time"),
                    "distance_m": _v(fr, "total_distance"),
                    "avg_hr": _v(fr, "avg_heart_rate"),
                    "max_hr": _v(fr, "max_heart_rate"),
                    "avg_speed": _v(fr, "enhanced_avg_speed", "avg_speed"),
                    "intensity": _v(fr, "intensity"),
                    "trigger": _v(fr, "lap_trigger"),
                    "step_index": _v(fr, "wkt_step_index"),
                })
            elif fr.name == "session":
                session = {
                    "sport": _v(fr, "sport"),
                    "sub_sport": _v(fr, "sub_sport"),
                    "start_time": _utc(_v(fr, "start_time")),
                    "elapsed_s": _v(fr, "total_elapsed_time"),
                    "timer_s": _v(fr, "total_timer_time"),
                    "distance_m": _v(fr, "total_distance"),
                    "avg_hr": _v(fr, "avg_heart_rate"),
                    "max_hr": _v(fr, "max_heart_rate"),
                    "ascent_m": _v(fr, "total_ascent"),
                    "descent_m": _v(fr, "total_descent"),
                }
    return FitActivity(records=prepare_records(pd.DataFrame(rows)), laps=laps, session=session)


def prepare_records(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a record stream: 1 Hz time base, filled distance/speed, elapsed seconds."""
    cols = ["timestamp", "distance", "speed", "hr", "cadence", "altitude", "power", "lat", "lon"]
    for c in cols:
        if c not in df:
            df[c] = np.nan
    if df.empty:
        return df.assign(elapsed=pd.Series(dtype=float))
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").drop_duplicates("timestamp")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp")
    num = df[["distance", "speed", "hr", "cadence", "altitude", "power", "lat", "lon"]].apply(pd.to_numeric, errors="coerce")
    num = num.resample("1s").mean()
    num[["distance", "altitude", "lat", "lon"]] = num[["distance", "altitude", "lat", "lon"]].interpolate(limit_area="inside")
    num[["hr", "cadence", "power"]] = num[["hr", "cadence", "power"]].interpolate(limit=5, limit_area="inside")
    if num["speed"].isna().all() and num["distance"].notna().any():
        num["speed"] = num["distance"].diff().clip(lower=0)
    num["speed"] = num["speed"].interpolate(limit=5, limit_area="inside").fillna(0)
    if num["distance"].isna().all():
        num["distance"] = num["speed"].cumsum()
    num["distance"] = num["distance"].ffill().fillna(0)
    num = num.reset_index()
    num["elapsed"] = (num["timestamp"] - num["timestamp"].iloc[0]).dt.total_seconds()
    return num
