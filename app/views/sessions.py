import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from coach import service
from coach.verdict import hard_segments
from common import (BLUE, ORANGE, ZONE_COLORS, ctx, elevation_fig, fdate, fdur, fnum, fpace, pace_ticks, route_map, style, tint,
                    type_badge)

s, db = ctx()
st.title("Séances")

RUN = (100, 101, 102, 103, None)
c0, c1, c2, c3 = st.columns([1.4, 1.1, 1.8, 5])
sport = c0.selectbox("Sport", ["Course à pied", "Autres sports", "Tous"], key="s-sport")
period = c1.selectbox("Période", ["3 mois", "6 mois", "1 an", "Tout"], key="s-period")
rows = service.sessions(db, {"3 mois": 91, "6 mois": 182, "1 an": 365}.get(period, 3650),
                        sports={"Course à pied": "run", "Autres sports": "other"}.get(sport, "all"))
if not rows:
    st.info("Aucune séance sur la période.")
    st.stop()


def cat_of(x):
    return x["kind_fr"] or ("Non analysée" if x.get("sport_type") in RUN else x["type"])


cats = sorted({cat_of(x) for x in rows})
cat = c2.selectbox("Type", ["Tous", *cats], key="s-cat")
rows = [x for x in rows if cat == "Tous" or cat_of(x) == cat]


def label(x):
    return f"{fdate(x['date'])} · {x['headline'] or x['name'] or x['type']}"


choice = c3.selectbox("Séance", rows, format_func=label)


@st.cache_data(show_spinner="Lecture du fichier FIT…")
def detail(label_id: str, computed_at: str | None):
    return service.session_detail(db, label_id, with_records=True)


an = db.analysis(choice["label_id"])
d = detail(choice["label_id"], an["computed_at"] if an else None)
m, v = d.get("metrics") or {}, d.get("verdict") or {}
is_run = choice.get("sport_type") in RUN

st.header(v.get("structure") or choice["name"] or "Séance")
st.markdown(f"{type_badge(v.get('type_fr') or choice['type'])} {fdate(choice['date'])} · :gray[{choice['name'] or ''}]")
if not is_run:
    pass
elif d.get("planned"):
    plan_txt = " + ".join(f"{p['name']} ({p['summary']})" for p in d["planned"])
    st.caption(f"Prévu : {plan_txt}" + (f" · respect du plan **{fnum(v['score'])}/10**" if v.get("score") is not None else ""))
else:
    st.caption("Séance hors plan.")

cv = d.get("coach_verdict")
if cv:
    with st.container(border=True):
        st.markdown("**Verdict du coach**" + (f" · {fnum(cv['score'])}/10" if cv.get("score") is not None else ""))
        st.markdown(cv["text"])
elif is_run:
    st.caption(f"Pas encore de verdict rédigé. Dans Claude Code : « juge ma séance du {fdate(choice['date'])} ».")

if v.get("findings"):
    st.subheader("Constats")
    for f in v["findings"]:
        st.markdown(f"- {f}")

if not m:
    st.info("Fichier FIT détaillé pas encore téléchargé : il arrive à la prochaine synchronisation. En attendant, le résumé COROS :",
            icon=":material/downloading:")
    with st.container(horizontal=True):
        st.metric("Distance", f"{fnum(choice['distance_km'], 2)} km", border=True)
        st.metric("Durée", fdur(choice["duration_s"]), border=True)
        if choice.get("avg_pace") and is_run:
            st.metric("Allure", f"{fpace(choice['avg_pace'])}/km", border=True)
        if choice.get("avg_hr"):
            st.metric("FC moyenne", f"{choice['avg_hr']:.0f} bpm", border=True)
        if choice.get("calories"):
            st.metric("Calories", f"{choice['calories']:.0f} kcal", border=True)
    st.stop()

dec = (m.get("decoupling") or {}).get("decoupling_pct")
easy_pct = sum((m.get("zones_hr") or {}).get(k_, 0) for k_ in ("Z1 récup", "Z2 endurance")) if m.get("zones_hr") else None
km = m["distance_m"] / 1000
up, down = m.get("ascent_m") or 0, m.get("descent_m") or 0
hilly = choice.get("sport_type") in (102, 104, 204) or (km > 0 and up / km >= 15)
stopped = (m.get("elapsed_s") or 0) - (m.get("moving_s") or 0)
H_EFFORT = ("Allure équivalente sur le plat pour le même effort : les montées la rendent plus rapide que l'allure réelle, "
            "les descentes raides plus lente. Sert à comparer une sortie vallonnée à une sortie plate.")
H_KME = "Kilomètres-effort : distance + D+ / 100 (100 m de montée ≈ 1 km à plat). La mesure usuelle de la taille d'un trail."
H_VERT = "Mètres de dénivelé gagnés par heure passée à monter (pente > 5 %)."
H_MOVE = "Temps pendant lequel tu avançais, marche comprise, sans les arrêts."
if is_run:
    grid = [
        ("Distance", f"{fnum(km, 2)} km", None),
        ("Temps en mouvement", fdur(m["moving_s"]), H_MOVE + (f" Arrêts : {fdur(stopped)}." if stopped > 60 else "")),
        ("Allure moyenne", f"{fpace(m['avg_pace'])}/km", "Distance / temps en mouvement."),
        ("FC moyenne", f"{fnum(m['avg_hr'], 0)} bpm", None),
        ("FC max", f"{fnum(m.get('max_hr'), 0)} bpm", None),
        ("Temps en endurance", f"{easy_pct:.0%}" if easy_pct is not None else "—", "Part du temps en zones 1 et 2 (FC)."),
        ("Dénivelé", f"+{fnum(up, 0)} / -{fnum(down, 0)} m", None),
    ]
    if hilly:
        grid += [("Allure d'effort", f"{fpace(m.get('effort_pace'))}/km" if m.get("effort_pace") else "—", H_EFFORT),
                 ("Km-effort", fnum(km + up / 100, 1), H_KME),
                 ("Vitesse ascensionnelle", f"{fnum(m.get('climb_rate'), 0)} m/h" if m.get("climb_rate") else "—", H_VERT)]
    grid += [
        ("Cadence", f"{fnum(m['cadence'], 0)} pas/min", None),
        *([] if hilly else [("Dérive cardiaque", f"{fnum(dec, 1)} %" if dec is not None else "—",
                              "Hausse de la FC à allure égale entre la 1re et la 2de moitié. Sous 5 % : endurance solide.")]),
        ("Charge", fnum(m.get("load"), 0), "Intensité × durée : 100 = une heure courue à ton allure seuil."),
    ]
else:
    spd = m["distance_m"] / m["moving_s"] * 3.6 if m.get("moving_s") else None
    grid = [("Distance", f"{fnum(km, 2)} km", None),
            ("Temps en mouvement", fdur(m["moving_s"]), H_MOVE),
            ("Durée totale", fdur(m.get("elapsed_s")), f"Arrêts et pauses : {fdur(stopped)}." if stopped > 60 else None),
            ("Vitesse en mouvement", f"{fnum(spd, 1)} km/h" if spd else "—", None),
            ("Dénivelé", f"+{fnum(up, 0)} / -{fnum(down, 0)} m", None)]
    if hilly:
        grid += [("Km-effort", fnum(km + up / 100, 1), H_KME),
                 ("Vitesse ascensionnelle", f"{fnum(m.get('climb_rate'), 0)} m/h" if m.get("climb_rate") else "—", H_VERT)]
    grid += [("FC moyenne", f"{fnum(m['avg_hr'], 0)} bpm", None), ("FC max", f"{fnum(m.get('max_hr'), 0)} bpm", None),
             ("Calories", f"{choice['calories']:.0f} kcal" if choice.get("calories") else "—", None)]
ncol = 6 if len(grid) > 10 else 5
for i in range(0, len(grid), ncol):
    for c_, (k, val, h) in zip(st.columns(ncol), grid[i:i + ncol]):
        c_.metric(k, val, help=h, border=True)

# ---- map and elevation ----------------------------------------------------------------------------------
rec0 = d.get("records")
if rec0 is not None and len(rec0) and rec0["lat"].notna().sum() > 10:
    g = rec0.dropna(subset=["lat", "lon"])
    g = g.iloc[:: max(1, len(g) // 1500)]
    spd_s = g["speed"].rolling(15, min_periods=3, center=True).mean()
    if is_run:
        col_vals = (1000 / spd_s.where(spd_s > 1.2)).clip(lower=150, upper=600)
        hover = [f"{d_ / 1000:.2f} km · {fpace(p_)}/km" if p_ == p_ else f"{d_ / 1000:.2f} km"
                 for d_, p_ in zip(g["distance"].fillna(0), col_vals)]
        fig = route_map(g["lat"], g["lon"], col_vals.fillna(col_vals.median()), "allure", hover)
        lo_, hi_ = col_vals.quantile(0.05), col_vals.quantile(0.95)
        ticks = list(range(int(lo_ // 15 * 15), int(hi_) + 15, 15 if hi_ - lo_ < 90 else 30))
        fig.update_traces(selector=dict(mode="markers"), marker=dict(cmin=lo_, cmax=hi_, colorbar=dict(
            title="allure", tickvals=ticks, ticktext=[fpace(v_) for v_ in ticks])))
    else:
        col_vals = (spd_s * 3.6).fillna(0)
        hover = [f"{d_ / 1000:.2f} km · {v_:.1f} km/h" for d_, v_ in zip(g["distance"].fillna(0), col_vals)]
        fig = route_map(g["lat"], g["lon"], col_vals, "km/h", hover, reverse=True)
    mc1, mc2 = st.columns([3, 2])
    mc1.plotly_chart(fig, width="stretch")
    mc1.caption("Couleur : " + ("allure (rouge = rapide, bleu = lent)." if is_run else "vitesse (bleu = rapide)."))
    alt = g.dropna(subset=["altitude"])
    if len(alt) > 10:
        mc2.plotly_chart(elevation_fig(alt["distance"] / 1000, alt["altitude"], height=300), width="stretch")
        mc2.caption(f"D+ {fnum(m.get('ascent_m'), 0)} m · point haut {alt['altitude'].max():.0f} m · point bas {alt['altitude'].min():.0f} m")

# ---- terrain: altitude with pace/effort pace, pace by slope, km splits ---------------------------------------
splits = m.get("splits") or []
if rec0 is not None and len(rec0) and hilly and rec0["altitude"].notna().sum() > 30:
    st.subheader("Relief et effort", divider="gray")
    r_ = rec0.dropna(subset=["distance"])
    alt_s = r_["altitude"].interpolate(limit_direction="both").rolling(15, center=True, min_periods=1).mean()
    step = max(1, len(r_) // 1500)
    fig = go.Figure()
    fig.add_scatter(x=r_["distance"][::step] / 1000, y=alt_s[::step], mode="lines", fill="tozeroy", name="Altitude", yaxis="y2",
                    line=dict(color="#0d9488", width=1.5), fillcolor="rgba(13,148,136,0.15)",
                    hovertemplate="%{y:.0f} m<extra>altitude</extra>")
    if is_run and splits:
        xs = [sp_["km"] - 0.5 for sp_ in splits]
        eff = [sp_.get("effort_pace") for sp_ in splits]
        fig.add_scatter(x=xs, y=[sp_["pace"] for sp_ in splits], mode="lines+markers", name="Allure réelle",
                        line=dict(color=BLUE, width=2.5), customdata=[fpace(sp_["pace"]) for sp_ in splits],
                        hovertemplate="%{customdata}/km<extra>allure réelle</extra>")
        fig.add_scatter(x=xs, y=eff, mode="lines+markers", name="Allure d'effort (équivalent plat)",
                        line=dict(color=ORANGE, width=2, dash="dot"), customdata=[fpace(e) for e in eff],
                        hovertemplate="%{customdata}/km<extra>allure d'effort</extra>")
        style(fig, 340, "pace").update_layout(title="Allure par km sur le profil", xaxis_title="km")
        pace_ticks(fig, [sp_["pace"] for sp_ in splits] + [e for e in eff if e])  # per-km values: no GPS spikes to trim
    elif splits:
        v_km = [3600 / sp_["pace"] for sp_ in splits]
        fig.add_scatter(x=[sp_["km"] - 0.5 for sp_ in splits], y=v_km, mode="lines+markers", name="Vitesse en mouvement",
                        line=dict(color=BLUE, width=2.5),
                        customdata=list(zip([round(sp_["up"]) for sp_ in splits], [round(sp_["down"]) for sp_ in splits])),
                        hovertemplate="%{y:.1f} km/h · D+ %{customdata[0]} m · D- %{customdata[1]} m<extra></extra>")
        style(fig, 340).update_layout(title="Vitesse par km sur le profil", xaxis_title="km")
        fig.update_yaxes(range=[0, max(6.0, max(v_km) * 1.15)], ticksuffix=" km/h")
    span = float(alt_s.max() - alt_s.min()) or 10.0
    fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, ticksuffix=" m",
                                  range=[alt_s.min() - span * 0.05, alt_s.max() + span * 0.9]))
    st.plotly_chart(fig, width="stretch")

    gb = m.get("grade_bins") or []
    if len(gb) >= 2:
        c1, c2 = st.columns(2)
        if is_run:
            txt = [f"{fpace(1000 / g_['speed'])}/km · {g_['share']:.0%}" if g_["speed"] > 0.3 else "" for g_ in gb]
        else:
            txt = [f"{fnum(g_['speed'] * 3.6, 1)} km/h · {g_['share']:.0%}" for g_ in gb]
        colors = ["#2e6fdb" if g_["name"].startswith(("<", "-")) else "#64748b" if g_["name"] == "plat" else "#dc2626" for g_ in gb]
        fig = go.Figure(go.Bar(y=[g_["name"] for g_ in gb], x=[g_["share"] * 100 for g_ in gb], orientation="h", marker_color=colors,
                               text=txt, textposition="auto", hovertemplate="%{y} : %{text}<extra></extra>"))
        style(fig, 300).update_layout(title=("Allure" if is_run else "Vitesse") + " selon la pente (barre = part du temps)",
                                      hovermode="closest", xaxis=dict(ticksuffix=" %"))
        c1.plotly_chart(fig, width="stretch")
        ups = [g_ for g_ in gb if g_["name"][0].isdigit() or g_["name"].startswith(">")]
        if ups:
            fig = go.Figure(go.Bar(x=[g_["name"] for g_ in ups], y=[g_["vert_m_h"] for g_ in ups], marker_color="#dc2626",
                                   text=[f"{g_['vert_m_h']:.0f} m/h" for g_ in ups], textposition="outside"))
            style(fig, 300).update_layout(title="Vitesse ascensionnelle selon la pente", hovermode="closest",
                                          yaxis=dict(range=[0, max(g_["vert_m_h"] for g_ in ups) * 1.25], ticksuffix=" m/h"))
            c2.plotly_chart(fig, width="stretch")
            c2.caption("Repères : 400-600 m/h en randonnée, 700-1000 m/h en trail soutenu.")

if len(splits) >= 2:
    with st.expander(f"Kilomètre par kilomètre ({len(splits)})", expanded=hilly, icon=":material/table_rows:"):
        st.dataframe(pd.DataFrame([{
            "Km": sp_["km"], "Temps": fdur(sp_["time_s"]),
            ("Allure" if is_run else "Vitesse"): f"{fpace(sp_['pace'])}/km" if is_run else f"{fnum(3600 / sp_['pace'], 1)} km/h",
            **({"Allure d'effort": f"{fpace(sp_['effort_pace'])}/km" if sp_.get("effort_pace") else "—"} if is_run and hilly else {}),
            "D+": round(sp_["up"]), "D-": round(sp_["down"]), "Pente": f"{sp_['grade'] * 100:+.0f} %".replace("+0 %", "0 %"),
            "FC": round(sp_["hr"]) if sp_.get("hr") else None} for sp_ in splits]), hide_index=True, width="stretch")

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
if rec is not None and len(rec) and is_run:
    rec = rec.copy()
    rec["km"] = rec["distance"] / 1000
    moving = rec["speed"] > 0.8
    sm = rec["speed"].where(moving).rolling(20, min_periods=5, center=True).mean()
    rec["pace"] = (1000 / sm).where(sm > 1.2)
    a = service.athlete(db, s)
    quality = (v.get("type_fr") or "").startswith(("VMA", "Seuil", "Allure", "Tempo", "Fartlek", "Côtes", "Course", "Sortie longue avec"))
    reps_idx = [sg for sg in hard_segments(m, a) if sg["end_idx"] < len(rec)] if quality else []

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

if not is_run and rec is not None and len(rec) and rec["hr"].notna().any():
    fig = go.Figure(go.Scatter(x=rec["distance"] / 1000, y=rec["hr"], mode="lines", line=dict(color="#111827", width=1.5),
                               hovertemplate="%{x:.2f} km · %{y:.0f} bpm<extra></extra>"))
    style(fig, 260).update_layout(title="Fréquence cardiaque (bpm)", xaxis_title="km", showlegend=False)
    st.plotly_chart(fig, width="stretch")

zc1, zc2 = st.columns(2)
for col, key, title in ((zc1, "zones_hr", "Temps par zone de FC"), (zc2, "zones_pace", "Temps par zone d'allure")):
    if key == "zones_pace" and not is_run:
        continue
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

be = (m.get("best_efforts") or {}) if is_run else {}
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
    for x in service.sessions(db, 3650, sports="all"):
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
