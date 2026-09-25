from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from coach import service
from common import BAND, BLUE, LEVEL_COLOR, LEVEL_ICON, ORANGE, ctx, style

s, db = ctx()
st.title("Récupération")
r = service.readiness_today(db, s)
st.markdown(f":{LEVEL_COLOR[r['level']]}-badge[{LEVEL_ICON[r['level']]} {r['level'].capitalize()}] "
            f"Disponibilité {r['score'] if r['score'] is not None else '—'}/100")
for reason in r["reasons"]:
    st.markdown(f"- {reason}")

daily = pd.DataFrame(db.daily((date.today() - timedelta(days=60)).isoformat()))
if daily.empty:
    st.info("Pas encore de données de récupération synchronisées.")
    st.stop()
daily["date"] = pd.to_datetime(daily["date"])
night = daily["date"] - pd.Timedelta(days=1)

c1, c2 = st.columns(2)
h = daily.dropna(subset=["hrv"])
if len(h):
    fig = go.Figure()
    if h["hrv_lo"].notna().any():
        fig.add_scatter(x=h["date"], y=h["hrv_hi"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
        fig.add_scatter(x=h["date"], y=h["hrv_lo"], mode="lines", line=dict(width=0), fill="tonexty", fillcolor=BAND,
                        name="Plage normale", hoverinfo="skip")
    fig.add_scatter(x=h["date"], y=h["hrv"], mode="lines+markers", line=dict(color=BLUE, width=2), name="VFC",
                    hovertemplate="%{x|%d %b} : %{y:.0f} ms<extra></extra>")
    style(fig, 280).update_layout(title="VFC nocturne (ms)")
    c1.plotly_chart(fig, width="stretch")
    c1.caption("Datée au jour du réveil. Une VFC sous ta plage normale plusieurs jours de suite signale une fatigue à respecter.")

rh = daily.dropna(subset=["rhr"])
if len(rh):
    fig = go.Figure(go.Scatter(x=rh["date"], y=rh["rhr"], mode="lines+markers", line=dict(color=ORANGE, width=2), name="FC repos",
                               hovertemplate="%{x|%d %b} : %{y:.0f} bpm<extra></extra>"))
    fig.add_scatter(x=rh["date"], y=rh["rhr"].rolling(7, min_periods=3).mean(), mode="lines", name="Moyenne 7 j",
                    line=dict(color=ORANGE, width=1, dash="dot"))
    style(fig, 280).update_layout(title="FC de repos (bpm)")
    c2.plotly_chart(fig, width="stretch")

sl = daily.dropna(subset=["sleep_score"])
if len(sl):
    fig = go.Figure(go.Bar(x=sl["date"] - pd.Timedelta(days=1), y=sl["sleep_score"], marker_color=BLUE,
                           customdata=sl["sleep_total"].fillna(""),
                           hovertemplate="Nuit du %{x|%d %b} : %{y:.0f}/100 · %{customdata}<extra></extra>"))
    style(fig, 260).update_layout(title="Score de sommeil", showlegend=False, hovermode="closest", yaxis=dict(range=[0, 100]))
    st.plotly_chart(fig, width="stretch")
