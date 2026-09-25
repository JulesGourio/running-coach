"""Build a demo database (8 weeks of simulated training) to try the dashboard without COROS.

    COACH_DATA_DIR=data-demo uv run python scripts/demo_data.py
    COACH_DATA_DIR=data-demo uv run coach dashboard
"""
from __future__ import annotations

import json
import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coach.config import get_settings  # noqa: E402
from coach.db import DB  # noqa: E402
from coach.sync import analyze  # noqa: E402
from tests.synth import write_fit  # noqa: E402

random.seed(7)


def course(name, sections):
    return {"courseName": name, "sportType": 1, "courseDescription": name, "sections": sections}


def easy(m):
    return course("Footing facile", [{"sectionType": 2, "targetType": 1, "targetValue": m, "intensityType": 2,
                                       "intensityValueStart": 345, "intensityValueEnd": 370}])


def intervals(reps, dist, lo, hi):
    return course(f"VO2max {reps}x{dist}m", [
        {"sectionType": 1, "targetType": 2, "targetValue": 900, "intensityType": 2, "intensityValueStart": 345, "intensityValueEnd": 370},
        {"intervalGroup": True, "repeats": reps, "sets": [
            {"sectionType": 2, "targetType": 1, "targetValue": dist, "intensityType": 2, "intensityValueStart": lo, "intensityValueEnd": hi},
            {"sectionType": 3, "targetType": 1, "targetValue": 300, "intensityType": 2, "intensityValueStart": 400, "intensityValueEnd": 450}]},
        {"sectionType": 4, "targetType": 2, "targetValue": 600, "intensityType": 2, "intensityValueStart": 345, "intensityValueEnd": 370}])


def threshold(sec, lo, hi):
    return course(f"Seuil {sec // 60}min", [
        {"sectionType": 1, "targetType": 2, "targetValue": 900, "intensityType": 2, "intensityValueStart": 345, "intensityValueEnd": 370},
        {"sectionType": 2, "targetType": 2, "targetValue": sec, "intensityType": 2, "intensityValueStart": lo, "intensityValueEnd": hi},
        {"sectionType": 4, "targetType": 2, "targetValue": 600, "intensityType": 2, "intensityValueStart": 345, "intensityValueEnd": 370}])


def long_run(easy_m, fast_m):
    secs = [{"sectionType": 2, "targetType": 1, "targetValue": easy_m, "intensityType": 2, "intensityValueStart": 320, "intensityValueEnd": 345}]
    if fast_m:
        secs.append({"sectionType": 2, "targetType": 1, "targetValue": fast_m, "intensityType": 2, "intensityValueStart": 240, "intensityValueEnd": 250})
    return course("Sortie longue" + (f" + {fast_m // 1000}km allure objectif" if fast_m else ""), secs)


def segments_for(c, gain, flaw):
    """Turn a planned course into simulated segments; gain = pace improvement factor, flaw = injected mistake."""
    segs, reps_seen = [], 0
    for s in c["sections"]:
        if s.get("intervalGroup"):
            for r in range(s["repeats"]):
                work, rec = s["sets"]
                p = (work["intensityValueStart"] + work["intensityValueEnd"]) / 2 * gain
                if flaw == "fade" and r >= s["repeats"] - 2:
                    p += 14
                segs.append({"pace": p, "hr": 183, "m": work["targetValue"]})
                segs.append({"pace": 430, "hr": 150, "m": rec["targetValue"]})
                reps_seen += 1
            continue
        p = (s["intensityValueStart"] + s["intensityValueEnd"]) / 2
        fast = p < 300
        p = p * gain if fast else p
        hr = 176 if fast else 146
        if flaw == "too_hard" and not fast:
            p, hr = p - 30, 168
        seg = {"pace": p, "hr": hr}
        seg.update({"sec": s["targetValue"]} if s["targetType"] == 2 else {"m": s["targetValue"]})
        segs.append(seg)
    return segs


def main() -> None:
    s = get_settings()
    db = DB(s.db_path)
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    start = monday - timedelta(weeks=8)
    plan_start = monday - timedelta(weeks=3)
    week_courses = lambda w: {  # noqa: E731
        1: intervals(6, 400 if w < 2 else 1000, 232, 240),
        2: easy(8000),
        3: threshold(1200 + 300 * min(w, 2), 255, 263),
        5: easy(9000),
        6: long_run(13000 if w % 2 else 16000, 5000 if w % 2 else 0),
    }
    flaws = {(1, 2): "too_hard", (3, 6): "drift", (5, 1): "fade", (6, 5): "too_hard"}
    n = 0
    for w in range(10):
        wk = start + timedelta(weeks=w)
        for dow, c in week_courses(w).items():
            d = wk + timedelta(days=dow)
            day_no = (d - plan_start).days
            done = d < today
            if d >= plan_start:
                db.upsert_plan_day(d.isoformat(), day_no, False,
                                   [{"status": "Completed" if done else "Not started", "name": c["courseName"], "json": c}])
            if not done or d > today:
                continue
            if random.random() < 0.06:
                continue
            gain = 1 - 0.0015 * w
            flaw = flaws.get((w, dow))
            segs = segments_for(c, gain, flaw)
            label = f"demo{w}{dow}"
            st = datetime.combine(d, time(6, 30), tzinfo=timezone.utc)
            path = write_fit(s.fit_dir / f"{label}.fit", segs, start=st,
                             drift_bpm_per_h=10 if flaw == "drift" else 2)
            db.upsert_activity({"label_id": label, "sport_type": 100, "date": d.isoformat(), "name": c["courseName"],
                                "type": "Course", "source": "démo"})
            db.set_fit_path(label, str(path))
            n += 1
    for i in range(70):
        d = today - timedelta(days=69 - i)
        bad = i in (60, 61)
        db.upsert_daily(d.isoformat(), hrv=(60 if bad else 84 + random.gauss(0, 4)), hrv_lo=70, hrv_hi=98, hrv_base=84,
                        hrv_eval="Below normal" if bad else "Normal", rhr=(57 if bad else 51 + random.gauss(0, 1.5)),
                        sleep_score=max(40, min(98, random.gauss(82, 9))), sleep_total="7h 20min")
    for k in range(9):
        d = today - timedelta(weeks=8 - k)
        db.upsert_fitness(d.isoformat(), vo2max=59 + k // 4, threshold=268 - k, p10=2680 - 9 * k, p5=1290 - 4 * k,
                          half=5950 - 18 * k, marathon=12400 - 25 * k)
    db.set_meta("plan", json.dumps({"id": "demo", "name": "Plan démo", "start": plan_start.isoformat(),
                                    "end": (plan_start + timedelta(weeks=11, days=-1)).isoformat(), "weeks": 11}))
    db.set_meta("phases", json.dumps([{"name": "Base", "start": plan_start.isoformat(), "end": "", "weeks": 3}]))
    analyze(s, db, force=True)
    print(f"{n} séances simulées dans {s.data_dir}")


if __name__ == "__main__":
    main()
