import asyncio
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from coach import history as hist
from coach import service
from common import BLUE, MUTED, ORANGE, ctx, fdate, fdur, fnum, fpace, style, type_color

s, db = ctx()
today = date.today()
st.title("Historique")

sport = st.segmented_control("Sport", ["Course à pied", "Tous les sports"], default="Course à pied", key="h-sport") or "Course à pied"
df = hist.frame(db, "run" if sport == "Course à pied" else "all")
if df.empty:
    st.info("Aucune séance : lance `uv run coach history --days 3650`.")
    st.stop()
rec = hist.records(df)

c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
period = c1.segmented_control("Période", ["30 jours", "3 mois", "6 mois", "1 an", "2 ans", "Tout"], default="3 mois", key="h-period") or "3 mois"
if c2.button("Tout l'historique COROS", icon=":material/history:", width="stretch",
             help="Récupère les séances (résumés) et les nuits depuis l'ouverture du compte. Les fichiers FIT détaillés "
                  "arrivent ensuite au fil des synchronisations (COROS limite leur nombre par jour)."):
    from coach.sources.coros_mcp import describe
    from coach.sync import sync_history
    try:
        with st.spinner("Récupération de l'historique COROS…"):
            asyncio.run(sync_history(s, db, days=3650, log=lambda m: st.toast(m)))
        st.rerun()
    except Exception as e:  # noqa: BLE001
        st.error(f"Impossible : {describe(e)}")
days = {"30 jours": 30, "3 mois": 91, "6 mois": 182, "1 an": 365, "2 ans": 730}.get(period)
start = today - timedelta(days=days) if days else rec["first"]
cur, prev = hist.totals(df, start, today), hist.totals(df, *hist.previous(start, today))
st.caption(f"Du {fdate(start)} à aujourd'hui · compte COROS depuis le {fdate(rec['first'])} · "
           f"{fnum(rec['total_km'], 0)} km en {rec['total_sessions']} sorties au total")


def delta(a, b, unit="", dec=0):
    if not b:
        return None
    return f"{a - b:+.{dec}f}{unit} vs période précédente".replace(".", ",")


with st.container(horizontal=True):
    st.metric("Distance", f"{fnum(cur['km'], 0)} km", border=True, delta=delta(cur["km"], prev["km"], " km") if days else None)
    st.metric("Sorties", cur["sessions"], border=True, delta=delta(cur["sessions"], prev["sessions"]) if days else None)
    st.metric("Temps", f"{fnum(cur['hours'], 0)} h", border=True, delta=delta(cur["hours"], prev["hours"], " h") if days else None)
    st.metric("Par semaine", f"{fnum(cur['km_week'], 1)} km", border=True, delta=f"{fnum(cur['sessions_week'], 1)} sorties", delta_color="off")
    st.metric("Allure moyenne", f"{fpace(cur['pace'])}/km" if cur["pace"] else "—", border=True,
              help="Sorties sur route, piste et tapis seulement (temps total / distance) : trail et autres sports la fausseraient.")
    if cur["longest"]:
        lg = cur["longest"]
        st.metric("Plus longue de la période", f"{fnum(lg['distance_km'], 1)} km", border=True,
                  delta=f"{fdate(lg['date'].date())} · {fdur(lg['duration_s'])}", delta_color="off")

# ---- volume --------------------------------------------------------------------------------------------
w = hist.window(df, start, today)
freq = "W" if (today - start).days <= 400 else "M"
vol = hist.volume(w, freq)
fig = go.Figure()
order = sorted(vol.columns, key=lambda c: (c in ("Non analysée", "Trail"), c))
for cat in order:
    color = "#cbd5e1" if cat == "Non analysée" else "#0f766e" if cat == "Trail" else type_color(cat)
    fig.add_bar(x=vol.index, y=vol[cat], name=cat, marker_color=color, hovertemplate="%{y:.1f} km<extra>" + cat + "</extra>")
style(fig, 320).update_layout(barmode="stack", title=f"Kilomètres par {'semaine' if freq == 'W' else 'mois'}, par type de séance",
                              hovermode="x unified")
st.plotly_chart(fig, width="stretch")
st.caption("« Non analysée » : séance sans fichier FIT détaillé pour l'instant (ils arrivent au fil des synchronisations).")

if sport == "Tous les sports" and len(w):
    hrs = w.assign(period=w["date"].dt.to_period(freq).dt.start_time).pivot_table(
        index="period", columns="sport", values="hours", aggfunc="sum", fill_value=0)
    palette = ["#2e6fdb", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444", "#06b6d4", "#84cc16", "#ec4899", "#64748b"]
    fig = go.Figure()
    for i, col in enumerate(sorted(hrs.columns, key=lambda c: (c != "Course à pied", c))):
        fig.add_bar(x=hrs.index, y=hrs[col], name=col, marker_color=palette[i % len(palette)],
                    hovertemplate="%{y:.1f} h<extra>" + col + "</extra>")
    style(fig, 300).update_layout(barmode="stack", title=f"Heures par {'semaine' if freq == 'W' else 'mois'}, par sport", hovermode="x unified")
    st.plotly_chart(fig, width="stretch")
    by_sport = w.groupby("sport").agg(n=("label_id", "count"), h=("hours", "sum"), km=("distance_km", "sum"), kcal=("calories", "sum"))
    st.dataframe(pd.DataFrame({"Sport": by_sport.index, "Séances": by_sport["n"].values, "Heures": by_sport["h"].round(1).values,
                               "Km": by_sport["km"].round(0).values, "Calories": by_sport["kcal"].round(0).values}),
                 hide_index=True, width="stretch")

# ---- pace & distance per run over the period -----------------------------------------------------------
if len(w) and sport == "Course à pied":
    fig = go.Figure(go.Scatter(x=w["date"], y=w["avg_pace"], mode="markers", marker=dict(size=(w["distance_km"].clip(3, 45) * 0.6 + 4),
                    color=[type_color(c) if c not in ("Non analysée", "Trail") else "#94a3b8" for c in w["category"]], opacity=0.8),
                    customdata=list(zip(w["distance_km"].round(1), w["avg_pace"].map(fpace), w["category"])),
                    hovertemplate="%{x|%d %b %Y} · %{customdata[0]} km à %{customdata[1]}/km<br>%{customdata[2]}<extra></extra>"))
    style(fig, 300, "pace").update_layout(title="Allure moyenne de chaque sortie (taille = distance)", hovermode="closest")
    from common import pace_ticks
    pace_ticks(fig, w["avg_pace"].dropna().quantile([0.02, 0.98]).tolist())
    st.plotly_chart(fig, width="stretch")

# ---- all-time -----------------------------------------------------------------------------------------
st.subheader("Depuis le début", divider="gray")
c1, c2 = st.columns([3, 2])
yr = hist.per_year(df)
fig = go.Figure(go.Bar(x=yr["year"].astype(str), y=yr["km"], marker_color=BLUE, text=yr["km"].map(lambda v: f"{v:.0f} km"),
                       textposition="outside", hovertemplate="%{x} : %{y:.0f} km<extra></extra>"))
style(fig, 280).update_layout(title="Kilomètres par année", showlegend=False, hovermode="closest",
                              yaxis=dict(range=[0, yr["km"].max() * 1.2]))
c1.plotly_chart(fig, width="stretch")
c2.dataframe(pd.DataFrame({"Année": yr["year"].astype(str), "Km": yr["km"].round(0), "Sorties": yr["sessions"],
                           "Heures": yr["hours"].round(0), "Plus longue": yr["longest"].map(lambda v: f"{v:.1f} km"),
                           "Allure (route)": yr["pace"].map(lambda v: f"{fpace(v)}/km" if v == v and v else "—")}), hide_index=True, width="stretch")

lg = rec["longest"]
with st.container(horizontal=True):
    st.metric("Plus longue sortie (depuis le début)", f"{fnum(lg['distance_km'], 1)} km", border=True,
              delta=f"{fdate(lg['date'].date())} · {fdur(lg['duration_s'])}", delta_color="off")
    st.metric("Plus grosse semaine", f"{fnum(rec['best_week'][1], 0)} km", border=True,
              delta=f"semaine du {fdate(rec['best_week'][0])}", delta_color="off")
    st.metric("Plus gros mois", f"{fnum(rec['best_month'][1], 0)} km", border=True,
              delta=rec["best_month"][0].strftime("%m/%Y"), delta_color="off")

recs, n_fit, n_runs = hist.personal_records(db)
if recs:
    st.markdown("**Records personnels** — meilleur temps sur chaque distance, n'importe où dans une sortie")
    st.dataframe(pd.DataFrame([{"Distance": r_["distance"], "Temps": fdur(r_["time"]), "Allure": f"{fpace(r_['time'] / (r_['meters'] / 1000))}/km",
                                "Date": fdate(r_["date"]), "Pendant": f"{r_['name'] or ''} ({fnum(r_['run_km'], 1)} km)"} for r_ in recs]),
                 hide_index=True, width="stretch")
    st.caption(f"Calculés sur les {n_fit} sorties dont le fichier FIT détaillé est déjà téléchargé (sur {n_runs}) ; le reste arrive "
               "au fil des synchronisations. Trail exclu (les descentes fausseraient les records).")

# ---- map of every route --------------------------------------------------------------------------------
st.subheader("Carte de tes sorties", divider="gray")
ans = db.analyses()
tracks = []
for _, r_ in w.iterrows():
    tr = ((ans.get(r_["label_id"]) or {}).get("metrics") or {}).get("track") or []
    if len(tr) > 5:
        tracks.append((r_, tr))
if not tracks:
    st.caption("Pas de tracé GPS sur la période.")
else:
    import math
    tab_routes, tab_heat = st.tabs([":material/route: Parcours", ":material/local_fire_department: Carte de chaleur"])
    lats = [p_[0] for _, tr in tracks for p_ in tr]
    lons = [p_[1] for _, tr in tracks for p_ in tr]
    # centre on where most runs start (a single trip far away shouldn't zoom the map out to half of Europe)
    starts = pd.DataFrame([(tr[0][0], tr[0][1]) for _, tr in tracks], columns=["lat", "lon"])
    c_lat, c_lon = starts["lat"].median(), starts["lon"].median()
    near = [(la, lo) for la, lo in zip(lats, lons) if abs(la - c_lat) < 0.3 and abs(lo - c_lon) < 0.4]
    span = max(max(p_[0] for p_ in near) - min(p_[0] for p_ in near), (max(p_[1] for p_ in near) - min(p_[1] for p_ in near)) * 0.7, 0.01) if near else 0.2
    zoom = max(3, min(15, math.log2(360 / span) - 1.3))
    palette = {"Course à pied": "#dc2626", "Randonnée": "#16a34a", "Vélo": "#2563eb", "VTT": "#7c3aed"}
    with tab_routes:
        fig = go.Figure()
        for sport_ in sorted({r_["sport"] for r_, _ in tracks}, key=lambda x: x != "Course à pied"):
            la, lo, tx = [], [], []
            for r_, tr in tracks:
                if r_["sport"] != sport_:
                    continue
                la += [p_[0] for p_ in tr] + [None]
                lo += [p_[1] for p_ in tr] + [None]
                label = f"{fdate(r_['date'].date())} · {r_.get('headline') or r_['name']}"
                tx += [label] * len(tr) + [None]
            fig.add_trace(go.Scattermap(lat=la, lon=lo, mode="lines", name=sport_, line=dict(width=2.5, color=palette.get(sport_, "#64748b")),
                                        opacity=0.55, hovertext=tx, hoverinfo="text"))
        fig.update_layout(map=dict(style="open-street-map", center=dict(lat=c_lat, lon=c_lon), zoom=zoom), height=560,
                          margin=dict(l=0, r=0, t=0, b=0), legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.8)"))
        st.plotly_chart(fig, width="stretch")
        st.caption(f"{len(tracks)} tracés sur la période. Zoome ou déplace la carte pour voir les sorties ailleurs.")
    with tab_heat:
        fig = go.Figure(go.Densitymap(lat=lats, lon=lons, radius=6, colorscale="YlOrRd", showscale=False, opacity=0.8))
        fig.update_layout(map=dict(style="open-street-map", center=dict(lat=c_lat, lon=c_lon), zoom=zoom), height=560,
                          margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig, width="stretch")
        st.caption("Plus c'est rouge, plus tu passes souvent par là.")
