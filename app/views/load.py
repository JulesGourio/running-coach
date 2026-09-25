import plotly.graph_objects as go
import streamlit as st

from coach import service
from common import BAND, BLUE, GOOD, MUTED, ORANGE, ZONE_COLORS, ctx, fnum, style

s, db = ctx()
st.title("Charge d'entraînement")
lm = service.load_model(db)
model, weekly = lm["model"], lm["weekly"]
if model.empty:
    st.info("Pas encore de séances analysées.")
    st.stop()

days = st.segmented_control("Période", [42, 90, 180], default=90, format_func=lambda d: f"{d} jours") or 90
m = model.tail(days)

fig = go.Figure()
fig.add_scatter(x=m.index, y=m["ctl"], name="Forme (CTL, 42 j)", line=dict(color=BLUE, width=2))
fig.add_scatter(x=m.index, y=m["atl"], name="Fatigue (ATL, 7 j)", line=dict(color=ORANGE, width=2))
style(fig, 300).update_layout(title="Forme et fatigue")
st.plotly_chart(fig, width="stretch")

c1, c2 = st.columns(2)
fig = go.Figure(go.Bar(x=m.index, y=m["tsb"], marker_color=[BLUE if v >= 0 else ORANGE for v in m["tsb"].fillna(0)],
                       name="Fraîcheur", hovertemplate="%{x|%d %b} : %{y:.0f}<extra></extra>"))
fig.add_hrect(y0=-30, y1=-10, fillcolor=BAND, line_width=0, annotation_text="zone d'entraînement productive",
              annotation_position="bottom left", annotation_font_color=MUTED)
style(fig, 260).update_layout(title="Fraîcheur (TSB = forme − fatigue)", showlegend=False)
c1.plotly_chart(fig, width="stretch")

fig = go.Figure(go.Scatter(x=m.index, y=m["acwr"], line=dict(color=BLUE, width=2), name="Ratio",
                           hovertemplate="%{x|%d %b} : %{y:.2f}<extra></extra>"))
fig.add_hrect(y0=0.8, y1=1.3, fillcolor=BAND, line_width=0, annotation_text="zone optimale", annotation_position="top left",
              annotation_font_color=MUTED)
fig.add_hline(y=1.5, line=dict(color=MUTED, dash="dash"), annotation_text="excessif", annotation_font_color=MUTED)
style(fig, 260).update_layout(title="Ratio charge aiguë / chronique", showlegend=False)
c2.plotly_chart(fig, width="stretch")

with st.container(horizontal=True):
    st.metric("Monotonie (7 j)", fnum(lm["monotony"], 2), border=True,
              help="Au-dessus de 2 : charge trop uniforme, manque de vraies journées faciles.")
    st.metric("Contrainte (7 j)", fnum(lm["strain"], 0), border=True, help="Charge de la semaine × monotonie (Foster).")
    st.metric("Charge 7 derniers jours", fnum(model["load"].tail(7).sum(), 0), border=True,
              chart_data=model["load"].tail(28).tolist(), chart_type="bar")

if not weekly.empty:
    w = weekly.tail(16)
    labels = [d.strftime("%d/%m") for d in w.index]
    c1, c2 = st.columns(2)
    fig = go.Figure(go.Bar(x=labels, y=w["km"], marker_color=BLUE, name="km",
                           customdata=w[["sessions", "hours"]].values,
                           hovertemplate="Semaine du %{x} : %{y:.1f} km · %{customdata[0]} séances · %{customdata[1]:.1f} h<extra></extra>"))
    style(fig, 280).update_layout(title="Volume par semaine (km)", showlegend=False, hovermode="closest")
    c1.plotly_chart(fig, width="stretch")

    fig = go.Figure()
    for col, name, color in (("pct_low", "Facile (Z1-Z2)", ZONE_COLORS["Z2 endurance"]), ("pct_mid", "Tempo (Z3)", ZONE_COLORS["Z3 tempo"]),
                             ("pct_high", "Intense (Z4-Z5)", ZONE_COLORS["Z5 VO2max"])):
        fig.add_bar(x=labels, y=w[col] * 100, name=name, marker_color=color,
                    hovertemplate=name + " : %{y:.0f} %<extra></extra>")
    fig.add_hline(y=80, line=dict(color=GOOD, dash="dot"), annotation_text="80 % facile", annotation_font_color=MUTED)
    style(fig, 280).update_layout(barmode="stack", title="Répartition de l'intensité (temps par zone de FC)",
                                  yaxis=dict(ticksuffix=" %", range=[0, 100]), hovermode="x")
    c2.plotly_chart(fig, width="stretch")
    st.caption("Les coureurs d'endurance progressent le mieux avec environ 80 % du temps en facile. "
               "Une grosse part de tempo (Z3) signale souvent des footings courus trop vite.")

    with st.expander("Données par semaine"):
        t = w.assign(semaine=labels)[["semaine", "km", "hours", "load", "sessions", "pct_low", "pct_mid", "pct_high"]]
        st.dataframe(t.rename(columns={"hours": "heures", "load": "charge", "sessions": "séances", "pct_low": "% facile",
                                       "pct_mid": "% tempo", "pct_high": "% intense"}).round(2),
                     hide_index=True, width="stretch")
