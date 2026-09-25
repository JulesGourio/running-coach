from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from coach import service
from coach.metrics import progress as prog
from common import (BLUE, CRIT, GOOD, MUTED, ctx, fdate, fdur, fnum, fpace, pace_ticks, style, time_ticks, tint,
                    TYPE_SYMBOLS, type_color)

s, db = ctx()
st.title("Progression")
pr = service.progress(db, s)
a = pr["athlete"]
vma, est, proj = pr["vma"], pr["estimate"], pr["projection"]
kmh = lambda v: f"{fnum(v * 3.6, 1)} km/h" if v else "—"  # noqa: E731
SOURCE_TXT = {"test": "ton test", "manuel": "la valeur que tu as fixée", "cardio": "la relation FC-vitesse de ta meilleure séance",
              "fractionnes": "les allures de tes fractionnés", "seuil": "ton allure seuil COROS"}

# ---- VMA ------------------------------------------------------------------------------------------------
st.subheader("Ta VMA", divider="gray")
c1, c2 = st.columns([1, 3], vertical_alignment="center")
with c1:
    st.metric("VMA retenue", kmh(vma.get("retenue")), border=True,
              delta=f"{fpace(1000 / vma['retenue'])}/km" if vma.get("retenue") else None, delta_color="off",
              help="Celle qui sert aux prédictions et aux allures du plan.")
with c2:
    src = vma.get("source")
    st.markdown(f"Retenue d'après **{SOURCE_TXT.get(src, src)}**.")
    if src in ("test", "manuel"):
        t = vma["test"]
        st.caption(f"Test du {fdate(t['date'])} ({t['detail']}). Il prime sur les estimations pendant 10 semaines.")
    else:
        st.caption("Pas de test récent : c'est une estimation. Un test de 6 minutes la remplacerait "
                   "(bouton plus bas, et proposé dans la page Plan).")
with st.container(horizontal=True):
    if vma.get("test"):
        st.metric("Test", kmh(vma["test"]["vma"]), border=True, help=vma["test"]["detail"])
    rng = vma.get("cardio_range")
    st.metric("FC-vitesse", kmh(vma.get("cardio")), border=True,
              delta=f"{fnum(rng[0] * 3.6, 1)}–{fnum(rng[1] * 3.6, 1)} km/h" if rng else None, delta_color="off",
              help="Échauffement et répétitions d'une même séance : la vitesse monte avec la FC presque en ligne droite. "
                   "Prolongée jusqu'à 97 % de ta FC max, elle donne la vitesse à VO2max, même si les répétitions n'étaient "
                   f"pas à fond. Fourchette : 95 % à 100 % de la FC max ({a['hr_max']:.0f} bpm, estimée)."
                   + (f" Séance utilisée : {fdate(vma['cardio_date'])}." if vma.get("cardio_date") else ""))
    st.metric("Allures des fractionnés", kmh(vma.get("fractionnes")), border=True,
              help="Chaque répétition (tours de la montre) ramenée à la VMA selon sa durée : un 400 m se court vers 105 % "
                   "de VMA, un 1000 m vers 98 %. C'est un plancher : ce que tu as couru, pas forcément ton maximum.")
    st.metric("Seuil COROS", kmh(vma.get("seuil")), border=True,
              help=f"Allure seuil COROS {fpace(a['threshold_pace'])}/km, le seuil se situant vers 87 % de VMA.")
    st.metric("VO2max COROS", kmh(vma.get("vo2max")), border=True,
              help="VO2max de la montre / 3,5. Estimation de la montre, souvent optimiste : non utilisée pour la VMA retenue.")

with st.expander("Enregistrer un test de VMA", icon=":material/timer:"):
    kind = st.radio("Type de test", list(prog.TEST_KINDS), format_func=prog.TEST_KINDS.get, key="t-kind")
    day = st.date_input("Date", date.today(), max_value=date.today(), key="t-date", format="DD/MM/YYYY")
    try:
        if kind == "6min":
            d = st.number_input("Distance parcourue en 6 minutes (m)", 1000, 2400, 1600, 10, key="t-6")
            v, detail = prog.vma_from_test("6min", distance_m=d), f"test 6 min, {d} m"
        elif kind == "effort":
            cc1, cc2 = st.columns(2)
            d = cc1.number_input("Distance (m)", 800, 21100, 3000, 100, key="t-d")
            tt = cc2.text_input("Temps (min:s ou h:min:s)", "11:00", key="t-t")
            parts = [int(x) for x in tt.strip().split(":")]
            secs = parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1]
            v, detail = prog.vma_from_test("effort", distance_m=d, time_s=secs), f"{d} m en {tt}"
        else:
            k = st.number_input("VMA (km/h)", 12.0, 24.0, 16.0, 0.1, key="t-k")
            v, detail = prog.vma_from_test("manuel", kmh=k), f"VMA saisie {fnum(k, 1)} km/h"
        st.markdown(f"→ VMA **{kmh(v)}** ({fpace(1000 / v)}/km), 10 km estimé **{fdur(prog.predict_from_vma(v, s.goal_distance_m))}**")
        if st.button("Enregistrer", type="primary", key="t-save"):
            service.add_vma_test(db, day.isoformat(), kind, v, detail)
            st.rerun()
    except (ValueError, IndexError):
        st.error("Temps au format 11:00 ou 1:05:30.")
    for t in reversed(service.vma_tests(db)):
        cc1, cc2 = st.columns([5, 1], vertical_alignment="center")
        cc1.markdown(f"{fdate(t['date'])} · **{kmh(t['vma'])}** · {t['detail']}")
        if cc2.button("Supprimer", key=f"del-{t['date']}"):
            service.delete_vma_test(db, t["date"])
            st.rerun()

# ---- 10 km -------------------------------------------------------------------------------------------
st.subheader("10 km", divider="gray")
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
        fig.add_scatter(x=[d for d, _ in series], y=[v for _, v in series], mode="lines+markers", name="Estimation (VMA)",
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
    st.caption("Courbe grise : 10 km déduit de la VMA retenue chaque semaine (sur les 6 semaines précédentes). "
               "Zone bleue : projection au jour J si le plan est suivi, incertitude comprise.")
preds = pr["predictions"]
if preds:
    st.dataframe(pd.DataFrame([{"Méthode": k_, "Temps": fdur(v), "Allure": f"{fpace(v / 10)}/km"} for k_, v in preds.items()]),
                 hide_index=True)

# ---- every distance --------------------------------------------------------------------------------------
st.subheader("Toutes les distances", divider="gray")
allp = service.predictions_all(db, s, pr)
st.dataframe(pd.DataFrame([{
    "Distance": r["distance"], "Estimation": fdur(r["estimate"]) if r["estimate"] else "—",
    "Allure": f"{fpace(r['pace'])}/km" if r["pace"] else "—",
    **{k: fdur(v) for k, v in r["methods"].items()},
    "Ton record": f"{fdur(r['real']['time'])} ({fdate(r['real']['date'])})" if r["real"] else "—"} for r in allp]),
    hide_index=True, width="stretch")
st.caption("Estimation = médiane des méthodes. Au-delà du 10 km, l'endurance compte autant que la VMA : les méthodes "
           "fondées sur la VMA supposent une endurance de coureur entraîné sur la distance, ton record sert de repère.")

# ---- goals A/B week by week ------------------------------------------------------------------------------
track = service.goal_track(db, s, pr)
if track:
    st.subheader("Suivi des objectifs, semaine par semaine", divider="gray")
    tk = pd.DataFrame(track)
    tk["week"] = pd.to_datetime(tk["week"])
    fig = go.Figure()
    fig.add_scatter(x=tk["week"], y=tk["A"] * 100, mode="lines+markers", name=f"Objectif A ({fdur(s.goal_a)})",
                    line=dict(color=CRIT, width=2), hovertemplate="%{x|%d %b} : %{y:.0f} %<extra>A</extra>")
    fig.add_scatter(x=tk["week"], y=tk["B"] * 100, mode="lines+markers", name=f"Objectif B ({fdur(s.goal_b)})",
                    line=dict(color=GOOD, width=2), hovertemplate="%{x|%d %b} : %{y:.0f} %<extra>B</extra>")
    style(fig, 280).update_layout(title="Chances d'atteindre chaque objectif (%)", yaxis=dict(range=[0, 100], ticksuffix=" %"))
    st.plotly_chart(fig, width="stretch")
    st.dataframe(pd.DataFrame([{"Semaine du": fdate(r["week"]), "10 km estimé": fdur(r["estimate"]),
                                "Projection jour J": f"{fdur(r['projected'])} ({fdur(r['low'])}–{fdur(r['high'])})",
                                "Chances A": f"{(r['A'] or 0):.0%}", "Chances B": f"{(r['B'] or 0):.0%}"} for r in reversed(track)]),
                 hide_index=True, width="stretch")
    st.caption("Un point par semaine, enregistré quand tu ouvres l'appli : la courbe se construit au fil de la préparation.")

# ---- rep paces over time -------------------------------------------------------------------------------
trend = pd.DataFrame([r for r in pr.get("rep_trend") or [] if not r["category"].startswith("Sortie longue")])
if len(trend):
    st.subheader("Allure de tes répétitions", divider="gray")
    fig = go.Figure()
    for cat, g in trend.groupby("category"):
        fig.add_scatter(x=pd.to_datetime(g["date"]), y=g["pace"], mode="markers+lines", name=cat,
                        line=dict(color=type_color(cat), width=1.5),
                        marker=dict(size=11, color=type_color(cat), symbol=TYPE_SYMBOLS.get(cat, "circle")),
                        customdata=list(zip(g["pace"].map(fpace), g["best"].map(fpace), g["structure"].fillna(""))),
                        hovertemplate="%{x|%d %b} · %{customdata[2]}<br>médiane %{customdata[0]}/km · meilleure %{customdata[1]}/km"
                                      "<extra>" + cat + "</extra>")
    style(fig, 320, "pace").update_layout(title="Allure médiane des répétitions, par type de séance", hovermode="closest")
    pace_ticks(fig, trend["pace"].tolist())
    st.plotly_chart(fig, width="stretch")
    st.caption("Un point par séance. Plus haut = plus rapide. À comparer entre séances du même type.")

# ---- training paces ------------------------------------------------------------------------------------
v_ref = vma.get("retenue")
if v_ref:
    st.subheader("Tes allures d'entraînement", divider="gray")
    vp = 1000 / v_ref
    rows = [
        ("VMA courte : 200-400 m, 30/30", vp / 1.07, vp / 1.03, "103-107 % VMA"),
        ("VMA longue : 800-1200 m, 3-4 min", vp / 1.00, vp / 0.96, "96-100 % VMA"),
        ("Allure 10 km actuelle", est / 10 if est else None, None, "ce que tu tiendrais aujourd'hui"),
        ("Objectif A / B", s.goal_a / 10 if s.goal_a else None, s.goal_b / 10 if s.goal_b else None, "sub-40 / 41:30"),
        ("Seuil", a["threshold_pace"] - 5, a["threshold_pace"] + 5, "tenable ~1 h (COROS)"),
        ("Endurance (Z2)", None, None, "zones sur la page Aujourd'hui"),
    ]
    st.dataframe(pd.DataFrame([{"Allure": n, "min/km": (f"{fpace(lo)}" + (f" – {fpace(hi)}" if hi else "")) if lo else "—",
                                "Repère": c_} for n, lo, hi, c_ in rows]), hide_index=True, width="stretch")
    st.caption("Toutes les séances de fractionné possibles, calculées sur cette VMA : page **Séances types**.")

be = pr["best_efforts"]
if be:
    st.subheader("Meilleurs efforts (90 jours)", divider="gray")
    names = {"400": "400 m", "1000": "1 km", "1609": "1 mile", "3000": "3 km", "5000": "5 km", "10000": "10 km", "21097": "Semi"}
    st.dataframe(pd.DataFrame([{"Distance": names.get(k_, k_), "Temps": fdur(t), "Allure": f"{fpace(t / (int(k_) / 1000))}/km",
                                "Date": fdate(d)} for k_, (t, d) in sorted(be.items(), key=lambda kv: int(kv[0]))]),
                 hide_index=True, width="stretch")
    st.caption("Meilleurs temps mesurés à l'intérieur d'une seule répétition ou d'un seul bloc (jamais à cheval sur une "
               "récupération) : ce ne sont pas des courses.")

st.caption(f"Profil : FC max {a['hr_max']:.0f} bpm · FC repos {a['hr_rest']:.0f} bpm · FC seuil {a['lt_hr']:.0f} bpm · "
           f"allure seuil {fpace(a['threshold_pace'])}/km — détails et zones sur la page **Aujourd'hui**.")
