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

tab_night, tab_stats, tab_hrv = st.tabs([":material/bedtime: Nuit", ":material/bar_chart: Statistiques du sommeil",
                                         ":material/monitor_heart: VFC et FC de repos"])

with tab_night:
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


    # ---- one night at a time -----------------------------------------------------------------------------------
    dates = [d.date() for d in all_df["date"]]  # wake-up dates
    cur = st.session_state.setdefault("night-sel", dates[-1])
    c1, c2, c3 = st.columns([1, 2, 1], vertical_alignment="bottom")
    if c1.button("Nuit précédente", icon=":material/chevron_left:", width="stretch"):
        st.session_state["night-sel"] = max((d for d in dates if d < cur), default=cur)
        st.rerun()
    picked = c2.date_input("Nuit se terminant le", value=cur, min_value=dates[0], max_value=dates[-1], format="DD/MM/YYYY",
                           key=f"night-pick-{cur}")
    if picked != cur:
        st.session_state["night-sel"] = picked
        st.rerun()
    if c3.button("Nuit suivante", icon=":material/chevron_right:", width="stretch", disabled=cur >= dates[-1]):
        st.session_state["night-sel"] = min((d for d in dates if d > cur), default=cur)
        st.rerun()
    wake = cur
    sel = all_df[all_df["date"].dt.date == wake]
    if sel.empty:
        st.info("Pas de nuit enregistrée pour cette date (montre non portée ?).")
    else:
        last = sel.iloc[0]
        st.subheader(f"Nuit du {fdate(last['night'].date())} au {fdate(last['date'].date())}", divider="gray")
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
        # 24 h timeline, from 18:00 the evening before to 18:00 on the wake-up day (hours after noon of the night)
        noon = pd.Timestamp(last["night"].date()) + pd.Timedelta(hours=12)
        rel = lambda ts: (pd.Timestamp(ts) - noon).total_seconds() / 3600  # noqa: E731
        fig = go.Figure()
        if last["bed_h"] == last["bed_h"] and last["wake_h"] == last["wake_h"]:
            fig.add_bar(y=["Sommeil"], x=[last["wake_h"] + 12 - last["bed_h"]], base=[last["bed_h"]], orientation="h", name="Nuit",
                        marker=dict(color="#3b5bdb", cornerradius=6), width=0.55, text=[dur(last["main_min"])],
                        textposition="inside", insidetextanchor="middle", textfont=dict(color="white"),
                        hovertemplate=f"Nuit {sl.hhmm(last['bed_h'], evening=True)} → {sl.hhmm(last['wake_h'])}<extra></extra>")
        for n_ in last["naps"] or []:
            a_, b_ = rel(n_["start"]), rel(n_["end"])
            fig.add_bar(y=["Sommeil"], x=[b_ - a_], base=[a_], orientation="h", name="Sieste", marker=dict(color="#10b981", cornerradius=6),
                        width=0.55, hovertemplate=f"Sieste {n_['start'][-5:]} → {n_['end'][-5:]}<extra></extra>", showlegend=False)
        ends = [rel(n_["end"]) for n_ in last["naps"] or []] + [last["wake_h"] + 12 if last["wake_h"] == last["wake_h"] else 20]
        starts = [rel(n_["start"]) for n_ in last["naps"] or []] + [last["bed_h"] if last["bed_h"] == last["bed_h"] else 10]
        x0, x1 = min(6, int(min(starts)) - 1), max(30, int(max(ends)) + 2)
        ticks = list(range(x0 + x0 % 2, x1 + 1, 2))
        style(fig, 150).update_layout(barmode="overlay", showlegend=False, hovermode="closest", margin=dict(t=36, b=30),
                                      title="La journée : nuit (bleu) et siestes (vert)",
                                      xaxis=dict(range=[x0, x1], tickvals=ticks, ticktext=[sl.hhmm(t_, evening=True) for t_ in ticks],
                                                 showgrid=True, gridcolor="rgba(137,135,129,0.2)"))
        fig.update_yaxes(showticklabels=False)
        fig.add_vrect(x0=12, x1=12, line=dict(color=MUTED, width=1, dash="dot"))
        st.plotly_chart(fig, width="stretch")

        # phases against their reference range: grey band = normal, colored bar = this night
        ph = [(k, name, c_) for (k, name), c_ in zip(sl.PHASE_FR.items(), ["#1e3a8a", "#60a5fa", "#a855f7", "#f59e0b"])]
        if any(last[k] == last[k] for k, *_ in ph):
            names = [name for _, name, _ in ph][::-1]
            fig = go.Figure()
            fig.add_bar(y=names, x=[sl.PHASE_REF[k][1] - sl.PHASE_REF[k][0] for k, *_ in ph][::-1],
                        base=[sl.PHASE_REF[k][0] for k, *_ in ph][::-1], orientation="h", width=0.8, name="Repère",
                        marker=dict(color="rgba(148,163,184,0.28)"), hoverinfo="skip")
            vals = [last[k] if last[k] == last[k] else 0 for k, *_ in ph][::-1]
            ok = [sl.PHASE_REF[k][0] <= last[k] <= sl.PHASE_REF[k][1] for k, *_ in ph][::-1]
            txt = [f"{v_:.0f} % · {dur(last[k.replace('_pct', '_min')])}" + ("" if o_ else "  ⚠") for v_, o_, (k, *_) in zip(vals, ok, ph[::-1])]
            fig.add_bar(y=names, x=vals, orientation="h", width=0.36, name="Cette nuit", marker=dict(color=[c_ for *_, c_ in ph][::-1], cornerradius=4),
                        text=txt, textposition="outside", cliponaxis=False, hovertemplate="%{y} : %{x:.0f} %<extra></extra>")
            style(fig, 230).update_layout(barmode="overlay", title="Phases de la nuit (bande grise : zone normale)", showlegend=False,
                                          hovermode="closest", xaxis=dict(range=[0, max(75, max(vals) + 20)], ticksuffix=" %"))
            st.plotly_chart(fig, width="stretch")
            st.caption("Profond : récupération physique (13-23 %). Léger : l'essentiel de la nuit (45-60 %). "
                       "Paradoxal : récupération nerveuse et mémoire (20-25 %). Éveil : sous 5 %.")

with tab_stats:
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
    g = g.dropna(subset=["total_min"])
    fig = go.Figure()
    fig.add_bar(x=g["night"], y=g["main_min"] / 60, name="Nuit", marker=dict(color="#93c5fd"),
                customdata=g["main_min"].map(dur), hovertemplate="%{x|%d %b} · nuit %{customdata}<extra></extra>")
    fig.add_bar(x=g["night"], y=g["naps_min"].fillna(0) / 60, name="Siestes", marker=dict(color="#10b981"),
                customdata=g["naps_min"].fillna(0).map(dur), hovertemplate="siestes %{customdata}<extra></extra>")
    if not weekly:
        roll = g.set_index("night")["total_min"].rolling("7D", min_periods=3).mean()
        fig.add_scatter(x=roll.index, y=roll / 60, mode="lines", name="Moyenne 7 jours", line=dict(color="#1e3a8a", width=2.5, shape="spline"),
                        customdata=roll.map(dur), hovertemplate="moyenne 7 j %{customdata}<extra></extra>")
    fig.add_hline(y=sl.TARGET_MIN / 60, line=dict(color=MUTED, dash="dash"), annotation_text="8 h", annotation_font_color=MUTED)
    style(fig, 300).update_layout(barmode="stack", bargap=0.25, hovermode="x unified",
                                  title="Durée de sommeil par " + ("semaine (moyenne par jour)" if weekly else "jour") + " : nuit + siestes",
                                  yaxis=dict(ticksuffix=" h", range=[0, max(10, float((g["total_min"] / 60).max()) + 0.5)]))
    st.plotly_chart(fig, width="stretch")

    c1, c2 = st.columns(2)
    q = df.dropna(subset=["deep_pct", "rem_pct"]).set_index("night")
    if len(q) >= 5:
        fig = go.Figure()
        for k, name, c_, (lo, hi) in (("deep_pct", "Profond", "#1e3a8a", sl.PHASE_REF["deep_pct"]),
                                      ("rem_pct", "Paradoxal", "#a855f7", sl.PHASE_REF["rem_pct"])):
            fig.add_hrect(y0=lo, y1=hi, fillcolor=tint(c_, 0.10), line_width=0, layer="below")
            fig.add_scatter(x=q.index, y=q[k], mode="markers", marker=dict(color=tint(c_, 0.35), size=5), showlegend=False, hoverinfo="skip")
            sm = q[k].rolling("7D", min_periods=2).mean()
            fig.add_scatter(x=sm.index, y=sm, mode="lines", name=name, line=dict(color=c_, width=2.5, shape="spline"),
                            hovertemplate=name + " %{y:.0f} % (moy. 7 j)<extra></extra>")
        style(fig, 300).update_layout(title="Qualité : part de profond et de paradoxal (bandes : zone normale)",
                                      yaxis=dict(ticksuffix=" %", range=[0, 45]), hovermode="x unified")
        c1.plotly_chart(fig, width="stretch")

    # sleep window of every night: a floating bar from bedtime to wake-up (y reversed: evening at the top)
    w_ = df.dropna(subset=["bed_h", "wake_h"])
    if len(w_):
        span = w_["wake_h"] + 12 - w_["bed_h"]
        fig = go.Figure(go.Bar(x=w_["night"], y=span, base=w_["bed_h"],
                               marker=dict(color=["#3b5bdb" if m_ >= 420 else "#f59e0b" for m_ in w_["main_min"].fillna(0)]),
                               customdata=list(zip(w_["bed_h"].map(lambda h: sl.hhmm(h, evening=True)), w_["wake_h"].map(sl.hhmm),
                                                   w_["main_min"].map(dur))),
                               hovertemplate="%{x|%d %b} · %{customdata[0]} → %{customdata[1]} (%{customdata[2]})<extra></extra>"))
        lo_, hi_ = float(w_["bed_h"].quantile(0.02)) - 0.5, float((w_["wake_h"] + 12).quantile(0.98)) + 0.5
        ticks = [t_ for t_ in range(int(lo_) - 1, int(hi_) + 2) if t_ % 2 == 0]
        style(fig, 300).update_layout(title="Fenêtre de sommeil : coucher → lever (orange : nuit sous 7 h)", hovermode="closest",
                                      bargap=0.3, showlegend=False)
        fig.update_yaxes(range=[hi_, lo_], tickvals=ticks, ticktext=[sl.hhmm(t_, evening=True) for t_ in ticks])
        c2.plotly_chart(fig, width="stretch")

    c1, c2 = st.columns(2)

    wd = sl.by_period(df, "weekday")
    fig = go.Figure(go.Bar(x=[sl.WEEKDAYS[i][:3] for i in wd["key"]], y=wd["total"] / 60, marker_color=BLUE,
                           customdata=wd["total"].map(dur), hovertemplate="nuit du %{x} : %{customdata}<extra></extra>",
                           text=wd["total"].map(dur), textposition="outside"))
    fig.add_hline(y=sl.TARGET_MIN / 60, line=dict(color=MUTED, dash="dash"))
    style(fig, 300).update_layout(title="Moyenne par jour de la semaine (nuit du …)", showlegend=False, hovermode="closest",
                                  yaxis=dict(range=[0, max(10, (wd["total"].max() or 0) / 60 + 1)]))
    c1.plotly_chart(fig, width="stretch")

    mo = sl.by_period(all_df, "month")
    yr = sl.by_period(all_df, "year")
    fig = go.Figure()
    fig.add_bar(x=mo["key"], y=mo["main"] / 60, name="Nuit", marker_color="#60a5fa")
    fig.add_bar(x=mo["key"], y=mo["naps"] / 60, name="Siestes", marker_color="#10b981")
    fig.add_hline(y=sl.TARGET_MIN / 60, line=dict(color=MUTED, dash="dash"))
    style(fig, 300).update_layout(barmode="stack", title="Moyenne par jour, mois par mois (tout l'historique)", yaxis=dict(ticksuffix=" h"), hovermode="x unified")
    fig.update_xaxes(tickformat="%b %y")
    c2.plotly_chart(fig, width="stretch")
    st.markdown("**Par année**")
    st.dataframe(pd.DataFrame({"Année": yr["key"].astype(str), "Par jour": yr["total"].map(dur), "Nuit": yr["main"].map(dur),
                               "Siestes": yr["naps"].map(dur), "Score": yr["score"].round(0), "Nuits": yr["nights"]}),
                 hide_index=True, width="stretch")

    naps = [(r_["night"], n) for _, r_ in df.iterrows() for n in r_["naps"]]
    if naps:
        with st.expander(f"Siestes de la période ({len(naps)})", icon=":material/bedtime:"):
            st.dataframe(pd.DataFrame([{"Jour": fdate((d + timedelta(days=1)).date()), "Début": n["start"][-5:], "Fin": n["end"][-5:]}
                                       for d, n in reversed(naps)]), hide_index=True, width="stretch")


with tab_hrv:
    # ---- HRV and resting HR ----------------------------------------------------------------------------------
    period_h = st.segmented_control("Période", ["30 jours", "3 mois", "6 mois", "1 an", "Tout"], default="3 mois",
                                    key="hrv-period") or "3 mois"
    daily = pd.DataFrame(db.daily(sl.since(period_h, today, first).isoformat()))
    if not daily.empty:
        daily["date"] = pd.to_datetime(daily["date"])
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
