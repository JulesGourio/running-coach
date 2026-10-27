"""Aujourd'hui (the Streamlit home page) and the weekly report."""
from __future__ import annotations

from collections import Counter
from datetime import date

from appkit import ui

from coach.mobile import app, ctx, fmt, last_sync


def session_row(x: dict) -> dict:
    """A session in a list: date, type badge, structure, distance, plan score."""
    bits = [f"{fmt.num(x['distance_km'], 1)} km" if x.get("distance_km") else None,
            fmt.pace_km(x["avg_pace"]) if x.get("avg_pace") and x.get("sport_type") in (100, 101, 102, 103, None) else None,
            f"FC {x['avg_hr']:.0f}" if x.get("avg_hr") else None]
    score = (f"{fmt.num(x['score'])}/10" if x.get("score") is not None else "prévue") if x.get("planned") else None
    return ui.row(x.get("structure") or x.get("headline") or x.get("name") or x.get("type") or "Séance",
                  sub=f"{fmt.day(x['date'])} · " + " · ".join(b for b in bits if b),
                  value=score, tone=("good" if (x.get("score") or 0) >= 8 else "warn" if (x.get("score") or 10) < 6 else None)
                  if x.get("score") is not None else None,
                  badge=fmt.type_badge(x.get("kind_fr") or x.get("type")), open=ui.link("seance", label_id=x["label_id"]))


def goal_line(s) -> str | None:
    if not s.goal_date:
        return None
    g = date.fromisoformat(s.goal_date)
    return f"{s.goal_label} le {fmt.day(g)} · J-{(g - date.today()).days} · A {fmt.dur(s.goal_a)} · B {fmt.dur(s.goal_b)}"


@app.screen("aujourdhui")
def aujourdhui():
    from coach import alerts as al
    from coach import service

    s, db = ctx()
    if not db.activities():
        return ui.page("Carnet de course",
                       ui.alert("info", "Aucune séance pour l'instant",
                                "Connecte COROS dans Réglages puis synchronise, ou importe l'archive du PC "
                                "(`uv run coach export-mobile`)."),
                       ui.rows([ui.row("Réglages", sub="Connexion COROS, import des données", open=ui.link("reglages"))]),
                       ui.sync_status(last_sync(db)), subtitle=goal_line(s))

    blocks = [ui.sync_status(last_sync(db))]
    for x in al.alerts(db, s):
        blocks.append(ui.alert(x["level"], x["title"], f"{x['detail']}\n{x['advice']}"))

    r = service.readiness_today(db, s)
    lvl = r["level"]
    t = r.get("today")
    today_blocks = []
    if t and t["courses"]:
        for c in t["courses"]:
            today_blocks += [ui.text(f"**{c['name']}**"), ui.muted(c["summary"])]
        if r.get("advice"):
            today_blocks.append(ui.alert("info", r["advice"]))
    else:
        today_blocks.append(ui.muted("Repos ou pas de séance prévue aujourd'hui."))
    blocks += [
        ui.card("Forme du jour", ui.big(lvl.capitalize(), f"{r['score'] if r['score'] is not None else '—'}/100",
                                        tone=fmt.LEVEL_TONE.get(lvl)), ui.bullets(r["reasons"], "muted"),
                open=ui.link("recuperation")),
        ui.card("Séance du jour", *today_blocks, open=ui.link("plan")),
    ]

    pr = service.progress(db, s)
    service.goal_track(db, s, pr)
    est, proj, probs, vma = pr["estimate"], pr["projection"], pr["probabilities"], pr["vma"]
    items = []
    if est:
        gap = est - s.goal_b
        items.append(ui.metric("10 km estimé", fmt.dur(est), f"{'+' if gap > 0 else '−'}{fmt.dur(abs(gap))} vs B",
                               sub_tone="bad" if gap > 0 else "good"))
    if proj:
        items.append(ui.metric("Projection jour J", fmt.dur(proj["projected"]), f"{fmt.dur(proj['low'])} – {fmt.dur(proj['high'])}"))
    if probs:
        items.append(ui.metric("Chances", f"A {probs.get('A', 0):.0%} · B {probs.get('B', 0):.0%}".replace("%", " %")))
    if vma.get("retenue"):
        src = {"test": "test", "cardio": "FC-vitesse", "fractionnes": "allures", "seuil": "seuil COROS"}.get(vma.get("source"), "")
        items.append(ui.metric("VMA d'entraînement", fmt.kmh(vma["retenue"]), f"{fmt.pace_km(1000 / vma['retenue'])} · {src}"))
    if items:
        blocks.append(ui.card("Objectif", ui.metrics(*items), open=ui.link("progression")))

    lm = service.load_model(db)
    now = lm["now"] or {}
    coros_load = next((d for d in reversed(db.daily()) if d.get("load_ratio")), None)
    acwr = coros_load["load_ratio"] if coros_load else now.get("acwr")
    ok = acwr is not None and acwr == acwr and 0.8 <= acwr <= 1.3
    blocks.append(ui.card("Charge", ui.metrics(
        ui.metric("Forme", fmt.num(now.get("ctl"), 0), "42 jours"),
        ui.metric("Fatigue", fmt.num(now.get("atl"), 0), "7 jours"),
        ui.metric("Fraîcheur", fmt.num(now.get("tsb"), 0), "forme − fatigue"),
        ui.metric("Ratio de charge", fmt.num(acwr, 2),
                  ("zone optimale" if ok else "à surveiller" if acwr and acwr > 1.3 else "charge basse") if acwr == acwr and acwr is not None else None,
                  sub_tone="good" if ok else "warn")), open=ui.link("charge")))

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
        blocks.append(ui.card(f"Remarques sur tes séances ({len(notes)})", ui.bullets(notes), collapsed=True))

    blocks += [ui.title("Dernières séances"), ui.rows([session_row(x) for x in recent], empty="Aucune séance sur 14 jours.")]
    blocks.append(ui.rows([ui.row("Bilan de la semaine", sub="Réalisé contre prévu, sommeil, ajustements", open=ui.link("bilan"))]))
    return ui.page("Carnet de course", *blocks, subtitle=goal_line(s))


@app.screen("bilan")
def bilan(semaine: str = ""):
    from coach import report as rpt

    s, db = ctx()
    last = rpt.ensure_last_week(db, s)
    allr = rpt.reports(db)
    weeks = sorted(allr, reverse=True)
    wk = semaine if semaine in allr else last["week"]
    r = allr[wk]
    i = weeks.index(wk)
    blocks = [
        ui.pager(f"Semaine du {fmt.day(wk)}", {"semaine": weeks[i + 1]} if i + 1 < len(weeks) else None,
                 {"semaine": weeks[i - 1]} if i > 0 else None),
        ui.metrics(ui.metric("Séances faites", f"{r['n_done']}/{r['n_planned']}"),
                   ui.metric("Kilomètres", f"{fmt.num(r['km_done'], 1)} km", f"prévu {fmt.num(r['km_planned'], 0)} km")),
        ui.card("Résumé", ui.bullets(r["summary"])),
        ui.card("Ajustements proposés", ui.bullets(r["proposals"])),
    ]
    if r.get("alerts"):
        blocks.append(ui.muted("Alertes en fin de semaine : " + " · ".join(x["title"] for x in r["alerts"])))
    blocks.append(ui.table(["Jour", "Prévu", "Réalisé", "Km"], [
        [fmt.day(d["date"]), d["planned"] or "—",
         " + ".join(x["headline"] for x in d["done"]) or ("—" if not d["planned"] or d["planned"] == "Repos" else "pas faite"),
         fmt.num(sum((x["km"] or 0) for x in d["done"]), 1) if d["done"] else ""] for d in r["days"]]))
    blocks.append(ui.button("Recalculer ce bilan", "bilan_recalculer", {"semaine": wk}, style="secondary", icon="refresh"))
    return ui.page("Bilan de la semaine", *blocks, subtitle=f"{fmt.day(r['week'])} → {fmt.day(r['end'])}")


@app.action("bilan_recalculer")
def bilan_recalculer(semaine: str):
    from coach import report as rpt
    s, db = ctx()
    rpt.regenerate(db, s, date.fromisoformat(semaine))
    return "Bilan recalculé."
