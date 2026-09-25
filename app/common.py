from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coach.config import Settings, get_settings  # noqa: E402
from coach.db import DB  # noqa: E402
from coach.metrics.zones import Athlete  # noqa: E402

BLUE, ORANGE = "#2e6fdb", "#d9480f"
GOOD, WARN, CRIT, MUTED = "#1a7f37", "#c9750a", "#cf222e", "#6b7280"
BAND = "rgba(46,111,219,0.10)"
DOW = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
MON = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
LEVEL_ICON = {"vert": ":material/check_circle:", "orange": ":material/warning:", "rouge": ":material/block:", "inconnu": ":material/help:"}
LEVEL_COLOR = {"vert": "green", "orange": "orange", "rouge": "red", "inconnu": "gray"}


def ctx() -> tuple[Settings, DB]:
    s = get_settings()
    return s, DB(s.db_path)


def fpace(sec) -> str:
    if sec is None or sec != sec:
        return "—"
    sec = round(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def fdur(sec) -> str:
    if sec is None or sec != sec:
        return "—"
    sec = round(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fdate(d: str | date) -> str:
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return f"{DOW[d.weekday()]} {d.day} {MON[d.month - 1]}"


def fnum(v, dec=1) -> str:
    return "—" if v is None or v != v else f"{v:.{dec}f}".replace(".", ",")


def _is_date(xs) -> bool:
    if xs is None or len(xs) == 0:
        return False
    x = xs[0]
    return isinstance(x, (date, pd.Timestamp, np.datetime64))


def style(fig: go.Figure, height: int = 280, yfmt: str | None = None) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=56, r=16, t=40, b=36), hovermode="x unified",
                      legend=dict(orientation="h", yanchor="top", y=-0.14, x=0), plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False, automargin=True)
    if any(_is_date(t.x) for t in fig.data):
        fig.update_xaxes(tickformat="%d/%m")
    fig.update_yaxes(gridcolor="rgba(137,135,129,0.25)", zeroline=False, automargin=True)
    if yfmt == "pace":
        fig.update_yaxes(autorange="reversed")
    return fig


def pace_ticks(fig: go.Figure, values: list[float]) -> None:
    """Round min:s ticks (every 10/15/20/30/60 s) and a fixed reversed range over `values` (pass robust
    quantiles, not raw data: a GPS dropout would otherwise stretch the axis)."""
    vals = [v for v in values if v == v]
    if not vals:
        return
    lo, hi = min(vals), max(vals)
    pad = max(5.0, (hi - lo) * 0.08)
    lo, hi = lo - pad, hi + pad
    step = next((s_ for s_ in (10, 15, 20, 30, 60, 120) if (hi - lo) / s_ <= 6), 120)
    first = int(-(-lo // step) * step)
    ticks = list(range(first, int(hi) + 1, step))
    fig.update_yaxes(tickvals=ticks, ticktext=[fpace(t) for t in ticks], range=[hi, lo], autorange=False)


def time_ticks(fig: go.Figure, values: list[float]) -> None:
    vals = [v for v in values if v == v]
    if not vals:
        return
    lo, hi = int(min(vals) // 30 * 30), int(max(vals) // 30 * 30 + 30)
    step = max(30, (hi - lo) // 5 // 30 * 30 or 30)
    ticks = list(range(lo, hi + 1, step))
    fig.update_yaxes(tickvals=ticks, ticktext=[fdur(t) for t in ticks])


# One color per zone, cold to hot, used everywhere a zone appears (tables, HR bands, time-in-zone bars).
ZONE_COLORS = {"Z1 récup": "#94a3b8", "Z2 endurance": "#2e6fdb", "Z3 tempo": "#16a34a",
               "Z4 seuil": "#ea8a0c", "Z5 VO2max": "#dc2626"}

# Session type → color, matched on the start of the French label.
TYPE_COLORS = [("VMA", "#dc2626"), ("Seuil", "#ea8a0c"), ("Tempo", "#d97706"), ("Allure", "#9333ea"),
               ("Sortie longue", "#0d9488"), ("Course", "#111827"), ("Footing", "#2e6fdb")]


TYPE_BADGES = [("VMA", "red"), ("Seuil", "orange"), ("Tempo", "orange"), ("Allure", "violet"),
               ("Sortie longue", "green"), ("Course", "gray"), ("Footing", "blue")]


def type_badge(label: str | None) -> str:
    """Markdown badge for a session type, e.g. ':red-badge[VMA (hors plan)]'."""
    color = next((c for p, c in TYPE_BADGES if (label or "").startswith(p)), "gray")
    return f":{color}-badge[{label or 'Séance'}]"


def type_color(label: str | None) -> str:
    for prefix, color in TYPE_COLORS:
        if (label or "").startswith(prefix):
            return color
    return MUTED


def tint(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"


def color_types(df: pd.DataFrame, column: str = "Type"):
    """Styler coloring a session-type column (text in the type's color, on a light tint)."""
    return df.style.map(lambda v: f"color: {type_color(v)}; background-color: {tint(type_color(v), 0.10)}; "
                                  "font-weight: 600", subset=[column])


ZONE_PURPOSE = {
    "Z1 récup": "Récupération : très facile, conversation aisée.",
    "Z2 endurance": "Endurance fondamentale : l'essentiel du volume, ~80 % des séances.",
    "Z3 tempo": "Tempo : zone grise, à limiter — ni vraiment facile ni vraiment qualité.",
    "Z4 seuil": "Seuil : l'intensité maximale tenable environ 1 heure.",
    "Z5 VO2max": "VO2max / VMA : efforts courts et intenses, fractionnés.",
}


def zone_table(a: Athlete):
    """Z1-Z5 with real bpm and pace bounds for this athlete, instead of bare zone names."""
    hr_b, pace_b = a.hr_zone_bounds(), a.pace_zone_bounds()
    rows = []
    for i, ((name, hlo, hhi), (_, plo, phi)) in enumerate(zip(hr_b, pace_b)):
        if i == 0:
            hr_txt, pace_txt = f"< {hhi:.0f}", f"> {fpace(plo)}"
        elif i == len(hr_b) - 1:
            hr_txt, pace_txt = f"> {hlo:.0f}", f"< {fpace(phi)}"
        else:
            hr_txt, pace_txt = f"{hlo:.0f}–{hhi:.0f}", f"{fpace(plo)}–{fpace(phi)}"
        rows.append({"Zone": name, "FC (bpm)": hr_txt, "Allure (min/km)": pace_txt, "But": ZONE_PURPOSE.get(name, "")})
    df = pd.DataFrame(rows)
    return df.style.apply(lambda row: [f"background-color: {tint(ZONE_COLORS.get(row['Zone'], MUTED), 0.14)}; "
                                       f"color: {ZONE_COLORS.get(row['Zone'], MUTED)}; font-weight: 600"
                                       if c == "Zone" else "" for c in row.index], axis=1)


def sidebar() -> None:
    s, db = ctx()
    with st.sidebar:
        st.caption(f"Données : `{s.data_dir}`")
        if st.button("Synchroniser COROS", icon=":material/sync:", width="stretch"):
            from coach.sources.coros_mcp import NeedsLogin, describe
            from coach.sync import analyze, sync_mcp
            logs: list[str] = []
            with st.spinner("Récupération des données COROS…"):
                try:
                    asyncio.run(sync_mcp(s, db, days=21, interactive=False, log=logs.append))
                    analyze(s, db, log=logs.append)
                    st.cache_data.clear()
                    st.success("\n\n".join(logs) or "Synchronisé.")
                except NeedsLogin as e:
                    st.warning(f"{e}\n\nLance la commande dans le terminal de VS Code, puis réessaie.")
                except Exception as e:  # noqa: BLE001
                    st.error(f"Synchronisation impossible : {describe(e)}")
        st.caption("Première connexion : `uv run coach login` dans le terminal.")
