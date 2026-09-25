from collections import Counter
from datetime import date

import pandas as pd
import streamlit as st

from coach import service
from common import LEVEL_COLOR, LEVEL_ICON, color_types, ctx, fdate, fdur, fnum, fpace, zone_table

s, db = ctx()
st.title("Carnet de course")
if s.goal_date:
    g = date.fromisoformat(s.goal_date)
    st.caption(f":material/flag: {s.goal_label} le {fdate(g)} · **J-{(g - date.today()).days}** · "
               f"objectif A {fdur(s.goal_a)} · objectif B {fdur(s.goal_b)}")

if not db.activities():
    st.info("Aucune séance en base. Lance `uv run coach login` puis `uv run coach sync` dans le terminal, "
            "ou `uv run coach import-fit <dossier>` pour importer des fichiers FIT.")
    st.stop()

from coach import alerts as al  # noqa: E402

for x in al.alerts(db, s):
    box = {"rouge": st.error, "orange": st.warning, "info": st.info}[x["level"]]
    box(f"**{x['title']}** — {x['detail']}  \n{x['advice']}", icon={"rouge": ":material/error:", "orange": ":material/warning:",
                                                                   "info": ":material/info:"}[x["level"]])

# ---- Where you stand vs the goal -------------------------------------------------------------------
pr = service.progress(db, s)
service.goal_track(db, s, pr)  # records this week's point of the A/B tracking
est, proj, probs, vma = pr["estimate"], pr["projection"], pr["probabilities"], pr["vma"]
with st.container(horizontal=True):
    if est:
        gap = est - s.goal_b
        st.metric("10 km estimé aujourd'hui", fdur(est), border=True,
                  delta=f"{'+' if gap > 0 else '−'}{fdur(abs(gap))} vs objectif B", delta_color="inverse",
                  help="Médiane de trois estimations indépendantes (détail plus bas) : ta VMA tirée de tes "
                       "fractionnés, la prédiction COROS, et ton allure seuil COROS.")
    if proj:
        basis = "ta tendance récente" if proj["basis"] == "tendance" else "gain typique d'un bloc structuré suivi"
        st.metric(f"Projection au {fdate(s.goal_date)}", fdur(proj["projected"]), border=True,
                  delta=f"fourchette {fdur(proj['low'])} – {fdur(proj['high'])}", delta_color="off",
                  help=f"Niveau actuel amélioré de {proj['gain_per_week'] * 100:.1f} % par semaine sur "
                       f"{proj['weeks']:.0f} semaines ({basis}). La fourchette couvre ±0,3 %/semaine.")
    if probs:
        st.metric("Chances d'y arriver", f"A {probs.get('A', 0):.0%} · B {probs.get('B', 0):.0%}", border=True,
                  help="Probabilité que la projection passe sous chaque objectif, compte tenu de la fourchette.")
    if vma.get("retenue"):
        src = {"test": "test", "manuel": "fixée par toi", "cardio": "FC-vitesse", "fractionnes": "allures", "seuil": "seuil COROS"}[vma["source"]]
        st.metric("VMA retenue", f"{fnum(vma['retenue'] * 3.6, 1)} km/h", border=True,
                  delta=f"{fpace(1000 / vma['retenue'])}/km · {src}", delta_color="off",
                  help="Vitesse maximale aérobie. Un test récent prime ; sinon la relation FC-vitesse de ta meilleure "
                       "séance de fractionné (ou, à défaut, les allures courues). Détail et saisie d'un test : page Progression.")

with st.expander("Comment ces chiffres sont calculés", icon=":material/calculate:"):
    rows = [{"Méthode": k, "10 km": fdur(v), "Allure": f"{fpace(v / 10)}/km"} for k, v in pr["predictions"].items()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    lines = []
    if vma.get("test"):
        lines.append(f"- **Test du {fdate(vma['test']['date'])}** : {vma['test']['detail']} → VMA {fnum(vma['test']['vma'] * 3.6, 1)} km/h.")
    if vma.get("cardio"):
        lo_, hi_ = vma["cardio_range"]
        lines.append(f"- **Relation FC-vitesse** (séance du {fdate(vma['cardio_date'])}) : VMA {fnum(vma['cardio'] * 3.6, 1)} km/h "
                     f"(entre {fnum(lo_ * 3.6, 1)} et {fnum(hi_ * 3.6, 1)} selon la FC atteinte à VMA).")
    if vma.get("fractionnes"):
        lines.append(f"- **Allures des fractionnés** (tours de la montre, {' et '.join(fdate(d) for d in vma['fractionnes_seances'])}) : "
                     f"VMA {fnum(vma['fractionnes'] * 3.6, 1)} km/h — un plancher, ce que tu as couru.")
    if vma.get("seuil"):
        lines.append(f"- **Allure seuil COROS** ({fpace(pr['athlete']['threshold_pace'])}/km) : le seuil se situe vers 87 % "
                     f"de VMA, soit {fnum(vma['seuil'] * 3.6, 1)} km/h.")
    if vma.get("vo2max"):
        lines.append(f"- **VO2max COROS** : {fnum(vma['vo2max'] * 3.6, 1)} km/h (VO2max ≈ 3,5 × VMA). Estimation de la montre, "
                     "au-dessus des autres : non retenue. Un test de 6 minutes tranchera.")
    lines.append("- **10 km** : la VMA est convertie en temps de course selon la part tenable sur la durée (~90 % sur 40 min).")
    st.markdown("\n".join(lines))
    st.caption("Pas de course ni d'effort continu 5/10 km cette année : tout part des répétitions, isolées de la "
               "récupération. La projection suppose que le plan est suivi.")

# ---- Today -----------------------------------------------------------------------------------------
r = service.readiness_today(db, s)
c1, c2 = st.columns([1, 2], gap="medium")
with c1, st.container(border=True, height="stretch"):
    st.markdown("**Forme du jour**")
    lvl = r["level"]
    st.markdown(f"### :{LEVEL_COLOR[lvl]}[{LEVEL_ICON[lvl]} {r['score'] if r['score'] is not None else '—'}/100]")
    for reason in r["reasons"]:
        st.caption(reason)
with c2, st.container(border=True, height="stretch"):
    st.markdown("**Séance du jour**")
    today = r.get("today")
    if today and today["courses"]:
        for c in today["courses"]:
            st.markdown(f"#### {c['name']}")
            st.caption(c["summary"])
        if r.get("advice"):
            st.info(r["advice"], icon=":material/lightbulb:")
    else:
        st.markdown("Repos ou pas de séance prévue aujourd'hui.")

# ---- Load ------------------------------------------------------------------------------------------
lm = service.load_model(db)
now = lm["now"]
model_tail = lm["model"].tail(30)
st.subheader("Charge d'entraînement", divider="gray")
coros_load = next((d for d in reversed(db.daily()) if d.get("load_ratio")), None)
acwr = coros_load["load_ratio"] if coros_load else now.get("acwr")
with st.container(horizontal=True):
    st.metric("Forme", fnum(now.get("ctl"), 0), border=True, chart_data=model_tail["ctl"].tolist(), chart_type="line",
              help="Moyenne pondérée de la charge sur 42 jours : ce que ton corps a assimilé.")
    st.metric("Fatigue", fnum(now.get("atl"), 0), border=True, chart_data=model_tail["atl"].tolist(), chart_type="line",
              help="Moyenne pondérée de la charge sur 7 jours.")
    st.metric("Fraîcheur", fnum(now.get("tsb"), 0), border=True, chart_data=model_tail["tsb"].tolist(), chart_type="line",
              help="Forme moins fatigue, la veille. Sous -20 : fatigue élevée. Entre +5 et +15 : frais pour une course.")
    st.metric("Ratio de charge (COROS)" if coros_load else "Ratio aigu/chronique", fnum(acwr, 2), border=True,
              delta=("zone optimale" if acwr is not None and 0.8 <= acwr <= 1.3 else "à surveiller" if acwr and acwr > 1.3 else "charge basse")
              if acwr is not None and acwr == acwr else None,
              delta_color="normal" if acwr is not None and acwr == acwr and 0.8 <= acwr <= 1.3 else "inverse",
              help="Charge des 7 derniers jours / moyenne sur 28 jours. Zone optimale 0,8-1,3 ; au-dessus de 1,5 plusieurs jours : on allège.")
st.caption("Forme, fatigue et fraîcheur comptent tous tes sports : la course (détaillée) et les autres activités "
           "(randonnée, vélo…, estimées d'après la FC et la durée). Le ratio de charge vient de COROS : c'est le garde-fou.")

# ---- Training notes (from the analyses) ----------------------------------------------------------------
recent = service.sessions(db, 14)
flags = Counter(f for x in recent for f in x["flags"])
notes = []
if flags["trop_intense"] or flags["trop_rapide"]:
    n = len([x for x in recent if {"trop_intense", "trop_rapide"} & set(x["flags"])])
    notes.append(f"{n} footing{'s' if n > 1 else ''} couru{'s' if n > 1 else ''} trop fort sur 14 jours : garde l'endurance en Z2.")
if flags["decouplage"]:
    notes.append(f"Dérive cardiaque au-delà de 5 % sur {flags['decouplage']} sortie(s) : endurance à consolider.")
if flags["reps_trop_rapides"]:
    notes.append(f"Répétitions plus rapides que prévu sur {flags['reps_trop_rapides']} séance(s).")
if notes:
    with st.expander(f"Remarques sur tes séances ({len(notes)})", icon=":material/info:"):
        for msg in notes:
            st.markdown(f"- {msg}")

# ---- Recent sessions -------------------------------------------------------------------------------
st.subheader("Dernières séances", divider="gray")
table = pd.DataFrame([{"Date": fdate(x["date"]), "Type": x["kind_fr"] or "—", "Contenu": x.get("structure") or "",
                       "Km": x["distance_km"], "Plan": (f"{fnum(x['score'])}/10" if x["score"] is not None else "prévue")
                       if x.get("planned") else "hors plan", "Constat": (x["findings"] or [""])[0]}
                      for x in recent])
if len(table):
    st.dataframe(color_types(table), hide_index=True, width="stretch",
                 column_config={"Km": st.column_config.NumberColumn("Km", format="%.1f"),
                                "Plan": st.column_config.TextColumn("Plan", help="Respect du plan sur 10, pour les séances prévues."),
                                "Constat": st.column_config.TextColumn("Constat", width="large")})

# ---- Profile & zones -------------------------------------------------------------------------------
a = service.athlete(db, s)
vo2max = next((f["vo2max"] for f in reversed(db.fitness()) if f.get("vo2max")), None)
st.subheader("Profil & zones", divider="gray")
with st.container(horizontal=True):
    st.metric("FC max", f"{fnum(a.hr_max, 0)} bpm", border=True,
              help="Fréquence cardiaque maximale. Estimée depuis tes séances (2e pic le plus haut sur 120 jours, "
                   "pour ignorer un artefact capteur isolé) ; renseigne ATHLETE_HR_MAX dans .env pour la figer.")
    st.metric("FC repos", f"{fnum(a.hr_rest, 0)} bpm", border=True,
              help="Médiane de ta FC de repos mesurée par la montre sur les 30 derniers jours.")
    st.metric("FC seuil (LTHR)", f"{fnum(a.lt_hr, 0)} bpm", border=True,
              help="FC au seuil lactique : l'intensité que tu peux tenir environ 1 heure. Estimée depuis ta meilleure "
                   "moyenne sur 20 minutes continues, sinon 89 % de FC max par défaut.")
    st.metric("Allure seuil", f"{fpace(a.threshold_pace)}/km", border=True,
              help="Allure à l'intensité seuil. Vient du dernier bilan COROS.")
    st.metric("VO2max (COROS)", fnum(vo2max, 0) if vo2max else "—", border=True,
              help="Consommation maximale d'oxygène en ml/kg/min, estimée par la montre. Indicateur du moteur "
                   "aérobie ; la montre a tendance à la surestimer par rapport à ce que montrent les allures.")
st.dataframe(zone_table(a), hide_index=True, width="stretch")
st.caption("Zones calculées à partir de ta FC seuil et de ton allure seuil. Repère : ~80 % du temps d'entraînement en Z1-Z2.")
