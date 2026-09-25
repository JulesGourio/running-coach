"""Human-readable French descriptions of COROS workouts."""
from __future__ import annotations

from coach.verdict import fpace


def fdist(m: float) -> str:
    if m >= 1000:
        km = m / 1000
        return (f"{km:.1f}".rstrip("0").rstrip(".") if km % 1 else f"{km:.0f}").replace(".", ",") + " km"
    return f"{m:.0f} m"


def fmin(s: float) -> str:
    return f"{s / 60:.0f} min" if s % 60 == 0 else f"{int(s // 60)}:{int(s % 60):02d}"


def pace_range(s: dict) -> str:
    if s.get("intensityType") == 2 and s.get("intensityValueStart"):
        a, b = sorted([s["intensityValueStart"], s.get("intensityValueEnd", s["intensityValueStart"])])
        return fpace(a) if a == b else f"{fpace(a)}–{fpace(b)}"
    if s.get("intensityType") == 1 and s.get("intensityValueStart"):
        return f"{s['intensityValueStart']}–{s['intensityValueEnd']} bpm"
    return ""


def section_text(s: dict) -> str:
    if s.get("intervalGroup"):
        return f"{s.get('repeats', 1)} × (" + " / ".join(section_text(m) for m in s.get("sets") or []) + ")"
    tt, tv = s.get("targetType"), s.get("targetValue") or 0
    tgt = fdist(tv) if tt == 1 else fmin(tv) if tt == 2 else "libre"
    kind = s.get("sectionType")
    if kind == 1:
        return f"échauff. {tgt}"
    if kind == 4:
        return f"retour au calme {tgt}"
    if kind == 3:
        return f"récup {tgt}"
    p = pace_range(s)
    return f"{tgt} @ {p}" if p else tgt


def course_text(course: dict | None) -> str:
    if not course:
        return ""
    return " · ".join(section_text(s) for s in course.get("sections") or [])
