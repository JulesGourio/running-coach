from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from coach import service
from coach.metrics import sleep as sl
from common import BAND, BLUE, LEVEL_COLOR, LEVEL_ICON, MUTED, ORANGE, ctx, fdate, fnum, style, tint

s, db = ctx()
today = date.today()
st.title("Récupération")

r = service.readiness_today(db, s)
with st.container(border=True):
    st.markdown(f":{LEVEL_COLOR[r['level']]}-badge[{LEVEL_ICON[r['level']]} {r['level'].capitalize()}] "
                f"Disponibilité {r['score'] if r['score'] is not None else '—'}/100")
    for reason in r["reasons"]:
        st.markdown(f"- {reason}")

rows = db.sleep()
if not rows:
    st.info("Pas encore de nuits synchronisées : lance `uv run coach history --days 365`.")
    st.stop()
all_df = sl.frame(rows)
first = all_df["night"].min().date()
dur = lambda m: f"{int(m // 60)} h {int(round(m % 60)):02d}" if m == m and m is not None else "—"  # noqa: E731

# ---- last night ------------------------------------------------------------------------------------------
last = all_df.iloc[-1]
st.subheader(f"Dernière nuit · {fdate(last['night'].date())}", divider="gray")
with st.container(horizontal=True):
    st.metric("Sommeil total", dur(last["total_min"]), border=True,
              delta=f"{(last['total_min'] - sl.TARGET_MIN) / 60:+.1f} h vs 8 h".replace(".", ","),
              delta_color="normal" if last["total_min"] >= sl.TARGET_MIN else "inverse", help="Nuit + siestes de la journée.")
    st.metric("Nuit", dur(last["main_min"]), border=True,
              delta=f"{sl.hhmm(last['bed_h'], evening=True)} → {sl.hhmm(last['wake_h'])}", delta_color="off")
    st.metric("Siestes", dur(last["naps_min"]) if last["naps_min"] else "aucune", border=True,
              delta=f"{int(last['n_naps'])} sieste(s)" if last["n_naps"] else None, delta_color="off")
    st.metric("Score COROS", f"{last['score']:.0f}/100", border=True)
    st.metric("Réveils > 5 min", f"{last['awake_count']:.0f}" if last["awake_count"] == last["awake_count"] else "—", border=True,
              delta=f"{dur(last['awake_min'])} éveillé" if last["awake_min"] == last["awake_min"] else None, delta_color="off")
with st.container(horizontal=True):
    for k, name in sl.PHASE_FR.items():
        lo, hi = sl.PHASE_REF[k]
        v = last[k]
        ok = v == v and lo <= v <= hi
        st.metric(name, f"{v:.0f} %" if v == v else "—", border=True,
                  delta=f"{dur(last[k.replace('_pct', '_min')])} · repère {lo}-{hi} %", delta_color="normal" if ok else "inverse",
                  help={"deep_pct": "Sommeil profond : récupération physique, hormone de croissance. Repère 13-23 %.",
                        "light_pct": "Sommeil léger : l'essentiel de la nuit. Repère 45-60 %.",
                        "rem_pct": "Sommeil paradoxal : récupération nerveuse, mémoire. Repère 20-25 %.",
                        "awake_pct": "Éveils dans la nuit. Repère sous 5 %."}[k])

# ---- tonight ---------------------------------------------------------------------------------------------
today_sessions = service.sessions_between(db, today.isoformat(), today.isoformat())
hard = any((x.get("kind_fr") or "").startswith(("VMA", "Seuil", "Allure", "Tempo", "Fartlek", "Côtes", "Course", "Sortie longue avec"))
           for x in today_sessions)
ratio = next((d["load_ratio"] for d in reversed(db.daily()) if d.get("load_ratio")), None)
rec = sl.recommended(all_df, hard, ratio, today)
with st.container(border=True):
    c1, c2 = st.columns([1, 2], vertical_alignment="center")
    c1.metric("Conseillé cette nuit", dur(rec["minutes"]), border=False,
              delta=f"coucher vers {sl.hhmm(rec['bedtime'])}", delta_color="off")
    c2.markdown(f"Pour un réveil vers **{sl.hhmm(rec['wake'])}** (ton heure habituelle sur 14 jours), 15 min d'endormissement comprises.  \n"
                + "  \n".join(f"- {w}" for w in rec["reasons"]))
    c2.caption(f"Dette de sommeil sur 7 nuits : **{dur(rec['debt_min'])}** sous l'objectif de 8 h par jour (siestes comprises).")

# ---- period ----------------------------------------------------------------------------------------------
period = st.segmented_control("Période", ["30 jours", "3 mois", "6 mois", "1 an", "Tout"], default="3 mois", key="rec-period") or "3 mois"
df = all_df[all_df["night"].dt.date >= sl.since(period, today, first)]
reg = sl.regularity(df)
with st.container(horizontal=True):
    st.metric("Moyenne par jour", dur(df["total_min"].mean()), border=True, help="Nuit + siestes, sur la période.")
    st.metric("Nuit moyenne", dur(df["main_min"].mean()), border=True)
    st.metric("Nuits sous 7 h", f"{(df['total_min'] < 420).mean():.0%}", border=True)
    st.metric("Jours avec sieste", f"{(df['n_naps'] > 0).mean():.0%}", border=True,
              delta=f"{dur(df.loc[df['naps_min'] > 0, 'naps_min'].mean())} en moyenne" if (df["naps_min"] > 0).any() else None,
              delta_color="off")
    st.metric("Coucher moyen", sl.hhmm(reg["bed_mean"], evening=True), border=True,
              delta=f"± {reg['bed_sd']:.0f} min" if reg["bed_sd"] else None, delta_color="off",
              help="Écart-type de l'heure de coucher : sous 30 min, horaires réguliers ; au-delà d'une heure, le rythme en pâtit.")
    st.metric("Lever moyen", sl.hhmm(reg["wake_mean"]), border=True,
              delta=f"± {reg['wake_sd']:.0f} min" if reg["wake_sd"] else None, delta_color="off")

# ---- nights: phases + naps -----------------------------------------------------------------------------
weekly = len(df) > 120
g = df.set_index("night").resample("W-MON", label="left").mean(numeric_only=True).reset_index() if weekly else df
fig = go.Figure()
colors = {"deep_min": "#1e3a8a", "light_min": "#60a5fa", "rem_min": "#a855f7", "awake_min": "#fbbf24", "naps_min": "#10b981"}
names = {"deep_min": "Profond", "light_min": "Léger", "rem_min": "Paradoxal", "awake_min": "Éveil", "naps_min": "Siestes"}
for k, c in colors.items():
    fig.add_bar(x=g["night"], y=g[k] / 60, name=names[k], marker_color=c,
                hovertemplate="%{x|%d %b} · " + names[k] + " %{y:.1f} h<extra></extra>")
fig.add_hline(y=sl.TARGET_MIN / 60, line=dict(color=MUTED, dash="dash"), annotation_text="8 h", annotation_font_color=MUTED)
style(fig, 320).update_layout(barmode="stack", title="Sommeil par " + ("semaine (moyenne par nuit)" if weekly else "nuit") + " : phases et siestes (h)",
                              hovermode="x unified")
st.plotly_chart(fig, width="stretch")

c1, c2 = st.columns(2)
fig = go.Figure()
fig.add_scatter(x=df["night"], y=df["bed_h"], mode="markers", name="Coucher", marker=dict(color="#6366f1", size=6),
                customdata=df["bed_h"].map(lambda h: sl.hhmm(h, evening=True)), hovertemplate="%{x|%d %b} coucher %{customdata}<extra></extra>")
fig.add_scatter(x=df["night"], y=df["wake_h"] + 12, mode="markers", name="Lever", marker=dict(color=ORANGE, size=6),
                customdata=df["wake_h"].map(sl.hhmm), hovertemplate="%{x|%d %b} lever %{customdata}<extra></extra>")
ticks = list(range(8, 24, 2))
style(fig, 280).update_layout(title="Heures de coucher et de lever", hovermode="closest")
fig.update_yaxes(tickvals=ticks, ticktext=[sl.hhmm(t, evening=True) for t in ticks], autorange="reversed")
c1.plotly_chart(fig, width="stretch")

wd = sl.by_period(df, "weekday")
fig = go.Figure(go.Bar(x=[sl.WEEKDAYS[i][:3] for i in wd["key"]], y=wd["total"] / 60, marker_color=BLUE,
                       customdata=wd["total"].map(dur), hovertemplate="nuit du %{x} : %{customdata}<extra></extra>",
                       text=wd["total"].map(dur), textposition="outside"))
fig.add_hline(y=sl.TARGET_MIN / 60, line=dict(color=MUTED, dash="dash"))
style(fig, 280).update_layout(title="Moyenne par jour de la semaine (nuit du …)", showlegend=False, hovermode="closest",
                              yaxis=dict(range=[0, max(10, (wd["total"].max() or 0) / 60 + 1)]))
c2.plotly_chart(fig, width="stretch")

mo = sl.by_period(all_df, "month")
yr = sl.by_period(all_df, "year")
c1, c2 = st.columns([2, 1])
fig = go.Figure()
fig.add_bar(x=mo["key"], y=mo["main"] / 60, name="Nuit", marker_color="#60a5fa")
fig.add_bar(x=mo["key"], y=mo["naps"] / 60, name="Siestes", marker_color="#10b981")
fig.add_hline(y=sl.TARGET_MIN / 60, line=dict(color=MUTED, dash="dash"))
style(fig, 280).update_layout(barmode="stack", title="Moyenne par jour, mois par mois (tout l'historique)", hovermode="x unified")
fig.update_xaxes(tickformat="%b %y")
c1.plotly_chart(fig, width="stretch")
c2.markdown("**Par année**")
c2.dataframe(pd.DataFrame({"Année": yr["key"].astype(str), "Par jour": yr["total"].map(dur), "Nuit": yr["main"].map(dur),
                           "Siestes": yr["naps"].map(dur), "Score": yr["score"].round(0), "Nuits": yr["nights"]}),
             hide_index=True, width="stretch")

naps = [(r_["night"], n) for _, r_ in df.iterrows() for n in r_["naps"]]
if naps:
    with st.expander(f"Siestes de la période ({len(naps)})", icon=":material/bedtime:"):
        st.dataframe(pd.DataFrame([{"Jour": fdate((d + timedelta(days=1)).date()), "Début": n["start"][-5:], "Fin": n["end"][-5:]}
                                   for d, n in reversed(naps)]), hide_index=True, width="stretch")

# ---- HRV and resting HR ----------------------------------------------------------------------------------
daily = pd.DataFrame(db.daily(sl.since(period, today, first).isoformat()))
if not daily.empty:
    daily["date"] = pd.to_datetime(daily["date"])
    st.subheader("VFC et FC de repos", divider="gray")
    c1, c2 = st.columns(2)
    h = daily.dropna(subset=["hrv"]) if "hrv" in daily else pd.DataFrame()
    if len(h):
        fig = go.Figure()
        if h["hrv_lo"].notna().any():
            fig.add_scatter(x=h["date"], y=h["hrv_hi"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
            fig.add_scatter(x=h["date"], y=h["hrv_lo"], mode="lines", line=dict(width=0), fill="tonexty", fillcolor=BAND,
                            name="Plage normale", hoverinfo="skip")
        fig.add_scatter(x=h["date"], y=h["hrv"], mode="lines+markers", line=dict(color=BLUE, width=2), name="VFC",
                        hovertemplate="%{x|%d %b} : %{y:.0f} ms<extra></extra>")
        style(fig, 280).update_layout(title="VFC nocturne (ms)")
        c1.plotly_chart(fig, width="stretch")
        c1.caption("Sous ta plage normale plusieurs jours de suite : fatigue à respecter.")
    rh = daily.dropna(subset=["rhr"]) if "rhr" in daily else pd.DataFrame()
    if len(rh):
        fig = go.Figure(go.Scatter(x=rh["date"], y=rh["rhr"], mode="lines+markers", line=dict(color=ORANGE, width=2), name="FC repos",
                                   hovertemplate="%{x|%d %b} : %{y:.0f} bpm<extra></extra>"))
        fig.add_scatter(x=rh["date"], y=rh["rhr"].rolling(7, min_periods=3).mean(), mode="lines", name="Moyenne 7 j",
                        line=dict(color=tint(ORANGE, 0.6), width=2, dash="dot"))
        style(fig, 280).update_layout(title="FC de repos (bpm)")
        c2.plotly_chart(fig, width="stretch")
        c2.caption("5 bpm au-dessus de ta moyenne au réveil : fatigue, maladie qui arrive ou chaleur.")
