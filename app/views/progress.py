from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from coach import service
from common import BLUE, CRIT, GOOD, MUTED, ORANGE, ctx, fdate, fdur, fnum, fpace, pace_ticks, style, time_ticks, tint

s, db = ctx()
st.title("Progression")
pr = service.progress(db, s)
a = pr["athlete"]

vma, est, proj = pr["vma"], pr["estimate"], pr["projection"]
kmh = lambda v: f"{fnum(v * 3.6, 1)} km/h" if v else "—"  # noqa: E731
with st.container(horizontal=True):
    st.metric("VMA (fractionnés)", kmh(vma.get("fractionnes")), border=True,
              delta=f"{fpace(1000 / vma['fractionnes'])}/km" if vma.get("fractionnes") else None, delta_color="off",
              help="Déduite de tes deux meilleures séances de fractionné des 6 dernières semaines (répétitions isolées "
                   "de la récup, ramenées à la VMA selon leur durée).")
    st.metric("VMA (seuil COROS)", kmh(vma.get("seuil")), border=True,
              help=f"Allure seuil COROS {fpace(a['threshold_pace'])}/km, le seuil se situant vers 87 % de VMA.")
    st.metric("VMA équivalente VO2max", kmh(vma.get("vo2max")), border=True,
              help="VO2max COROS / 3,5. Mesure le moteur aérobie, pas la vitesse spécifique : plus haute que ce que "
                   "montrent tes allures, elle indique une marge de progression en vitesse.")
    st.metric("10 km estimé", fdur(est) if est else "—", border=True,
              help="Médiane des estimations ci-dessous.")

goal_day = date.fromisoformat(s.goal_date) if s.goal_date else None
series = pr["prediction_series"]
if series or proj:
    fig = go.Figure()
    if proj and goal_day:
        today_ = date.today()
        fig.add_scatter(x=[today_, goal_day, goal_day, today_], y=[proj["current"], proj["low"], proj["high"], proj["current"]],
                        fill="toself", fillcolor=tint(BLUE, 0.12), line=dict(width=0), mode="lines", hoverinfo="skip",
                        name="Fourchette")
        fig.add_scatter(x=[today_, goal_day], y=[proj["current"], proj["projected"]], mode="lines+markers", name="Projection",
                        line=dict(color=BLUE, dash="dot", width=2), marker=dict(size=[8, 11]),
                        customdata=[fdur(proj["current"]), fdur(proj["projected"])],
                        hovertemplate="%{x|%d %b} : %{customdata}<extra></extra>")
    if series:
        fig.add_scatter(x=[d for d, _ in series], y=[v for _, v in series], mode="lines+markers", name="Estimation fractionnés",
                        line=dict(color=MUTED, width=1.5), marker=dict(size=6),
                        customdata=[fdur(v) for _, v in series], hovertemplate="%{x|%d %b} : %{customdata}<extra></extra>")
    for t, name, color in ((s.goal_a, "Objectif A", CRIT), (s.goal_b, "Objectif B", GOOD)):
        if t:
            fig.add_hline(y=t, line=dict(color=color, dash="dash", width=1.5), annotation_text=f"{name} {fdur(t)}",
                          annotation_font_color=color, annotation_position="top left")
    ys = [v for _, v in series] + ([proj["low"], proj["high"], proj["current"]] if proj else []) + [s.goal_a, s.goal_b]
    style(fig, 340).update_layout(title="10 km : estimation, projection et objectifs")
    time_ticks(fig, [y_ for y_ in ys if y_])
    st.plotly_chart(fig, width="stretch")
    if pr["probabilities"]:
        p = pr["probabilities"]
        st.markdown(f"Chances d'atteindre l'objectif A : **{p.get('A', 0):.0%}** · l'objectif B : **{p.get('B', 0):.0%}**.")
    st.caption("Courbe grise : 10 km estimé chaque semaine à partir des fractionnés des 6 semaines précédentes (elle bouge "
               "surtout selon les séances qui entrent dans la fenêtre). Zone bleue : projection au jour J si le plan est suivi.")

preds = pr["predictions"]
if preds:
    st.subheader("Estimations 10 km", divider="gray")
    st.dataframe(pd.DataFrame([{"Méthode": k_, "Temps": fdur(v), "Allure": f"{fpace(v / 10)}/km"} for k_, v in preds.items()]),
                 hide_index=True)

v_ref = vma.get("fractionnes") or vma.get("seuil")
if v_ref:
    st.subheader("Tes allures d'entraînement", divider="gray")
    vma_pace = 1000 / v_ref
    rows = [
        ("VMA (100 %)", vma_pace, "Référence : l'allure tenable ~6 min."),
        ("Répétitions 400 m (~105 %)", vma_pace / 1.05, "VMA courte."),
        ("Répétitions 1000 m (~98 %)", vma_pace / 0.98, "VMA longue."),
        ("Allure 10 km actuelle", est / 10 if est else None, "Ce que tu tiendrais aujourd'hui sur 10 km."),
        ("Objectif A", s.goal_a / 10 if s.goal_a else None, "Sub-40."),
        ("Objectif B", s.goal_b / 10 if s.goal_b else None, ""),
        ("Seuil", a["threshold_pace"], "Tenable ~1 h (COROS)."),
        ("Endurance (Z2)", None, "Voir les zones sur la page Aujourd'hui."),
    ]
    st.dataframe(pd.DataFrame([{"Allure": n, "min/km": f"{fpace(p_)}" if p_ else "—", "Repère": c_} for n, p_, c_ in rows]),
                 hide_index=True, width="stretch")

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
    st.caption("Meilleurs temps mesurés à l'intérieur d'une seule portion rapide (jamais à cheval sur une récupération) : "
               "ce ne sont pas des courses, les distances longues n'apparaissent que si tu les as courues d'une traite.")

st.caption(f"Profil : FC max {a['hr_max']:.0f} bpm · FC repos {a['hr_rest']:.0f} bpm · FC seuil {a['lt_hr']:.0f} bpm · "
           f"allure seuil {fpace(a['threshold_pace'])}/km — détails et zones sur la page **Aujourd'hui**.")
