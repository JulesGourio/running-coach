"""Parsers for the plain-text answers of the official COROS MCP server."""
from __future__ import annotations

import json
import re


def clock(s: str | None) -> float | None:
    if not s:
        return None
    parts = [float(p) for p in s.strip().split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]


def _g(pattern: str, text: str, flags: int = 0) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def parse_fitness(t: str) -> dict | None:
    if not _g(r"VO2max:\s*([\d.]+)", t) and not _g(r"10 km Prediction:\s*([\d:]+)", t):
        return None
    num = lambda p: float(v) if (v := _g(p, t)) else None  # noqa: E731
    return {
        "vo2max": num(r"VO2max:\s*([\d.]+)"),
        "level": num(r"Running Level:\s*([\d.]+)"),
        "threshold": clock(_g(r"Threshold Pace:\s*([\d:]+)", t)),
        "p5": clock(_g(r"(?<!\d)5 km Prediction:\s*([\d:]+)", t)),
        "p10": clock(_g(r"10 km Prediction:\s*([\d:]+)", t)),
        "half": clock(_g(r"Half Marathon Prediction:\s*([\d:]+)", t)),
        "marathon": clock(_g(r"^Marathon Prediction:\s*([\d:]+)", t, re.M)),
    }


def parse_recovery(t: str) -> dict | None:
    pct = _g(r"Recovery:\s*(\d+)\s*%", t)
    if pct is None:
        return None
    return {"pct": float(pct), "level": _g(r"Level:\s*(.+)", t) or "",
            "full": _g(r"Estimated Full Recovery:\s*(.+)", t) or ""}


def parse_load(t: str) -> list[dict]:
    rx = re.compile(r"(\d{4}-\d{2}-\d{2})\s*\nComment:\s*(.*)\nShort-Term Load:\s*([\d.]+)\n"
                    r"Long-Term Load:\s*([\d.]+)\nLoad Ratio:\s*([\d.]+)")
    out = [{"date": m[0], "comment": m[1].strip(), "st": float(m[2]), "lt": float(m[3]), "ratio": float(m[4])}
           for m in rx.findall(t)]
    return sorted(out, key=lambda x: x["date"])


RUN_TYPES = {"Outdoor Run": "Course", "Trail Run": "Trail", "Indoor Run": "Tapis", "Track Run": "Piste"}


def parse_sport_records(t: str) -> list[dict]:
    out = []
    for b in re.split(r"\n(?=\d+\.\s)", t):
        h = re.search(r"^\d+\.\s+(.+?)\s+[—–-]\s+(\d{4}-\d{2}-\d{2})", b, re.M)
        if not h:
            continue
        label = _g(r"LabelId:\s*(\d+)", b)
        if not label:
            continue
        dist = _g(r"Distance:\s*([\d.]+)\s*km", b)
        hr = _g(r"Avg HR:\s*(\d+)", b)
        sport = _g(r"SportType:\s*(\d+)", b)
        start = _g(r"startTimestamp=(\d+)", b)
        out.append({
            "label_id": label,
            "sport_type": int(sport) if sport else None,
            "date": h.group(2),
            "start_ts": int(start) if start else None,
            "type": RUN_TYPES.get(h.group(1).strip(), h.group(1).strip()),
            "name": _g(r"Location:\s*(.+)", b),
            "distance_km": float(dist) if dist else None,
            "duration_s": clock(_g(r"Duration:\s*([\d:]+)", b)),
            "avg_pace": clock(_g(r"Average Pace:\s*([\d:]+)", b)),
            "avg_hr": float(hr) if hr else None,
        })
    return sorted(out, key=lambda x: (x["date"], x["start_ts"] or 0), reverse=True)


def parse_hrv(t: str) -> list[dict]:
    head = t.split("Sleep HRV Time Series")[0]
    rx = re.compile(r"(\d{4}-\d{2}-\d{2}):\s*\n\s*HRV Avg:\s*(\d+)\s*ms\s*[—–-]\s*(.+)\n\s*Normal Range:\s*(\d+)\s*-\s*"
                    r"(\d+)\s*ms\n\s*Baseline:\s*(\d+)")
    out = [{"date": m[0], "hrv": float(m[1]), "hrv_eval": m[2].strip(), "hrv_lo": float(m[3]), "hrv_hi": float(m[4]),
            "hrv_base": float(m[5])} for m in rx.findall(head)]
    return sorted(out, key=lambda x: x["date"])


def parse_sleep(t: str) -> list[dict]:
    out = []
    for b in re.split(r"\n(?=\d{4}-\d{2}-\d{2}\nSleep Score)", t):
        m = re.search(r"^(\d{4}-\d{2}-\d{2})\nSleep Score:\s*(\d+)", b, re.M)
        if not m or int(m.group(2)) == 0:
            continue
        deep, rem = _g(r"Deep Sleep Ratio:\s*(\d+)", b), _g(r"REM Ratio:\s*(\d+)", b)
        out.append({"date": m.group(1), "sleep_score": float(m.group(2)),
                    "sleep_total": _g(r"Daily Sleep:\s*([^(\n]+)", b),
                    "sleep_deep": float(deep) if deep else None, "sleep_rem": float(rem) if rem else None})
    return sorted(out, key=lambda x: x["date"])


def parse_rhr(t: str) -> list[dict]:
    return sorted(({"date": d, "rhr": float(v)} for d, v in re.findall(r"(\d{4}-\d{2}-\d{2}):\s*(\d+)\s*bpm", t)),
                  key=lambda x: x["date"])


def parse_plan_library(t: str) -> dict | None:
    for b in re.split(r"\n(?=\d+\.\s)", t):
        if not (re.search(r"Record role:\s*execution", b, re.I) and re.search(r"Editable via MCP:\s*yes", b, re.I)
                and re.search(r"\[In progress\]", b, re.I)):
            continue
        pid = _g(r"Plan ID:\s*(\d+)", b)
        dates = re.search(r"Dates:\s*(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})", b)
        if not pid or not dates:
            continue
        weeks = _g(r"Weeks:\s*(\d+)", b)
        return {"id": pid, "name": _g(r"^\d+\.\s+(.+?)\s+\[", b, re.M) or "", "start": dates.group(1),
                "end": dates.group(2), "weeks": int(weeks) if weeks else None}
    return None


PHASES_FR = {"Preparation": "Préparation", "Base": "Base", "Build": "Développement", "Peak": "Spécifique",
             "Race": "Course", "Transition": "Transition"}


def parse_plan_details(t: str) -> dict:
    phases = [{"name": PHASES_FR.get(m[0], m[0]), "start": m[1], "end": m[2], "weeks": int(m[3])}
              for m in re.findall(r"Phase \d+:\s*(\w+)\s*\((\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})\),\s*(\d+)\s*week", t)]
    days = []
    rx = re.compile(r"Day (\d+) - (\d{4}-\d{2}-\d{2})\n([\s\S]*?)(?=\nDay \d+ - \d{4}-\d{2}-\d{2}|\n\s*\nUpdate hint|\Z)")
    for m in rx.finditer(t):
        body, courses = m.group(3), []
        for c in re.finditer(r"Course \d+ \[([^\]]*)\]\s*\nCourse:\s*(.*)\nCourse JSON:\s*(\{.*\})", body):
            try:
                js = json.loads(c.group(3))
            except json.JSONDecodeError:
                js = None
            courses.append({"status": c.group(1), "name": c.group(2).strip(), "json": js})
        days.append({"day_no": int(m.group(1)), "date": m.group(2),
                     "rest": bool(re.search(r"Rest day", body, re.I)) and not courses, "courses": courses})
    return {"phases": phases, "days": days}


def minutes(txt: str | None) -> float | None:
    """'8h 48min' / '41 min' / '7h' -> minutes."""
    if not txt:
        return None
    h = re.search(r"(\d+)\s*h", txt)
    m = re.search(r"(\d+)\s*min", txt)
    if not h and not m:
        return None
    return (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0)


def parse_sleep_full(t: str) -> list[dict]:
    """Every field of querySleepOverview, one row per wake-up date (naps included, with their windows)."""
    out = []
    for b in re.split(r"\n(?=\d{4}-\d{2}-\d{2}\n)", t):
        d = re.match(r"(\d{4}-\d{2}-\d{2})\nSleep Score:\s*(\d+)", b)
        if not d or int(d.group(2)) == 0:
            continue
        pct = lambda k: float(v) if (v := _g(rf"{k}:\s*(\d+)\s*%", b)) else None  # noqa: E731
        win = re.search(r"Main Sleep Window:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*-\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", b)
        naps = re.findall(r"Nap Window:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*-\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", b)
        out.append({
            "date": d.group(1), "score": float(d.group(2)),
            "total_min": minutes(_g(r"Daily Sleep:\s*([^(\n]+)", b)),
            "main_min": minutes(_g(r"Main Sleep \(asleep\):\s*(.+)", b)),
            "main_period_min": minutes(_g(r"Main Sleep Period \(incl\. awake\):\s*(.+)", b)),
            "deep_pct": pct("Deep Sleep Ratio"), "light_pct": pct("Light Sleep Ratio"),
            "rem_pct": pct("REM Ratio"), "awake_pct": pct("Awake Ratio"),
            "awake_min": minutes(_g(r"Awake Time:\s*(.+)", b)),
            "awake_count": float(v) if (v := _g(r"Awake Count[^:]*:\s*(\d+)", b)) else None,
            "bedtime": win.group(1) if win else None, "waketime": win.group(2) if win else None,
            "naps_min": minutes(_g(r"Naps Total \(asleep\):\s*(.+)", b)) or 0,
            "naps": [{"start": a, "end": e} for a, e in naps],
        })
    return sorted(out, key=lambda x: x["date"])


def parse_fit_urls(t: str) -> list[str]:
    return re.findall(r"https?://[^\s\"'<>)]+", t)


def is_done(status: str | None) -> bool:
    return not re.search(r"not started", status or "", re.I)
