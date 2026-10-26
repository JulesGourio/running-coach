"""Séances: the list with its filters, and one session in detail (as the Streamlit Séances page)."""
from __future__ import annotations

import pandas as pd
from appkit import ui

from coach.mobile import app, ctx, fmt
from coach.mobile.today import session_row

RUN = (100, 101, 102, 103, None)
PERIODS = [("91", "3 mois"), ("182", "6 mois"), ("365", "1 an"), ("3650", "Tout")]
SPORTS = [("run", "Course"), ("other", "Autres sports"), ("all", "Tous")]


def _cat(x: dict) -> str:
    return x["kind_fr"] or ("Non analysée" if x.get("sport_type") in RUN else x["type"] or "Autre")


@app.screen("seances")
def seances(periode: str = "91", sport: str = "run", type: str = ""):
    from coach import service

    _, db = ctx()
    rows = service.sessions(db, int(periode) if periode.isdigit() else 91, sports=sport)
    cats = sorted({_cat(x) for x in rows})
    if type and type not in cats:
        type = ""
    shown = [x for x in rows if not type or _cat(x) == type]
    km = sum(x["distance_km"] or 0 for x in shown)
    return ui.page(
        "Séances",
        ui.choice("periode", PERIODS, periode),
        ui.choice("sport", SPORTS, sport),
        ui.choice("type", [("", "Tous les types"), *[(c, c) for c in cats]], type) if len(cats) > 1 else None,
        ui.muted(f"{len(shown)} séance{'s' if len(shown) > 1 else ''} · {fmt.num(km, 0)} km"),
        ui.rows([session_row(x) for x in shown], empty="Aucune séance sur la période."),
    )


def _downsample(df: pd.DataFrame, n: int = 300) -> pd.DataFrame:
    return df.iloc[:: max(1, len(df) // n)]


@app.screen("seance")
def seance(label_id: str):
    from coach import service
    from coach.verdict import hard_segments

    s, db = ctx()
    act = db.activity(label_id)
    if not act:
        return ui.page("Séance", ui.alert("bad", "Séance introuvable"))
    try:
        d = service.session_detail(db, label_id, with_records=True)
    except Exception:  # noqa: BLE001 - FIT unreadable on this device: show the stored analysis
        d = service.session_detail(db, label_id)
    m, v = d.get("metrics") or {}, d.get("verdict") or {}
    is_run = act.get("sport_type") in RUN
    blocks: list = []

    head = [fmt.day(act["date"]), act.get("name") or ""]
    if is_run and d.get("planned"):
        plan_txt = " + ".join(f"{p['name']} ({p['summary']})" for p in d["planned"])
        blocks.append(ui.muted(f"Prévu : {plan_txt}"))
        if v.get("score") is not None:
            blocks.append(ui.big("Respect du plan", f"{fmt.num(v['score'])}/10",
                                 tone="good" if v["score"] >= 8 else "warn" if v["score"] >= 6 else "bad"))
    elif is_run:
        blocks.append(ui.muted("Séance hors plan."))

    cv = d.get("coach_verdict")
    if cv:
        blocks.append(ui.card("Verdict du coach" + (f" · {fmt.num(cv['score'])}/10" if cv.get("score") is not None else ""),
                              ui.text(cv["text"]), tone="info"))
    if v.get("findings"):
        blocks.append(ui.card("Constats", ui.bullets(v["findings"])))

    if not m:
        blocks += [ui.alert("info", "Fichier FIT détaillé pas encore téléchargé",
                            "Il arrive à la prochaine synchronisation. En attendant, le résumé COROS :"),
                   ui.metrics(ui.metric("Distance", f"{fmt.num(act['distance_km'], 2)} km"),
                              ui.metric("Durée", fmt.dur(act["duration_s"])),
                              ui.metric("Allure", fmt.pace_km(act.get("avg_pace"))) if act.get("avg_pace") and is_run else None,
                              ui.metric("FC moyenne", f"{act['avg_hr']:.0f} bpm") if act.get("avg_hr") else None,
                              ui.metric("Calories", f"{act['calories']:.0f} kcal") if act.get("calories") else None)]
        blocks.append(_verdict_form(label_id, cv))
        return ui.page(v.get("structure") or act.get("name") or "Séance", *blocks, subtitle=" · ".join(h for h in head if h))

    km = m["distance_m"] / 1000
    up, down = m.get("ascent_m") or 0, m.get("descent_m") or 0
    hilly = act.get("sport_type") in (102, 104, 204) or (km > 0 and up / km >= 15)
    stopped = (m.get("elapsed_s") or 0) - (m.get("moving_s") or 0)
    easy_pct = sum((m.get("zones_hr") or {}).get(k, 0) for k in ("Z1 récup", "Z2 endurance")) if m.get("zones_hr") else None
    dec = (m.get("decoupling") or {}).get("decoupling_pct")
    if is_run:
        items = [ui.metric("Distance", f"{fmt.num(km, 2)} km"),
                 ui.metric("Temps en mouvement", fmt.dur(m["moving_s"]), f"arrêts {fmt.dur(stopped)}" if stopped > 60 else None),
                 ui.metric("Allure moyenne", fmt.pace_km(m["avg_pace"])),
                 ui.metric("FC moyenne", f"{fmt.num(m['avg_hr'], 0)} bpm", f"max {fmt.num(m.get('max_hr'), 0)}"),
                 ui.metric("Temps en endurance", fmt.pct(easy_pct) if easy_pct is not None else "—", "zones 1 et 2"),
                 ui.metric("Dénivelé", f"+{fmt.num(up, 0)} / -{fmt.num(down, 0)} m")]
        if hilly:
            items += [ui.metric("Allure d'effort", fmt.pace_km(m.get("effort_pace")), "équivalent plat"),
                      ui.metric("Km-effort", fmt.num(km + up / 100, 1)),
                      ui.metric("Vitesse ascensionnelle", f"{fmt.num(m.get('climb_rate'), 0)} m/h" if m.get("climb_rate") else "—")]
        items += [ui.metric("Cadence", f"{fmt.num(m['cadence'], 0)} pas/min"),
                  None if hilly else ui.metric("Dérive cardiaque", f"{fmt.num(dec, 1)} %" if dec is not None else "—",
                                               "sous 5 % : endurance solide", sub_tone="good" if dec is not None and dec < 5 else "warn"),
                  ui.metric("Charge", fmt.num(m.get("load"), 0), "100 = 1 h au seuil")]
    else:
        spd = m["distance_m"] / m["moving_s"] * 3.6 if m.get("moving_s") else None
        items = [ui.metric("Distance", f"{fmt.num(km, 2)} km"), ui.metric("Temps en mouvement", fmt.dur(m["moving_s"])),
                 ui.metric("Durée totale", fmt.dur(m.get("elapsed_s"))),
                 ui.metric("Vitesse", f"{fmt.num(spd, 1)} km/h" if spd else "—"),
                 ui.metric("Dénivelé", f"+{fmt.num(up, 0)} / -{fmt.num(down, 0)} m"),
                 ui.metric("FC moyenne", f"{fmt.num(m['avg_hr'], 0)} bpm", f"max {fmt.num(m.get('max_hr'), 0)}"),
                 ui.metric("Calories", f"{act['calories']:.0f} kcal" if act.get("calories") else "—")]
        if hilly:
            items += [ui.metric("Km-effort", fmt.num(km + up / 100, 1)),
                      ui.metric("Vitesse ascensionnelle", f"{fmt.num(m.get('climb_rate'), 0)} m/h" if m.get("climb_rate") else "—")]
    blocks.append(ui.metrics(*items))

    track = m.get("track") or []
    if len(track) > 5:
        blocks.append(ui.route(track, label=f"D+ {fmt.num(up, 0)} m"))

    rec = d.get("records")
    if rec is not None and len(rec):
        rec = rec.copy()
        rec["km"] = rec["distance"] / 1000
        g = _downsample(rec)
        labels = [fmt.num(k, 1) for k in g["km"]]
        if is_run:
            moving = rec["speed"] > 0.8
            sm = rec["speed"].where(moving).rolling(20, min_periods=5, center=True).mean()
            p = (1000 / sm).where(sm > 1.2).clip(lower=150, upper=600)
            a = service.athlete(db, s)
            blocks.append(ui.chart("Allure (min/km)", labels, ui.series("Allure", p.loc[g.index], fmt.BLUE), y="pace", reverse=True,
                                   lines=[ui.hline(a.threshold_pace, f"seuil {fmt.pace(a.threshold_pace)}", fmt.ZONE_COLORS["Z4 seuil"])]))
        else:
            sp = rec["speed"].rolling(15, min_periods=3, center=True).mean() * 3.6
            blocks.append(ui.chart("Vitesse (km/h)", labels, ui.series("Vitesse", sp.loc[g.index], fmt.BLUE)))
        if rec["hr"].notna().any():
            warm = g[g["elapsed"] >= 60] if (g["elapsed"] >= 60).any() else g
            a = service.athlete(db, s)
            bands = [ui.band(lo, hi, fmt.ZONE_COLORS[name], name) for name, lo, hi in a.hr_zone_bounds()]
            blocks.append(ui.chart("Fréquence cardiaque (bpm)", [fmt.num(k, 1) for k in warm["km"]],
                                   ui.series("FC", warm["hr"], "#111827"), bands=bands,
                                   y_min=float(warm["hr"].quantile(0.02)) - 5, y_max=float(warm["hr"].quantile(0.98)) + 5))
        if "altitude" in rec and rec["altitude"].notna().sum() > 10:
            alt = g["altitude"].interpolate(limit_direction="both")
            blocks.append(ui.chart("Altitude (m)", labels, ui.series("Altitude", alt, "#0d9488", "area"), height=120))

    for key, ttl in (("zones_hr", "Temps par zone de FC"), ("zones_pace", "Temps par zone d'allure")):
        z = m.get(key) or {}
        if z and (is_run or key == "zones_hr"):
            blocks.append(ui.chart(ttl, list(z), ui.series("Part du temps", [x * 100 for x in z.values()]), kind="hbar", y="pct",
                                   height=150, lines=None))

    splits = m.get("splits") or []
    if len(splits) >= 2:
        cols = ["Km", "Temps", "Allure" if is_run else "Vitesse", *(["Effort"] if is_run and hilly else []), "D+", "D-", "FC"]
        blocks.append(ui.card(f"Kilomètre par kilomètre ({len(splits)})", ui.table(cols, [
            [sp["km"], fmt.dur(sp["time_s"]), fmt.pace(sp["pace"]) if is_run else fmt.num(3600 / sp["pace"], 1),
             *([fmt.pace(sp.get("effort_pace"))] if is_run and hilly else []), round(sp["up"]), round(sp["down"]),
             round(sp["hr"]) if sp.get("hr") else None] for sp in splits]), collapsed=not hilly))

    reps = v.get("reps")
    if reps and reps.get("reps"):
        t = []
        for i, r in enumerate(reps["reps"], 1):
            st_, done = r["step"], r["done"] or {}
            t.append([i, f"{fmt.pace(st_['pace_lo'])}–{fmt.pace(st_['pace_hi'])}", fmt.pace(done.get("pace")) if done else "—",
                      fmt.num(r["delta_s"], 1) if r["delta_s"] is not None else None, r["status"],
                      round(done["avg_hr"]) if done.get("avg_hr") else None])
        blocks.append(ui.card("Répétitions", ui.muted("Tours de la montre" if reps.get("method") == "tour" else "Détectées dans les données"),
                              ui.table(["#", "Cible", "Réalisé", "Écart s/km", "Statut", "FC"], t)))
    segments = v.get("segments")
    if segments:
        blocks.append(ui.card("Répétitions", ui.muted("D'après les tours de la montre." if segments[0].get("source") == "tour"
                                                      else "Détectées dans les données GPS, au cœur de chaque effort."),
                              ui.table(["#", "Distance", "Durée", "Allure", "FC"], [
                                  [sg["n"], f"{round(sg['distance_m'])} m" if sg.get("distance_m") else None, fmt.dur(sg["duration_s"]),
                                   fmt.pace(sg.get("pace")), round(sg["avg_hr"]) if sg.get("avg_hr") else None] for sg in segments])))
    if d.get("laps"):
        blocks.append(ui.card(f"Tours ({len(d['laps'])})", ui.table(["#", "Distance", "Temps", "Allure", "FC moy.", "FC max"], [
            [i, f"{round(lp['distance_m'] or 0)} m", fmt.dur(lp.get("timer_s") or lp.get("elapsed_s")),
             fmt.pace((lp.get("timer_s") or lp.get("elapsed_s") or 0) / (lp["distance_m"] / 1000)) if lp.get("distance_m") else "—",
             lp.get("avg_hr"), lp.get("max_hr")] for i, lp in enumerate(d["laps"], 1)]), collapsed=True))

    be = (m.get("best_efforts") or {}) if is_run else {}
    if be:
        names = {"400": "400 m", "1000": "1 km", "1609": "1 mile", "3000": "3 km", "5000": "5 km", "10000": "10 km", "21097": "Semi"}
        blocks.append(ui.card("Meilleurs efforts de la séance", ui.table(["Distance", "Temps", "Allure"], [
            [names.get(k, k), fmt.dur(t_), fmt.pace_km(t_ / (int(k) / 1000))] for k, t_ in be.items()]), collapsed=True))

    kind = v.get("type_fr")
    if kind:
        a_ = service.athlete(db, s)
        ans = db.analyses()
        same = []
        for x in service.sessions(db, 3650, sports="all"):
            if x["kind_fr"] != kind:
                continue
            mx = (ans.get(x["label_id"]) or {}).get("metrics") or {}
            reps_ = [g_["avg_pace"] for g_ in hard_segments(mx, a_) if g_["duration_s"] >= 40]
            same.append({"date": x["date"], "pace": x["avg_pace"],
                         "rep": float(pd.Series(reps_).median()) if reps_ else None, "current": x["label_id"] == label_id})
        if len(same) > 1:
            same.sort(key=lambda r_: r_["date"])
            use_rep = sum(1 for r_ in same if r_["rep"]) >= 2
            vals = [r_["rep"] if use_rep else r_["pace"] for r_ in same]
            cur = next(i for i, r_ in enumerate(same) if r_["current"])
            blocks.append(ui.chart(f"Tes séances « {kind} » ({len(same)}) : " + ("allure des répétitions" if use_rep else "allure moyenne"),
                                   [fmt.short(r_["date"]) for r_ in same], ui.series(kind, vals, fmt.type_color(kind), "points"),
                                   y="pace", reverse=True, highlight=cur))

    blocks.append(_verdict_form(label_id, cv))
    return ui.page(v.get("structure") or act.get("name") or "Séance", *blocks, subtitle=" · ".join(h for h in head if h))


def _verdict_form(label_id: str, cv: dict | None) -> dict:
    return ui.card("Écrire un verdict", ui.muted("Claude rédige le verdict depuis le PC (« juge ma séance »). Tu peux aussi "
                                                 "noter la tienne ici."),
                   ui.form([ui.field("texte", "Verdict", "multiline", (cv or {}).get("text", "")),
                            ui.field("note", "Note sur 10 (facultatif)", "decimal",
                                     "" if not cv or cv.get("score") is None else fmt.num(cv["score"]))],
                           "verdict_enregistrer", args={"label_id": label_id}), collapsed=True)


@app.action("verdict_enregistrer")
def verdict_enregistrer(label_id: str, texte: str = "", note: str = ""):
    _, db = ctx()
    if not texte.strip():
        raise ValueError("Le verdict est vide.")
    score = float(note.replace(",", ".")) if note.strip() else None
    if score is not None and not 0 <= score <= 10:
        raise ValueError("Note entre 0 et 10.")
    db.save_verdict(label_id, texte.strip(), score)
    return "Verdict enregistré."
