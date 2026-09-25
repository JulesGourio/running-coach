from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from coach import service
from common import BLUE, MUTED, ORANGE, ctx, fdate, fdur, fnum, fpace, pace_ticks, style, time_ticks

s, db = ctx()
st.title("Progression")
pr = service.progress(db, s)
a = pr["athlete"]

k = st.columns(4)
fit = [f for f in db.fitness() if f.get("vo2max")]
k[0].metric("VO2max (COROS)", fnum(fit[-1]["vo2max"], 0) if fit else "—",
            delta=fnum(fit[-1]["vo2max"] - fit[0]["vo2max"], 0) if len(fit) > 1 else None)
cs = pr["critical_speed"]
k[1].metric("Vitesse critique", f"{fpace(cs['cs_pace'])}/km" if cs else "—",
            help="Allure tenable environ 30 à 40 min, calculée sur tes meilleurs efforts de 3 à 20 min (42 derniers jours).")
k[2].metric("Réserve anaérobie (D')", f"{fnum(cs['d_prime'], 0)} m" if cs else "—",
            help="Distance que tu peux courir au-dessus de ta vitesse critique avant d'être à bout.")
k[3].metric("VDOT", fnum(pr["vdot"], 1) if pr["vdot"] else "—", help="Indice de Jack Daniels calculé sur ton meilleur effort récent.")

series = pr["prediction_series"]
if series:
    x = [d for d, _ in series]
    y = [v for _, v in series]
    fig = go.Figure(go.Scatter(x=x, y=y, mode="lines+markers", name="Prédiction 10 km", line=dict(color=BLUE, width=2),
                               customdata=[fdur(v) for v in y], hovertemplate="%{x|%d %b} : %{customdata}<extra></extra>"))
    goal_day = date.fromisoformat(s.goal_date) if s.goal_date else None
    proj = pr["projection"]
    if proj and goal_day:
        fig.add_scatter(x=[x[-1], goal_day], y=[y[-1], proj["projected"]], mode="lines", name="Projection",
                        line=dict(color=BLUE, dash="dot", width=2), hoverinfo="skip")
        fig.add_scatter(x=[goal_day, goal_day], y=[proj["low"], proj["high"]], mode="lines", name="Fourchette",
                        line=dict(color=BLUE, width=6), opacity=0.35, hoverinfo="skip")
    for t, name in ((s.goal_a, "Objectif A"), (s.goal_b, "Objectif B")):
        if t:
            fig.add_hline(y=t, line=dict(color=MUTED, dash="dash"), annotation_text=f"{name} {fdur(t)}",
                          annotation_font_color=MUTED, annotation_position="top left")
    style(fig, 320).update_layout(title="Prédiction 10 km et projection vers le jour J")
    time_ticks(fig, y + [s.goal_a or y[0], s.goal_b or y[0]] + ([proj["low"], proj["high"]] if proj else []))
    st.plotly_chart(fig, width="stretch")
    if pr["probabilities"]:
        p = pr["probabilities"]
        st.markdown(f"Probabilité estimée d'atteindre l'objectif A : **{p.get('A', 0):.0%}**, l'objectif B : **{p.get('B', 0):.0%}**.")

preds = pr["predictions"]
if preds:
    st.subheader("Prédictions 10 km")
    if "COROS" in preds:
        st.caption("COROS est la référence la plus fiable tant qu'aucune course ou effort continu 5/10 km "
                   "n'a été couru cette année pour recalibrer les autres méthodes.")
    st.dataframe(pd.DataFrame([{"Méthode": k_, "Temps": fdur(v), "Allure": f"{fpace(v / 10)}/km"} for k_, v in preds.items()]),
                 hide_index=True)

c1, c2 = st.columns(2)
ph = pr["pace_at_hr"]
if len(ph):
    fig = go.Figure(go.Scatter(x=ph["date"], y=ph["pace_at_hr"], mode="markers+lines", line=dict(color=BLUE, width=2),
                               customdata=ph["pace_at_hr"].map(fpace), hovertemplate="%{x|%d %b} : %{customdata}/km<extra></extra>"))
    style(fig, 280, "pace").update_layout(title=f"Allure à {pr['ref_hr']} bpm (footings et sorties longues)", showlegend=False)
    pace_ticks(fig, ph["pace_at_hr"].tolist())
    c1.plotly_chart(fig, width="stretch")
    c1.caption("Si la courbe monte (allure plus rapide à la même FC), ton moteur aérobie progresse. C'est l'indicateur le plus fiable.")
else:
    c1.info(f"Pas assez de footings avec une FC moyenne proche de {pr['ref_hr']} bpm pour tracer la tendance.")

ef = pd.DataFrame(pr["ef_rows"])
if len(ef):
    ef["date"] = pd.to_datetime(ef["date"])
    ef = ef.sort_values("date")
    fig = go.Figure(go.Scatter(x=ef["date"], y=ef["ef"], mode="markers", marker=dict(color=ORANGE, size=8), name="Efficacité",
                               hovertemplate="%{x|%d %b} : %{y:.2f}<extra></extra>"))
    if len(ef) >= 4:
        fig.add_scatter(x=ef["date"], y=ef["ef"].rolling(4, min_periods=2).mean(), mode="lines", name="Moyenne sur 4",
                        line=dict(color=ORANGE, width=2))
    style(fig, 280).update_layout(title="Efficacité (m/min par battement) en endurance")
    c2.plotly_chart(fig, width="stretch")

be = pr["best_efforts"]
if be:
    st.subheader("Meilleurs efforts (90 jours)")
    names = {"400": "400 m", "1000": "1 km", "1609": "1 mile", "3000": "3 km", "5000": "5 km", "10000": "10 km", "21097": "Semi"}
    st.dataframe(pd.DataFrame([{"Distance": names.get(k_, k_), "Temps": fdur(t), "Allure": f"{fpace(t / (int(k_) / 1000))}/km",
                                "Date": fdate(d)} for k_, (t, d) in sorted(be.items(), key=lambda kv: int(kv[0]))]),
                 hide_index=True, width="stretch")
    st.caption("Efforts extraits de n'importe quelle portion de tes séances : un 5 km peut être la fin d'une sortie longue.")

st.caption(f"Profil : FC max {a['hr_max']:.0f} bpm · FC repos {a['hr_rest']:.0f} bpm · FC seuil {a['lt_hr']:.0f} bpm · "
           f"allure seuil {fpace(a['threshold_pace'])}/km — détails et zones sur la page **Aujourd'hui**.")
