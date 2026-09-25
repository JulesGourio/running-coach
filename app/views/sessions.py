import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from coach import service
from coach.verdict import hard_segments
from common import BLUE, ORANGE, ZONE_COLORS, ctx, fdate, fdur, fnum, fpace, pace_ticks, style, tint, type_badge

s, db = ctx()
st.title("Séances")

c1, c2, c3 = st.columns([1.2, 2, 5])
period = c1.selectbox("Période", ["3 mois", "6 mois", "1 an", "Tout"], key="s-period")
rows = service.sessions(db, {"3 mois": 91, "6 mois": 182, "1 an": 365}.get(period, 3650))
if not rows:
    st.info("Aucune séance synchronisée.")
    st.stop()
cats = sorted({x["kind_fr"] or "Non analysée" for x in rows})
cat = c2.selectbox("Type", ["Tous", *cats], key="s-cat")
rows = [x for x in rows if cat == "Tous" or (x["kind_fr"] or "Non analysée") == cat]


def label(x):
    return f"{fdate(x['date'])} · {x['headline'] or x['name'] or x['type']}"


choice = c3.selectbox("Séance", rows, format_func=label)


@st.cache_data(show_spinner="Lecture du fichier FIT…")
def detail(label_id: str, computed_at: str | None):
    return service.session_detail(db, label_id, with_records=True)


an = db.analysis(choice["label_id"])
d = detail(choice["label_id"], an["computed_at"] if an else None)
m, v = d.get("metrics") or {}, d.get("verdict") or {}

st.header(v.get("structure") or choice["name"] or "Séance")
st.markdown(f"{type_badge(v.get('type_fr'))} {fdate(choice['date'])} · :gray[{choice['name'] or ''}]")
if d.get("planned"):
    plan_txt = " + ".join(f"{p['name']} ({p['summary']})" for p in d["planned"])
    st.caption(f"Prévu : {plan_txt}" + (f" · respect du plan **{fnum(v['score'])}/10**" if v.get("score") is not None else ""))
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
easy_pct = sum((m.get("zones_hr") or {}).get(k_, 0) for k_ in ("Z1 récup", "Z2 endurance")) if m.get("zones_hr") else None
grid = [
    ("Distance", f"{fnum(m['distance_m'] / 1000, 2)} km", None),
    ("Temps en mouvement", fdur(m["moving_s"]), None),
    ("Allure moyenne", f"{fpace(m['avg_pace'])}/km", None),
    ("FC moyenne", f"{fnum(m['avg_hr'], 0)} bpm", None),
    ("FC max", f"{fnum(m.get('max_hr'), 0)} bpm", None),
    ("Temps en endurance", f"{easy_pct:.0%}" if easy_pct is not None else "—", "Part du temps en zones 1 et 2 (FC)."),
    ("Dénivelé +", f"{fnum(m['ascent_m'], 0)} m", None),
    ("Cadence", f"{fnum(m['cadence'], 0)} pas/min", None),
    ("Foulée", f"{fnum(m['stride_m'], 2)} m", None),
    ("Dérive cardiaque", f"{fnum(dec, 1)} %" if dec is not None else "—",
     "Hausse de la FC à allure égale entre la 1re et la 2de moitié. Sous 5 % : endurance solide."),
    ("Charge", fnum(m["rtss"], 0), "Intensité × durée : 100 = une heure courue à ton allure seuil."),
]
cols = st.columns(6)
for i, (k, val, h) in enumerate(grid):
    cols[i % 6].metric(k, val, help=h, border=True)

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

segments = v.get("segments")
if segments:
    st.subheader("Répétitions")
    st.caption("D'après les tours de ta montre (mêmes valeurs que l'app COROS)." if segments[0].get("source") == "tour"
               else "Détectées dans les données GPS (pas de tours enregistrés) : isolées de la récupération, "
                    "au cœur de chaque effort.")
    t = [{"#": sg["n"], "Distance (m)": round(sg["distance_m"]) if sg.get("distance_m") else None,
          "Durée": fdur(sg["duration_s"]), "Allure": f"{fpace(sg['pace'])}/km" if sg.get("pace") else "—",
          "FC moy.": round(sg["avg_hr"]) if sg.get("avg_hr") else None} for sg in segments]
    st.dataframe(pd.DataFrame(t), hide_index=True, width="stretch")

rec = d.get("records")
if rec is not None and len(rec):
    rec = rec.copy()
    rec["km"] = rec["distance"] / 1000
    moving = rec["speed"] > 1.2
    sm = rec["speed"].where(moving).rolling(20, min_periods=5, center=True).mean()
    rec["pace"] = (1000 / sm).where(sm > 1.2)
    a = service.athlete(db, s)
    reps_idx = [sg for sg in hard_segments(m, a) if sg["end_idx"] < len(rec)]

    # Pace, with each detected rep shaded and the threshold pace as a reference line.
    fig = go.Figure()
    for sg in reps_idx:
        fig.add_vrect(x0=rec["km"].iloc[sg["start_idx"]], x1=rec["km"].iloc[sg["end_idx"]],
                      fillcolor=tint(ORANGE, 0.16), line_width=0, layer="below")
    fig.add_scatter(x=rec["km"], y=rec["pace"], mode="lines", line=dict(color=BLUE, width=2), name="Allure",
                    customdata=rec["pace"].map(fpace), hovertemplate="%{x:.2f} km · %{customdata}/km<extra></extra>")
    fig.add_hline(y=a.threshold_pace, line=dict(color=ZONE_COLORS["Z4 seuil"], width=1.5, dash="dash"),
                  annotation_text=f"seuil {fpace(a.threshold_pace)}", annotation_position="top right",
                  annotation_font_color=ZONE_COLORS["Z4 seuil"])
    style(fig, 300, "pace")
    pace_ticks(fig, rec["pace"].dropna().quantile([0.02, 0.98]).tolist() + [a.threshold_pace])
    fig.update_layout(title="Allure (min/km)" + (" — répétitions surlignées" if reps_idx else ""), xaxis_title="km",
                      showlegend=False)
    st.plotly_chart(fig, width="stretch")

    if rec["hr"].notna().any():
        # Skip the first minute (sensor/HR cold start, often ~100 bpm on a run that's really 150+) so it
        # doesn't stretch the axis; the zones are drawn as colored bands instead of thin lines.
        warmed = rec[rec["elapsed"] >= 60] if (rec["elapsed"] >= 60).any() else rec
        hr_vals = warmed["hr"].dropna()
        lo_v, hi_v = (hr_vals.quantile(0.02), hr_vals.quantile(0.98)) if len(hr_vals) else (100, 200)
        pad = max(4.0, (hi_v - lo_v) * 0.15)
        y0, y1 = lo_v - pad, hi_v + pad
        fig = go.Figure()
        for name, lo, hi in a.hr_zone_bounds():
            b0, b1 = max(lo, y0), min(hi, y1)
            if b1 <= b0:
                continue
            fig.add_hrect(y0=b0, y1=b1, fillcolor=tint(ZONE_COLORS[name], 0.13), line_width=0, layer="below",
                          annotation_text=f"{name}", annotation_position="right",
                          annotation_font=dict(color=ZONE_COLORS[name], size=11))
        fig.add_scatter(x=warmed["km"], y=warmed["hr"], mode="lines", line=dict(color="#111827", width=1.8), name="FC",
                        hovertemplate="%{x:.2f} km · %{y:.0f} bpm<extra></extra>")
        style(fig, 300).update_layout(title="Fréquence cardiaque (bpm) et zones", xaxis_title="km", showlegend=False,
                                      margin=dict(r=90))
        fig.update_yaxes(range=[y0, y1])
        st.plotly_chart(fig, width="stretch")
        st.caption("1re minute masquée (montée en régime du capteur) pour garder une échelle lisible.")

zc1, zc2 = st.columns(2)
for col, key, title in ((zc1, "zones_hr", "Temps par zone de FC"), (zc2, "zones_pace", "Temps par zone d'allure")):
    z = m.get(key) or {}
    if z:
        fig = go.Figure(go.Bar(x=[v_ * 100 for v_ in z.values()], y=list(z.keys()), orientation="h",
                               marker_color=[ZONE_COLORS.get(k_, BLUE) for k_ in z],
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

# ---- same kind of session, since the start of the account ---------------------------------------------
kind = v.get("type_fr")
if kind:
    a_ = service.athlete(db, s)
    ans = db.analyses()
    same = []
    for x in service.sessions(db, 3650):
        if x["kind_fr"] != kind:
            continue
        mx = (ans.get(x["label_id"]) or {}).get("metrics") or {}
        reps = [g["avg_pace"] for g in hard_segments(mx, a_) if g["duration_s"] >= 40]
        same.append({"date": x["date"], "structure": x.get("structure") or "", "km": x["distance_km"],
                     "pace": x["avg_pace"], "hr": x["avg_hr"], "rep_med": float(pd.Series(reps).median()) if reps else None,
                     "rep_best": min(reps) if reps else None, "current": x["label_id"] == choice["label_id"]})
    if len(same) > 1:
        st.subheader(f"Tes séances « {kind} » ({len(same)})", divider="gray")
        sd = pd.DataFrame(same).sort_values("date")
        y = sd["rep_med"] if sd["rep_med"].notna().sum() >= 2 else sd["pace"]
        what = "allure médiane des répétitions" if y is sd["rep_med"] else "allure moyenne"
        fig = go.Figure(go.Scatter(x=pd.to_datetime(sd["date"]), y=y, mode="lines+markers", line=dict(color=BLUE, width=1.5),
                                   marker=dict(size=[14 if c else 8 for c in sd["current"]], color=[ORANGE if c else BLUE for c in sd["current"]]),
                                   customdata=list(zip(y.map(fpace), sd["structure"], sd["hr"].fillna(0).round(0))),
                                   hovertemplate="%{x|%d %b %Y} · %{customdata[1]}<br>%{customdata[0]}/km · FC %{customdata[2]}<extra></extra>"))
        style(fig, 260, "pace").update_layout(title=f"{what.capitalize()}, séance après séance (en orange : celle-ci)", hovermode="closest")
        pace_ticks(fig, y.dropna().tolist())
        st.plotly_chart(fig, width="stretch")
        st.dataframe(pd.DataFrame([{"Date": fdate(r_["date"]), "Contenu": r_["structure"], "Km": r_["km"],
                                    "Allure moy.": f"{fpace(r_['pace'])}/km" if r_["pace"] else "—",
                                    "Répétitions (médiane)": f"{fpace(r_['rep_med'])}/km" if r_["rep_med"] else "—",
                                    "Meilleure répétition": f"{fpace(r_['rep_best'])}/km" if r_["rep_best"] else "—",
                                    "FC moy.": round(r_["hr"]) if r_["hr"] == r_["hr"] and r_["hr"] else None}
                                   for r_ in sorted(same, key=lambda r_: r_["date"], reverse=True)]),
                     hide_index=True, width="stretch", column_config={"Km": st.column_config.NumberColumn(format="%.1f")})
