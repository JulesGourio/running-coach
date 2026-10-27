"""Récupération: readiness, tonight's advice, one night at a time, sleep statistics, HRV and resting HR."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from appkit import ui

from coach.mobile import app, ctx, fmt

PERIODS = [("30 jours", "30 j"), ("3 mois", "3 mois"), ("6 mois", "6 mois"), ("1 an", "1 an"), ("Tout", "Tout")]
HARD = ("VMA", "Seuil", "Allure", "Tempo", "Fartlek", "Côtes", "Course", "Sortie longue avec")


@app.screen("recuperation")
def recuperation(vue: str = "nuit", nuit: str = "", periode: str = "3 mois"):
    from coach import service
    from coach.metrics import sleep as sl

    s, db = ctx()
    today = date.today()
    r = service.readiness_today(db, s)
    blocks = [ui.card(f"Disponibilité {r['score'] if r['score'] is not None else '—'}/100",
                      ui.bullets(r["reasons"]), tone=fmt.LEVEL_TONE.get(r["level"])),
              ui.choice("vue", [("nuit", "Nuit"), ("stats", "Statistiques"), ("vfc", "VFC et FC de repos")], vue)]
    rows = db.sleep()
    if not rows and vue != "vfc":
        return ui.page("Récupération", *blocks, ui.alert("info", "Pas encore de nuits synchronisées",
                                                         "Plus → Historique → « Tout l'historique COROS »."))
    all_df = sl.frame(rows) if rows else pd.DataFrame()

    if vue == "nuit":
        sess = service.sessions_between(db, today.isoformat(), today.isoformat())
        hard = any((x.get("kind_fr") or "").startswith(HARD) for x in sess)
        ratio = next((d["load_ratio"] for d in reversed(db.daily()) if d.get("load_ratio")), None)
        rec = sl.recommended(all_df, hard, ratio, today)
        blocks.append(ui.card("Cette nuit", ui.big("Sommeil conseillé", fmt.hm(rec["minutes"]), f"coucher vers {sl.hhmm(rec['bedtime'])}"),
                              ui.text(f"Pour un réveil vers **{sl.hhmm(rec['wake'])}** (ton heure habituelle), 15 min d'endormissement comprises."),
                              ui.bullets(rec["reasons"], "muted"),
                              ui.muted(f"Dette de sommeil sur 7 nuits : {fmt.hm(rec['debt_min'])} sous 8 h par jour (siestes comprises).")))
        dates = [d.date().isoformat() for d in all_df["date"]]
        cur = nuit if nuit in dates else dates[-1]
        i = dates.index(cur)
        blocks.append(ui.pager(f"Nuit se terminant le {fmt.day(cur)}", {"nuit": dates[i - 1]} if i > 0 else None,
                               {"nuit": dates[i + 1]} if i + 1 < len(dates) else None))
        last = all_df[all_df["date"].dt.date == date.fromisoformat(cur)].iloc[0]
        ok = last["total_min"] >= sl.TARGET_MIN
        blocks.append(ui.metrics(
            ui.metric("Sommeil total", fmt.hm(last["total_min"]), f"{(last['total_min'] - sl.TARGET_MIN) / 60:+.1f} h vs 8 h".replace(".", ","),
                      sub_tone="good" if ok else "bad"),
            ui.metric("Nuit", fmt.hm(last["main_min"]), f"{sl.hhmm(last['bed_h'], evening=True)} → {sl.hhmm(last['wake_h'])}"),
            ui.metric("Siestes", fmt.hm(last["naps_min"]) if last["naps_min"] else "aucune",
                      f"{int(last['n_naps'])} sieste(s)" if last["n_naps"] else None),
            ui.metric("Score COROS", f"{last['score']:.0f}/100" if last["score"] == last["score"] else "—"),
            ui.metric("Réveils > 5 min", f"{last['awake_count']:.0f}" if last["awake_count"] == last["awake_count"] else "—",
                      f"{fmt.hm(last['awake_min'])} éveillé" if last["awake_min"] == last["awake_min"] else None)))
        ph = list(sl.PHASE_FR.items())
        if any(last[k] == last[k] for k, _ in ph):
            blocks.append(ui.card("Phases de la nuit", ui.table(["Phase", "Cette nuit", "Durée", "Zone normale"], [
                [name, f"{last[k]:.0f} %" if last[k] == last[k] else "—", fmt.hm(last.get(k.replace("_pct", "_min"))),
                 f"{sl.PHASE_REF[k][0]}-{sl.PHASE_REF[k][1]} %"] for k, name in ph],
                tones=[[None, None if last[k] != last[k] or sl.PHASE_REF[k][0] <= last[k] <= sl.PHASE_REF[k][1] else "warn", None, None]
                       for k, _ in ph]),
                ui.muted("Profond : récupération physique. Paradoxal : récupération nerveuse et mémoire.")))
        if last["naps"]:
            blocks.append(ui.muted("Siestes : " + ", ".join(f"{n['start'][-5:]} → {n['end'][-5:]}" for n in last["naps"])))

    elif vue == "stats":
        first = all_df["night"].min().date()
        df = all_df[all_df["night"].dt.date >= sl.since(periode, today, first)]
        reg = sl.regularity(df)
        blocks += [ui.choice("periode", PERIODS, periode), ui.metrics(
            ui.metric("Moyenne par jour", fmt.hm(df["total_min"].mean()), "nuit + siestes"),
            ui.metric("Nuit moyenne", fmt.hm(df["main_min"].mean())),
            ui.metric("Nuits sous 7 h", fmt.pct((df["total_min"] < 420).mean())),
            ui.metric("Jours avec sieste", fmt.pct((df["n_naps"] > 0).mean())),
            ui.metric("Coucher moyen", sl.hhmm(reg["bed_mean"], evening=True), f"± {reg['bed_sd']:.0f} min" if reg["bed_sd"] else None),
            ui.metric("Lever moyen", sl.hhmm(reg["wake_mean"]), f"± {reg['wake_sd']:.0f} min" if reg["wake_sd"] else None))]
        weekly = len(df) > 120
        g = df.set_index("night").resample("W-MON", label="left").mean(numeric_only=True).reset_index() if weekly else df
        g = g.dropna(subset=["total_min"])
        if len(g):
            blocks.append(ui.chart("Sommeil par " + ("semaine (moyenne par jour)" if weekly else "jour") + " (h)",
                                   [fmt.short(d) for d in g["night"]], ui.series("Nuit", g["main_min"] / 60, "#93c5fd"),
                                   ui.series("Siestes", g["naps_min"].fillna(0) / 60, "#10b981"), kind="stack", y="hours",
                                   lines=[ui.hline(sl.TARGET_MIN / 60, "8 h")]))
        q = df.dropna(subset=["deep_pct", "rem_pct"]).set_index("night")
        if len(q) >= 5:
            blocks.append(ui.chart("Part de profond et de paradoxal (moyenne 7 j)", [fmt.short(d) for d in q.index],
                                   ui.series("Profond", q["deep_pct"].rolling("7D", min_periods=2).mean(), "#1e3a8a"),
                                   ui.series("Paradoxal", q["rem_pct"].rolling("7D", min_periods=2).mean(), "#a855f7"),
                                   y="pct", bands=[ui.band(*sl.PHASE_REF["deep_pct"], "#1e3a8a"), ui.band(*sl.PHASE_REF["rem_pct"], "#a855f7")],
                                   y_min=0, y_max=45))
        wd = sl.by_period(df, "weekday")
        if len(wd):
            blocks.append(ui.chart("Moyenne par jour de la semaine (h)", [sl.WEEKDAYS[i][:3] for i in wd["key"]],
                                   ui.series("Sommeil", wd["total"] / 60, fmt.BLUE, "bar"), kind="bar", y="hours",
                                   lines=[ui.hline(sl.TARGET_MIN / 60, "8 h")]))
        yr = sl.by_period(all_df, "year")
        blocks.append(ui.card("Par année", ui.table(["Année", "Par jour", "Nuit", "Siestes", "Score", "Nuits"], [
            [str(r.key), fmt.hm(r.total), fmt.hm(r.main), fmt.hm(r.naps), fmt.num(r.score, 0), int(r.nights)] for r in yr.itertuples()])))

    else:
        first = all_df["night"].min().date() if len(all_df) else today - timedelta(days=365)
        daily = pd.DataFrame(db.daily(sl.since(periode, today, first).isoformat()))
        blocks.append(ui.choice("periode", PERIODS, periode))
        if not daily.empty:
            h = daily.dropna(subset=["hrv"]) if "hrv" in daily else pd.DataFrame()
            if len(h):
                bands = None
                lo, hi = h.get("hrv_lo"), h.get("hrv_hi")
                if lo is not None and lo.notna().any():
                    bands = [ui.band(float(lo.dropna().iloc[-1]), float(hi.dropna().iloc[-1]), fmt.BLUE, "plage normale")]
                blocks += [ui.chart("VFC nocturne (ms)", [fmt.short(d) for d in h["date"]], ui.series("VFC", h["hrv"], fmt.BLUE), bands=bands),
                           ui.muted("Sous ta plage normale plusieurs jours de suite : fatigue à respecter.")]
            rh = daily.dropna(subset=["rhr"]) if "rhr" in daily else pd.DataFrame()
            if len(rh):
                blocks += [ui.chart("FC de repos (bpm)", [fmt.short(d) for d in rh["date"]], ui.series("FC repos", rh["rhr"], fmt.ORANGE),
                                    ui.series("Moyenne 7 j", rh["rhr"].rolling(7, min_periods=3).mean(), "#f0a07a", "dash")),
                           ui.muted("5 bpm au-dessus de ta moyenne au réveil : fatigue, maladie qui arrive ou chaleur.")]
        else:
            blocks.append(ui.muted("Pas encore de VFC ni de FC de repos."))
    return ui.page("Récupération", *blocks)
