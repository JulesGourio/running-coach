import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from coach import service
from common import BLUE, MUTED, ORANGE, ctx, fdate, fdur, fnum, fpace, pace_ticks, style

s, db = ctx()
st.title("Séances")

rows = service.sessions(db, 120)
if not rows:
    st.info("Aucune séance synchronisée.")
    st.stop()


def label(x):
    score = f" · {fnum(x['score'])}/10" if x["score"] is not None else ""
    return f"{fdate(x['date'])} · {x['name'] or x['type']}{score}"


choice = st.selectbox("Séance", rows, format_func=label)


@st.cache_data(show_spinner="Lecture du fichier FIT…")
def detail(label_id: str, computed_at: str | None):
    return service.session_detail(db, label_id, with_records=True)


an = db.analysis(choice["label_id"])
d = detail(choice["label_id"], an["computed_at"] if an else None)
m, v = d.get("metrics") or {}, d.get("verdict") or {}

st.header(v.get("headline") or choice["name"] or "Séance")
if d.get("planned"):
    st.caption("Prévu : " + " + ".join(f"{p['name']} ({p['summary']})" for p in d["planned"]))
else:
    st.caption("Séance hors plan.")

cv = d.get("coach_verdict")
if cv:
    with st.container(border=True):
        st.markdown("**Verdict du coach**" + (f" · {fnum(cv['score'])}/10" if cv.get("score") is not None else ""))
        st.markdown(cv["text"])
else:
    st.caption(f"Pas encore de verdict rédigé. Dans Claude Code : « juge ma séance du {fdate(choice['date'])} ».")

if v.get("findings"):
    st.subheader("Constats")
    for f in v["findings"]:
        st.markdown(f"- {f}")

if not m:
    st.warning("Pas de fichier FIT pour cette séance : seules les données résumées sont disponibles.")
    st.stop()

dec = (m.get("decoupling") or {}).get("decoupling_pct")
grid = [
    ("Distance", f"{fnum(m['distance_m'] / 1000, 2)} km", None),
    ("Temps en mouvement", fdur(m["moving_s"]), None),
    ("Allure moyenne", f"{fpace(m['avg_pace'])}/km", None),
    ("Allure ajustée (NGP)", f"{fpace(m['ngp_pace'])}/km", "Allure équivalente sur plat, lissée : tient compte du dénivelé et des variations."),
    ("FC moyenne", f"{fnum(m['avg_hr'], 0)} bpm", None),
    ("Charge (rTSS)", fnum(m["rtss"], 0), "100 = une heure à ton allure seuil."),
    ("TRIMP", fnum(m["trimp"], 0), "Charge cardiaque (Banister)."),
    ("Efficacité", fnum(m["ef"], 2), "Mètres par minute divisés par la FC : plus c'est haut, plus tu es économique."),
    ("Découplage", f"{fnum(dec, 1)} %" if dec is not None else "—", "Perte d'efficacité entre la 1re et la 2de moitié. Sous 5 % : endurance solide."),
    ("Cadence (pas/min)", fnum(m["cadence"], 0), None),
    ("Foulée", f"{fnum(m['stride_m'], 2)} m", None),
    ("Dénivelé +", f"{fnum(m['ascent_m'], 0)} m", None),
]
cols = st.columns(6)
for i, (k, val, h) in enumerate(grid):
    cols[i % 6].metric(k, val, help=h)

reps = v.get("reps")
if reps and reps.get("reps"):
    st.subheader("Répétitions")
    st.caption("Méthode : " + ("tours enregistrés par la montre" if reps.get("method") == "tour" else "détection dans les données"))
    t = []
    for i, r in enumerate(reps["reps"], 1):
        st_ = r["step"]
        done = r["done"] or {}
        t.append({"#": i, "Cible": f"{fpace(st_['pace_lo'])}–{fpace(st_['pace_hi'])}/km",
                  "Réalisé": f"{fpace(done.get('pace'))}/km" if done else "—",
                  "Écart (s/km)": round(r["delta_s"], 1) if r["delta_s"] is not None else None,
                  "Statut": r["status"], "FC moy.": round(done["avg_hr"]) if done.get("avg_hr") else None,
                  "Distance (m)": round(done["distance_m"]) if done.get("distance_m") else None})
    st.dataframe(pd.DataFrame(t), hide_index=True, width="stretch")

rec = d.get("records")
if rec is not None and len(rec):
    rec = rec.copy()
    rec["km"] = rec["distance"] / 1000
    moving = rec["speed"] > 1.2
    sm = rec["speed"].where(moving).rolling(20, min_periods=5, center=True).mean()
    rec["pace"] = (1000 / sm).where(sm > 1.2)
    c1, c2 = st.columns(2)
    fig = go.Figure(go.Scatter(x=rec["km"], y=rec["pace"], mode="lines", line=dict(color=BLUE, width=2), name="Allure",
                               hovertemplate="%{x:.2f} km<extra></extra>", customdata=rec["pace"].map(fpace)))
    fig.update_traces(hovertemplate="%{x:.2f} km · %{customdata}/km<extra></extra>")
    style(fig, 260, "pace")
    pace_ticks(fig, rec["pace"].dropna().quantile([0.02, 0.98]).tolist())
    fig.update_layout(title="Allure (min/km)", xaxis_title="km")
    c1.plotly_chart(fig, width="stretch")
    if rec["hr"].notna().any():
        fig = go.Figure(go.Scatter(x=rec["km"], y=rec["hr"], mode="lines", line=dict(color=ORANGE, width=2), name="FC",
                                   hovertemplate="%{x:.2f} km · %{y:.0f} bpm<extra></extra>"))
        a = service.athlete(db, s)
        for name, lo, hi in a.hr_zone_bounds()[1:]:
            fig.add_hline(y=lo, line=dict(color=MUTED, width=1, dash="dot"), annotation_text=name.split()[0],
                          annotation_position="top left", annotation_font_color=MUTED)
        style(fig, 260).update_layout(title="Fréquence cardiaque (bpm)", xaxis_title="km")
        c2.plotly_chart(fig, width="stretch")

zc1, zc2 = st.columns(2)
for col, key, title in ((zc1, "zones_hr", "Temps par zone de FC"), (zc2, "zones_pace", "Temps par zone d'allure")):
    z = m.get(key) or {}
    if z:
        fig = go.Figure(go.Bar(x=[v_ * 100 for v_ in z.values()], y=list(z.keys()), orientation="h", marker_color=BLUE,
                               hovertemplate="%{y} : %{x:.0f} %<extra></extra>", text=[f"{v_:.0%}" for v_ in z.values()],
                               textposition="outside"))
        style(fig, 220).update_layout(title=title, hovermode="closest", xaxis=dict(range=[0, 110], ticksuffix=" %"))
        fig.update_yaxes(autorange="reversed")
        col.plotly_chart(fig, width="stretch")

if d.get("laps"):
    st.subheader("Tours")
    laps = [{"#": i, "Distance (m)": round(l["distance_m"] or 0), "Temps": fdur(l.get("timer_s") or l.get("elapsed_s")),
             "Allure": fpace((l.get("timer_s") or l.get("elapsed_s") or 0) / (l["distance_m"] / 1000)) if l.get("distance_m") else "—",
             "FC moy.": l.get("avg_hr"), "FC max": l.get("max_hr")} for i, l in enumerate(d["laps"], 1)]
    st.dataframe(pd.DataFrame(laps), hide_index=True, width="stretch")

be = m.get("best_efforts") or {}
if be:
    st.subheader("Meilleurs efforts de la séance")
    names = {"400": "400 m", "1000": "1 km", "1609": "1 mile", "3000": "3 km", "5000": "5 km", "10000": "10 km", "21097": "Semi"}
    st.dataframe(pd.DataFrame([{"Distance": names.get(k, k), "Temps": fdur(t), "Allure": f"{fpace(t / (int(k) / 1000))}/km"}
                               for k, t in be.items()]), hide_index=True)
