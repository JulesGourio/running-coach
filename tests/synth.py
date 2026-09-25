"""Synthetic runs for tests: segments of constant pace with a first-order heart-rate response."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from coach.fit import prepare_records

START = datetime(2026, 10, 6, 7, 0, 0, tzinfo=timezone.utc)


def build(segments: list[dict], hr0: float = 95, drift_bpm_per_h: float = 0.0, start: datetime = START):
    """segments: {"pace": s/km, "hr": target bpm, "sec": duration} or {"pace", "hr", "m": distance}."""
    rows, laps = [], []
    t, dist, hr = 0, 0.0, hr0
    for seg in segments:
        speed = 1000 / seg["pace"]
        n = int(seg["sec"]) if "sec" in seg else int(math.ceil(seg["m"] / speed))
        lap_t0, lap_d0, hrs = t, dist, []
        for _ in range(n):
            target = seg["hr"] + drift_bpm_per_h * t / 3600
            hr += (target - hr) / 25
            dist += speed
            t += 1
            hrs.append(hr)
            rows.append({"timestamp": start + timedelta(seconds=t), "distance": dist, "speed": speed, "hr": round(hr),
                         "cadence": 172.0, "altitude": 150.0, "power": None, "lat": None, "lon": None})
        laps.append({"start_time": start + timedelta(seconds=lap_t0), "timer_s": float(t - lap_t0),
                     "elapsed_s": float(t - lap_t0), "distance_m": dist - lap_d0, "avg_hr": float(np.mean(hrs)),
                     "avg_speed": speed})
    df = prepare_records(pd.DataFrame(rows))
    return df, laps


def write_fit(path: Path, segments: list[dict], **kw) -> Path:
    from fit_tool.fit_file_builder import FitFileBuilder
    from fit_tool.profile.messages.file_id_message import FileIdMessage
    from fit_tool.profile.messages.lap_message import LapMessage
    from fit_tool.profile.messages.record_message import RecordMessage
    from fit_tool.profile.messages.session_message import SessionMessage
    from fit_tool.profile.profile_type import FileType, Manufacturer, Sport

    df, laps = build(segments, **kw)
    ms = lambda d: round(d.timestamp() * 1000)  # noqa: E731
    b = FitFileBuilder(auto_define=True, min_string_size=50)
    fid = FileIdMessage()
    fid.type = FileType.ACTIVITY
    fid.manufacturer = Manufacturer.DEVELOPMENT.value
    fid.product = 0
    fid.time_created = ms(df["timestamp"].iloc[0])
    fid.serial_number = 1
    b.add(fid)
    recs = []
    for r in df.itertuples():
        m = RecordMessage()
        m.timestamp = ms(r.timestamp)
        m.distance = float(r.distance)
        m.enhanced_speed = float(r.speed)
        m.heart_rate = int(r.hr)
        m.cadence = int(r.cadence / 2)
        m.enhanced_altitude = float(r.altitude)
        recs.append(m)
    b.add_all(recs)
    for lap in laps:
        m = LapMessage()
        m.start_time = ms(lap["start_time"])
        m.timestamp = ms(lap["start_time"] + timedelta(seconds=lap["timer_s"]))
        m.total_elapsed_time = lap["elapsed_s"]
        m.total_timer_time = lap["timer_s"]
        m.total_distance = lap["distance_m"]
        m.avg_heart_rate = int(lap["avg_hr"])
        m.enhanced_avg_speed = lap["avg_speed"]
        b.add(m)
    s = SessionMessage()
    s.start_time = ms(df["timestamp"].iloc[0])
    s.timestamp = ms(df["timestamp"].iloc[-1])
    s.sport = Sport.RUNNING
    s.total_elapsed_time = float(df["elapsed"].iloc[-1])
    s.total_timer_time = float(df["elapsed"].iloc[-1])
    s.total_distance = float(df["distance"].iloc[-1])
    s.avg_heart_rate = int(df["hr"].mean())
    b.add(s)
    b.build().to_file(str(path))
    return path


VO2_COURSE = {
    "courseName": "VO2max 6x400m", "sportType": 1,
    "sections": [
        {"sectionType": 1, "targetType": 2, "targetValue": 900, "intensityType": 2, "intensityValueStart": 345, "intensityValueEnd": 370},
        {"intervalGroup": True, "repeats": 6, "sets": [
            {"sectionType": 2, "targetType": 1, "targetValue": 400, "intensityType": 2, "intensityValueStart": 230, "intensityValueEnd": 240},
            {"sectionType": 3, "targetType": 1, "targetValue": 200, "intensityType": 2, "intensityValueStart": 400, "intensityValueEnd": 450}]},
        {"sectionType": 4, "targetType": 2, "targetValue": 600, "intensityType": 2, "intensityValueStart": 345, "intensityValueEnd": 370},
    ],
}

EASY_COURSE = {"courseName": "Footing facile", "sportType": 1,
               "sections": [{"sectionType": 2, "targetType": 1, "targetValue": 8000, "intensityType": 2,
                             "intensityValueStart": 345, "intensityValueEnd": 370}]}


def vo2_segments(rep_paces: list[float] | None = None) -> list[dict]:
    rep_paces = rep_paces or [235] * 6
    segs = [{"pace": 357, "hr": 140, "sec": 900}]
    for p in rep_paces:
        segs += [{"pace": p, "hr": 182, "m": 400}, {"pace": 425, "hr": 150, "m": 200}]
    segs.append({"pace": 360, "hr": 138, "sec": 600})
    return segs
