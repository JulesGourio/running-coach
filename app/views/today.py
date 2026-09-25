from collections import Counter
from datetime import date

import pandas as pd
import streamlit as st

from coach import service
from common import LEVEL_COLOR, LEVEL_ICON, ctx, fdate, fdur, fnum

s, db = ctx()
st.title("Carnet de course")
if s.goal_date:
    g = date.fromisoformat(s.goal_date)
    st.caption(f"{s.goal_label} le {fdate(g)} · J-{(g - date.today()).days} · objectif A {fdur(s.goal_a)} · objectif B {fdur(s.goal_b)}")

if not db.activities():
    st.info("Aucune séance en base. Lance `uv run coach login` puis `uv run coach sync` dans le terminal, "
            "ou `uv run coach import-fit <dossier>` pour importer des fichiers FIT.")
    st.stop()

r = service.readiness_today(db, s)
c1, c2 = st.columns([1, 2], gap="large")
with c1:
    st.subheader("Forme du jour")
    lvl = r["level"]
    st.markdown(f":{LEVEL_COLOR[lvl]}-badge[{LEVEL_ICON[lvl]} {lvl.capitalize()}]")
    st.metric("Disponibilité", f"{r['score']}/100" if r["score"] is not None else "—",
              help="Combine ta VFC et ta FC de repos (comparées à tes 4 dernières semaines), le sommeil et la fraîcheur (TSB).")
    for reason in r["reasons"]:
        st.markdown(f"- {reason}")
with c2:
    st.subheader("Séance du jour")
    today = r.get("today")
    if today and today["courses"]:
        for c in today["courses"]:
            st.markdown(f"**{c['name']}**")
            st.caption(c["summary"])
        if r.get("advice"):
            st.info(r["advice"], icon=":material/lightbulb:")
    else:
        st.markdown("Pas de séance prévue aujourd'hui.")

lm = service.load_model(db)
now = lm["now"]
st.subheader("Charge d'entraînement")
k = st.columns(5)
k[0].metric("Forme (CTL)", fnum(now.get("ctl"), 0), help="Moyenne pondérée de la charge sur 42 jours : ce que ton corps a assimilé.")
k[1].metric("Fatigue (ATL)", fnum(now.get("atl"), 0), help="Moyenne pondérée de la charge sur 7 jours.")
k[2].metric("Fraîcheur (TSB)", fnum(now.get("tsb"), 0), help="Forme moins fatigue, la veille. Sous -20 : fatigue élevée. Entre +5 et +15 : frais pour une course.")
k[3].metric("Ratio aigu/chronique", fnum(now.get("acwr"), 2), help="Charge des 7 derniers jours / moyenne sur 28 jours. Au-dessus de 1,3 : risque de blessure accru.")
k[4].metric("Monotonie", fnum(lm["monotony"], 1), help="Moyenne / écart-type de la charge sur 7 jours. Au-dessus de 2 : semaines trop uniformes, peu de vraie récupération.")

pr = service.progress(db, s)
st.subheader("Objectif")
rows = []
for method, t in pr["predictions"].items():
    rows.append({"Méthode": method, "10 km prédit": fdur(t),
                 "Écart objectif A": ("+" if t > s.goal_a else "−") + fdur(abs(t - s.goal_a)),
                 "Écart objectif B": ("+" if t > s.goal_b else "−") + fdur(abs(t - s.goal_b))})
if rows:
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
proj = pr["projection"]
if proj:
    p = pr["probabilities"]
    st.markdown(f"Projection au {fdate(s.goal_date)} : **{fdur(proj['projected'])}** "
                f"(fourchette {fdur(proj['low'])} – {fdur(proj['high'])}), tendance {fnum(proj['slope_s_per_week'], 0)} s par semaine"
                + (", plafonnée à 1 % de progrès par semaine" if proj["capped"] else "") + ".")
    st.markdown(f"Probabilité estimée : objectif A **{p.get('A', 0):.0%}** · objectif B **{p.get('B', 0):.0%}**")
    st.caption("Estimation statistique à partir de la tendance récente de la prédiction. Elle suppose que l'entraînement continue au même rythme.")
st.caption("Vitesse critique, Riegel et VDOT sont calculés sur tes meilleurs efforts à l'entraînement des 90 derniers jours, "
           "pas sur des courses : c'est une estimation prudente.")

recent = service.sessions(db, 14)
flags = Counter(f for x in recent for f in x["flags"])
missed = [p for p in service.plan_view(db, s, back=14, ahead=0) if p["status"] == "manquée"]
alerts = []
if flags["trop_intense"] or flags["trop_rapide"]:
    n = len([x for x in recent if {"trop_intense", "trop_rapide"} & set(x["flags"])])
    alerts.append(f"{n} séance{'s' if n > 1 else ''} facile{'s' if n > 1 else ''} courue{'s' if n > 1 else ''} trop fort sur 14 jours.")
if flags["decouplage"]:
    alerts.append(f"Découplage cardiaque au-delà de 5 % sur {flags['decouplage']} sortie(s) : endurance à consolider.")
if flags["reps_trop_rapides"]:
    alerts.append(f"Répétitions trop rapides sur {flags['reps_trop_rapides']} séance(s) : tu en fais plus que prévu.")
if missed:
    alerts.append(f"{len(missed)} séance{'s' if len(missed) > 1 else ''} du plan manquée{'s' if len(missed) > 1 else ''} sur 14 jours.")
if alerts:
    st.subheader("À surveiller")
    for a in alerts:
        st.warning(a, icon=":material/warning:")

st.subheader("Dernières séances")
table = [{"Date": fdate(x["date"]), "Séance": x["name"], "Type": x["kind_fr"], "Note": x["score"],
          "Constat": (x["findings"] or [""])[0], "Verdict du coach": "oui" if x["coach_verdict"] else ""}
         for x in recent]
st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch",
             column_config={"Note": st.column_config.ProgressColumn("Note", min_value=0, max_value=10, format="%.1f")})
