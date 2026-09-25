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
    st.metric("Allure moyenne", f"{fpace(cur['pace'])}/km" if cur["pace"] else "—", border=True)
    if cur["longest"]:
        lg = cur["longest"]
        st.metric("Plus longue", f"{fnum(lg['distance_km'], 1)} km", border=True,
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
                           "Allure": yr["pace"].map(lambda v: f"{fpace(v)}/km")}), hide_index=True, width="stretch")

lg = rec["longest"]
with st.container(horizontal=True):
    st.metric("Plus longue sortie", f"{fnum(lg['distance_km'], 1)} km", border=True,
              delta=f"{fdate(lg['date'].date())} · {fdur(lg['duration_s'])}", delta_color="off")
    st.metric("Plus grosse semaine", f"{fnum(rec['best_week'][1], 0)} km", border=True,
              delta=f"semaine du {fdate(rec['best_week'][0])}", delta_color="off")
    st.metric("Plus gros mois", f"{fnum(rec['best_month'][1], 0)} km", border=True,
              delta=rec["best_month"][0].strftime("%m/%Y"), delta_color="off")

best = hist.best_by_distance(df)
if best:
    st.markdown("**Meilleures sorties sur les distances classiques** (allure moyenne de la sortie entière : courses ou sorties de cette longueur)")
    st.dataframe(pd.DataFrame([{"Distance": b["distance"], "Date": fdate(b["date"]), "Km": round(b["km"], 2), "Temps": fdur(b["time"]),
                                "Allure": f"{fpace(b['pace'])}/km", "Séance": b["name"]} for b in best]),
                 hide_index=True, width="stretch")
be = service.progress(db, s)["best_efforts"]
if be:
    names = {"400": "400 m", "1000": "1 km", "1609": "1 mile", "3000": "3 km", "5000": "5 km", "10000": "10 km", "21097": "Semi"}
    st.markdown("**Meilleurs efforts mesurés dans les séances détaillées** (90 derniers jours)")
    st.dataframe(pd.DataFrame([{"Distance": names.get(k, k), "Temps": fdur(t), "Allure": f"{fpace(t / (int(k) / 1000))}/km", "Date": fdate(d)}
                               for k, (t, d) in sorted(be.items(), key=lambda kv: int(kv[0]))]), hide_index=True, width="stretch")
