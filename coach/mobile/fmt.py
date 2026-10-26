"""French formatting for the phone screens (same conventions as the Streamlit dashboard)."""
from __future__ import annotations

from datetime import date

DOW = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
MON = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]

# Session type → colour, matched on the start of the French label (as in app/common.py).
TYPE_COLORS = [("VMA courte", "#ef4444"), ("VMA longue", "#9f1239"), ("VMA", "#dc2626"), ("Côtes", "#7f1d1d"),
               ("Seuil", "#ea8a0c"), ("Tempo", "#a16207"), ("Allure", "#7c3aed"), ("Fartlek", "#db2777"),
               ("Sortie longue", "#0d9488"), ("Course", "#111827"), ("Footing", "#2e6fdb"), ("Récupération", "#94a3b8")]
ZONE_COLORS = {"Z1 récup": "#94a3b8", "Z2 endurance": "#2e6fdb", "Z3 tempo": "#16a34a",
               "Z4 seuil": "#ea8a0c", "Z5 VO2max": "#dc2626"}
BLUE, ORANGE, GREEN, RED, GREY = "#2e6fdb", "#d9480f", "#1a7f37", "#cf222e", "#6b7280"
LEVEL_TONE = {"vert": "good", "orange": "warn", "rouge": "bad", "inconnu": "muted"}


def _nan(v) -> bool:
    return v is None or v != v


def pace(sec) -> str:
    if _nan(sec):
        return "—"
    sec = round(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def pace_km(sec) -> str:
    return "—" if _nan(sec) else f"{pace(sec)}/km"


def dur(sec) -> str:
    if _nan(sec):
        return "—"
    sec = round(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def hm(minutes) -> str:
    if _nan(minutes):
        return "—"
    return f"{int(minutes // 60)} h {int(round(minutes % 60)):02d}"


def day(d) -> str:
    if not d:
        return "—"
    d = date.fromisoformat(str(d)[:10]) if not isinstance(d, date) else d
    year = f" {d.year}" if d.year != date.today().year else ""
    return f"{DOW[d.weekday()]} {d.day} {MON[d.month - 1]}{year}"


def short(d) -> str:
    d = date.fromisoformat(str(d)[:10]) if not isinstance(d, date) else d
    return f"{d.day:02d}/{d.month:02d}"


def num(v, dec: int = 1) -> str:
    return "—" if _nan(v) else f"{v:.{dec}f}".replace(".", ",")


def kmh(v_ms) -> str:
    return "—" if _nan(v_ms) or not v_ms else f"{num(v_ms * 3.6, 1)} km/h"


def pct(frac, dec: int = 0) -> str:
    return "—" if _nan(frac) else f"{frac * 100:.{dec}f} %".replace(".", ",")


def type_color(label: str | None) -> str:
    for prefix, color in TYPE_COLORS:
        if (label or "").startswith(prefix):
            return color
    return GREY


def type_badge(label: str | None) -> dict:
    return {"text": label or "Séance", "tone": type_color(label)}


def parse_clock(txt) -> float | None:
    """'4:05' → 245, '1:29:00' → 5340."""
    try:
        parts = [int(x) for x in str(txt).strip().replace("'", ":").split(":")]
    except ValueError:
        return None
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return None
