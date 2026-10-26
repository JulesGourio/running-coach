"""Charge, Progression and Historique (the matching Streamlit pages)."""
from __future__ import annotations

from datetime import date, timedelta

from appkit import Result, ui

from coach.mobile import app, ctx, fmt


@app.screen("charge")
def charge(jours: int = 90):
    from coach import service

    _, db = ctx()
    lm = service.load_model(db)
    model, weekly = lm["model"], lm["weekly"]
    if model.empty:
        return ui.page("Charge", ui.alert("info", "Pas encore de séances analysées."))
    m = model.tail(jours)
    labels = [fmt.short(d) for d in m.index]
    blocks = [
        ui.choice("jours", [(42, "42 jours"), (90, "90 jours"), (180, "180 jours")], jours),
        ui.metrics(ui.metric("Charge 7 derniers jours", fmt.num(model["load"].tail(7).sum(), 0)),
                   ui.metric("Monotonie", fmt.num(lm["monotony"], 2), "sous 2 : variée"),
                   ui.metric("Contrainte", fmt.num(lm["strain"], 0))),
        ui.chart("Forme et fatigue", labels, ui.series("Forme (6 semaines)", m["ctl"], fmt.BLUE),
                 ui.series("Fatigue (7 jours)", m["atl"], fmt.ORANGE)),
        ui.chart("Fraîcheur (forme − fatigue)", labels, ui.series("Fraîcheur", m["tsb"], fmt.BLUE, "bar"), kind="bar",
                 bands=[ui.band(-30, -10, fmt.BLUE, "productif")]),
        ui.chart("Ratio charge aiguë / chronique", labels, ui.series("Ratio", m["acwr"], fmt.BLUE),
                 bands=[ui.band(0.8, 1.3, fmt.GREEN, "optimal")], lines=[ui.hline(1.5, "excessif", fmt.RED)]),
    ]
    if not weekly.empty:
        w = weekly.tail(16)
        wl = [d.strftime("%d/%m") for d in w.index]
        blocks += [
            ui.chart("Volume par semaine (km)", wl, ui.series("km", w["km"], fmt.BLUE, "bar"), kind="bar", y="km"),
            ui.chart("Répartition de l'intensité", wl,
                     ui.series("Facile (Z1-Z2)", w["pct_low"] * 100, fmt.ZONE_COLORS["Z2 endurance"]),
                     ui.series("Tempo (Z3)", w["pct_mid"] * 100, fmt.ZONE_COLORS["Z3 tempo"]),
                     ui.series("Intense (Z4-Z5)", w["pct_high"] * 100, fmt.ZONE_COLORS["Z5 VO2max"]),
                     kind="stack", y="pct", lines=[ui.hline(80, "80 % facile", fmt.GREEN)], y_max=100),
            ui.muted("Repère : environ 80 % du temps en facile. Beaucoup de tempo (Z3) signale souvent des footings trop rapides."),
            ui.card("Données par semaine", ui.table(["Semaine", "Km", "Heures", "Charge", "Séances", "% facile", "% tempo", "% intense"], [
                [lab, fmt.num(r.km, 1), fmt.num(r.hours, 1), fmt.num(r.load, 0), int(r.sessions), fmt.pct(r.pct_low),
                 fmt.pct(r.pct_mid), fmt.pct(r.pct_high)] for lab, r in zip(wl, w.itertuples())]), collapsed=True),
        ]
    return ui.page("Charge d'entraînement", *blocks)


SOURCE_TXT = {"test": "ton test", "cardio": "la relation FC-vitesse de ta meilleure séance",
              "fractionnes": "les allures de tes fractionnés", "seuil": "ton allure seuil COROS"}
BEST_NAMES = {"400": "400 m", "1000": "1 km", "1609": "1 mile", "3000": "3 km", "5000": "5 km", "10000": "10 km", "21097": "Semi"}


@app.screen("progression")
def progression(test: str = "6min"):
    from coach import service
    from coach.metrics import progress as prog

    s, db = ctx()
    pr = service.progress(db, s)
    a, vma, est, proj = pr["athlete"], pr["vma"], pr["estimate"], pr["projection"]
    blocks = []
    if vma.get("retenue"):
        blocks.append(ui.big("VMA d'entraînement", fmt.kmh(vma["retenue"]), f"{fmt.pace_km(1000 / vma['retenue'])} · d'après "
                             + SOURCE_TXT.get(vma.get("source"), vma.get("source") or "")))
    if vma.get("source") == "test":
        blocks.append(ui.muted(f"Test du {fmt.day(vma['test']['date'])} ({vma['test']['detail']}) : il prime pendant 10 semaines."))
    else:
        blocks.append(ui.muted("Pas de test de terrain récent : estimation tirée de tes séances. Un test de 6 minutes la remplacerait."))
    if vma.get("peak") and vma.get("retenue"):
        pk = vma["peak"]["vma"]
        blocks.append(ui.alert("info", f"VMA de test progressif {fmt.kmh(pk)} : pour info seulement",
                               f"Un test par paliers finit sur un sprint. Tes 1000 m se courent vers {fmt.kmh(vma['retenue'] * 0.96)}, "
                               f"soit {vma['retenue'] * 0.96 / pk:.0%} de cette VMA : avec elle, les séances seraient trop dures.".replace("%", " %")))
    rng = vma.get("cardio_range")
    blocks.append(ui.metrics(
        ui.metric("Test de terrain", fmt.kmh(vma["test"]["vma"]), vma["test"]["detail"]) if vma.get("test") else None,
        ui.metric("FC-vitesse", fmt.kmh(vma.get("cardio")), f"{fmt.num(rng[0] * 3.6, 1)}–{fmt.num(rng[1] * 3.6, 1)} km/h" if rng else None),
        ui.metric("Allures des fractionnés", fmt.kmh(vma.get("fractionnes")), "plancher"),
        ui.metric("Seuil COROS", fmt.kmh(vma.get("seuil")), fmt.pace_km(a["threshold_pace"])),
        ui.metric("VO2max COROS", fmt.kmh(vma.get("vo2max")), "non retenue")))

    # test form: the fields depend on the kind of test
    fields = {"6min": [ui.field("distance", "Distance parcourue en 6 minutes (m)", "number", 1600)],
              "effort": [ui.field("distance", "Distance (m)", "number", 3000), ui.field("temps", "Temps (min:s ou h:min:s)", "text", "11:00")],
              "manuel": [ui.field("kmh", "VMA (km/h)", "decimal", "16,0")]}[test if test in prog.TEST_KINDS else "6min"]
    tests = list(reversed(service.vma_tests(db)))
    blocks.append(ui.card("Enregistrer un test de VMA",
                          ui.choice("test", [(k, {"6min": "6 minutes", "effort": "Effort chronométré", "manuel": "Test progressif"}[k])
                                             for k in prog.TEST_KINDS], test),
                          ui.muted(prog.TEST_KINDS.get(test, "")),
                          ui.form([ui.field("jour", "Date", "date", date.today().isoformat()), *fields], "vma_test_ajouter",
                                  args={"kind": test}),
                          ui.rows([ui.row(f"{fmt.kmh(t['vma'])}", sub=f"{fmt.day(t['date'])} · {t['detail']}",
                                          action={"name": "vma_test_supprimer", "args": {"jour": t["date"]},
                                                  "confirm": f"Supprimer le test du {fmt.day(t['date'])} ?"}, value="Supprimer")
                                   for t in tests]) if tests else None,
                          collapsed=True))

    # 10 km
    series = pr["prediction_series"]
    if series:
        labels = [fmt.short(d) for d, _ in series]
        vals = [v for _, v in series]
        lines = [ui.hline(s.goal_a, f"A {fmt.dur(s.goal_a)}", fmt.RED), ui.hline(s.goal_b, f"B {fmt.dur(s.goal_b)}", fmt.GREEN)]
        if proj and s.goal_date:
            labels.append(fmt.short(s.goal_date))
            proj_vals = [None] * (len(vals) - 1) + [vals[-1], proj["projected"]]
            vals.append(None)
            blocks.append(ui.chart("10 km : estimation et projection au jour J", labels, ui.series("Estimation (VMA)", vals, fmt.GREY),
                                   ui.series("Projection", proj_vals, fmt.BLUE, "dash"), y="time", lines=lines))
        else:
            blocks.append(ui.chart("10 km estimé", labels, ui.series("Estimation", vals, fmt.GREY), y="time", lines=lines))
    p = pr["probabilities"]
    blocks.append(ui.metrics(
        ui.metric("10 km estimé", fmt.dur(est), fmt.pace_km(est / 10) if est else None),
        ui.metric("Projection jour J", fmt.dur(proj["projected"]), f"{fmt.dur(proj['low'])} – {fmt.dur(proj['high'])}") if proj else None,
        ui.metric("Chances A", fmt.pct(p.get("A", 0)), fmt.dur(s.goal_a)) if p else None,
        ui.metric("Chances B", fmt.pct(p.get("B", 0)), fmt.dur(s.goal_b)) if p else None))
    if pr["predictions"]:
        blocks.append(ui.table(["Méthode", "10 km", "Allure"], [[k, fmt.dur(v), fmt.pace_km(v / 10)] for k, v in pr["predictions"].items()]))

    allp = service.predictions_all(db, s, pr)
    if allp:
        blocks.append(ui.card("Toutes les distances", ui.table(["Distance", "Estimation", "Allure", "Record"], [
            [r["distance"], fmt.dur(r["estimate"]) if r["estimate"] else "—", fmt.pace_km(r["pace"]) if r["pace"] else "—",
             f"{fmt.dur(r['real']['time'])} ({fmt.short(r['real']['date'])})" if r["real"] else "—"] for r in allp]),
            ui.muted("Au-delà du 10 km, l'endurance compte autant que la VMA : ton record sert de repère.")))

    track = service.goal_track(db, s, pr)
    if len(track) >= 2:
        blocks.append(ui.chart("Chances d'atteindre chaque objectif (%)", [fmt.short(r["week"]) for r in track],
                               ui.series(f"A ({fmt.dur(s.goal_a)})", [(r["A"] or 0) * 100 for r in track], fmt.RED),
                               ui.series(f"B ({fmt.dur(s.goal_b)})", [(r["B"] or 0) * 100 for r in track], fmt.GREEN),
                               y="pct", y_min=0, y_max=100))

    trend = [r for r in pr.get("rep_trend") or [] if not r["category"].startswith("Sortie longue")]
    if trend:
        cats = sorted({r["category"] for r in trend})
        dates = sorted({r["date"] for r in trend})
        by = {(r["category"], r["date"]): r["pace"] for r in trend}
        blocks.append(ui.chart("Allure médiane des répétitions, par type", [fmt.short(d) for d in dates],
                               *[ui.series(c, [by.get((c, d)) for d in dates], fmt.type_color(c), "points") for c in cats],
                               y="pace", reverse=True))

    v_ref = vma.get("retenue")
    if v_ref:
        vp = 1000 / v_ref
        rows = [("VMA courte (200-400 m, 30/30)", vp / 1.07, vp / 1.03), ("VMA longue (800-1200 m)", vp / 1.00, vp / 0.96),
                ("Allure 10 km actuelle", est / 10 if est else None, None),
                ("Objectifs A / B", s.goal_a / 10 if s.goal_a else None, s.goal_b / 10 if s.goal_b else None),
                ("Seuil (~1 h)", a["threshold_pace"] - 5, a["threshold_pace"] + 5)]
        blocks.append(ui.card("Tes allures d'entraînement", ui.table(["Allure", "min/km"], [
            [n, (fmt.pace(lo) + (f" – {fmt.pace(hi)}" if hi else "")) if lo else "—"] for n, lo, hi in rows]),
            ui.rows([ui.row("Toutes les séances types", open=ui.link("seances_types"))])))

    be = pr["best_efforts"]
    if be:
        blocks.append(ui.card("Meilleurs efforts (90 jours)", ui.table(["Distance", "Temps", "Allure", "Date"], [
            [BEST_NAMES.get(k, k), fmt.dur(t), fmt.pace_km(t / (int(k) / 1000)), fmt.short(d)]
            for k, (t, d) in sorted(be.items(), key=lambda kv: int(kv[0]))]), collapsed=True))
    blocks.append(ui.muted(f"Profil : FC max {a['hr_max']:.0f} · repos {a['hr_rest']:.0f} · seuil {a['lt_hr']:.0f} bpm · "
                           f"allure seuil {fmt.pace_km(a['threshold_pace'])}"))
    blocks.append(_zones(service.athlete(db, s)))
    return ui.page("Progression", *blocks)


def _zones(a) -> dict:
    hr_b, pace_b = a.hr_zone_bounds(), a.pace_zone_bounds()
    rows = []
    for i, ((name, hlo, hhi), (_, plo, phi)) in enumerate(zip(hr_b, pace_b)):
        if i == 0:
            h, p = f"< {hhi:.0f}", f"> {fmt.pace(plo)}"
        elif i == len(hr_b) - 1:
            h, p = f"> {hlo:.0f}", f"< {fmt.pace(phi)}"
        else:
            h, p = f"{hlo:.0f}–{hhi:.0f}", f"{fmt.pace(plo)}–{fmt.pace(phi)}"
        rows.append([name, h, p])
    return ui.card("Zones", ui.table(["Zone", "FC (bpm)", "Allure"], rows,
                                     tones=[[fmt.ZONE_COLORS.get(r[0]), None, None] for r in rows]),
                   ui.muted("Repère : ~80 % du temps en Z1-Z2."), collapsed=True)


@app.action("vma_test_ajouter")
def vma_test_ajouter(kind: str, jour: str = "", distance: str = "", temps: str = "", kmh: str = ""):
    from coach import service
    from coach.metrics import progress as prog

    s, db = ctx()
    d = date.fromisoformat(jour) if jour else date.today()
    if d > date.today():
        raise ValueError("Date dans le futur.")
    if kind == "6min":
        dist = int(float(distance.replace(",", ".")))
        v, detail = prog.vma_from_test("6min", distance_m=dist), f"test 6 min, {dist} m"
    elif kind == "effort":
        dist = int(float(distance.replace(",", ".")))
        secs = fmt.parse_clock(temps)
        if not secs:
            raise ValueError("Temps au format 11:00 ou 1:05:30.")
        v, detail = prog.vma_from_test("effort", distance_m=dist, time_s=secs), f"{dist} m en {temps}"
    else:
        k = float(kmh.replace(",", "."))
        v, detail = prog.vma_from_test("manuel", kmh=k), f"VMA saisie {fmt.num(k, 1)} km/h"
    service.add_vma_test(db, d.isoformat(), kind, v, detail)
    return Result(message=f"VMA {fmt.kmh(v)} enregistrée, 10 km estimé {fmt.dur(prog.predict_from_vma(v, s.goal_distance_m))}.")


@app.action("vma_test_supprimer")
def vma_test_supprimer(jour: str):
    from coach import service
    _, db = ctx()
    service.delete_vma_test(db, jour)
    return "Test supprimé."


HIST_PERIODS = [(30, "30 j"), (91, "3 mois"), (182, "6 mois"), (365, "1 an"), (730, "2 ans"), (0, "Tout")]


@app.screen("historique")
def historique(periode: int = 91, sport: str = "run"):
    from coach import history as hist

    _, db = ctx()
    today = date.today()
    df = hist.frame(db, "run" if sport == "run" else "all")
    head = [ui.choice("sport", [("run", "Course à pied"), ("all", "Tous les sports")], sport),
            ui.choice("periode", HIST_PERIODS, periode)]
    if df.empty:
        return ui.page("Historique", *head, ui.alert("info", "Aucune séance", "Lance « Tout l'historique COROS » plus bas."),
                       _history_button())
    rec = hist.records(df)
    start = today - timedelta(days=periode) if periode else rec["first"]
    cur, prev = hist.totals(df, start, today), hist.totals(df, *hist.previous(start, today))

    def delta(a, b, unit="", dec=0):
        return f"{a - b:+.{dec}f}{unit} vs avant".replace(".", ",") if periode and b else None

    blocks = [*head, ui.muted(f"Du {fmt.day(start)} à aujourd'hui · compte COROS depuis le {fmt.day(rec['first'])} · "
                             f"{fmt.num(rec['total_km'], 0)} km en {rec['total_sessions']} sorties au total"),
              ui.metrics(ui.metric("Distance", f"{fmt.num(cur['km'], 0)} km", delta(cur["km"], prev["km"], " km")),
                         ui.metric("Sorties", str(cur["sessions"]), delta(cur["sessions"], prev["sessions"])),
                         ui.metric("Temps", f"{fmt.num(cur['hours'], 0)} h", delta(cur["hours"], prev["hours"], " h")),
                         ui.metric("Par semaine", f"{fmt.num(cur['km_week'], 1)} km", f"{fmt.num(cur['sessions_week'], 1)} sorties"),
                         ui.metric("Allure moyenne", fmt.pace_km(cur["pace"]) if cur["pace"] else "—", "route, piste, tapis"),
                         ui.metric("Plus longue", f"{fmt.num(cur['longest']['distance_km'], 1)} km",
                                   fmt.day(cur["longest"]["date"].date())) if cur["longest"] else None)]

    w = hist.window(df, start, today)
    freq = "W" if (today - start).days <= 400 else "M"
    vol = hist.volume(w, freq)
    if len(vol):
        order = sorted(vol.columns, key=lambda c: (c in ("Non analysée", "Trail"), c))
        blocks.append(ui.chart(f"Kilomètres par {'semaine' if freq == 'W' else 'mois'}",
                               [d.strftime("%d/%m" if freq == "W" else "%m/%y") for d in vol.index],
                               *[ui.series(c, vol[c], "#cbd5e1" if c == "Non analysée" else "#0f766e" if c == "Trail" else fmt.type_color(c))
                                 for c in order], kind="stack", y="km"))
    if sport == "all" and len(w):
        by = w.groupby("sport").agg(n=("label_id", "count"), h=("hours", "sum"), km=("distance_km", "sum"))
        blocks.append(ui.table(["Sport", "Séances", "Heures", "Km"],
                               [[i, int(r.n), fmt.num(r.h, 1), fmt.num(r.km, 0)] for i, r in by.iterrows()]))

    yr = hist.per_year(df)
    blocks += [ui.title("Depuis le début"),
               ui.chart("Kilomètres par année", [str(y) for y in yr["year"]], ui.series("km", yr["km"], fmt.BLUE, "bar"), kind="bar", y="km"),
               ui.table(["Année", "Km", "Sorties", "Heures", "Plus longue", "Allure (route)"], [
                   [str(r.year), fmt.num(r.km, 0), int(r.sessions), fmt.num(r.hours, 0), f"{fmt.num(r.longest, 1)} km",
                    fmt.pace_km(r.pace) if r.pace == r.pace and r.pace else "—"] for r in yr.itertuples()])]
    lg = rec["longest"]
    blocks.append(ui.metrics(ui.metric("Plus longue sortie", f"{fmt.num(lg['distance_km'], 1)} km", fmt.day(lg["date"].date())),
                             ui.metric("Plus grosse semaine", f"{fmt.num(rec['best_week'][1], 0)} km", f"du {fmt.day(rec['best_week'][0])}"),
                             ui.metric("Plus gros mois", f"{fmt.num(rec['best_month'][1], 0)} km", rec["best_month"][0].strftime("%m/%Y"))))
    recs, n_fit, n_runs = hist.personal_records(db)
    if recs:
        blocks.append(ui.card("Records personnels", ui.table(["Distance", "Temps", "Allure", "Date"], [
            [r["distance"], fmt.dur(r["time"]), fmt.pace_km(r["time"] / (r["meters"] / 1000)), fmt.day(r["date"])] for r in recs]),
            ui.muted(f"Sur les {n_fit} sorties dont le fichier FIT est téléchargé (sur {n_runs}). Trail exclu.")))
    blocks.append(_history_button())
    return ui.page("Historique", *blocks)


def _history_button() -> dict:
    return ui.button("Tout l'historique COROS", "historique_coros", style="secondary", icon="history",
                     confirm="Récupérer les résumés de toutes les séances et nuits depuis l'ouverture du compte ? "
                             "Les fichiers détaillés arrivent ensuite au fil des synchros (50 par jour).")


@app.action("historique_coros")
def historique_coros():
    import asyncio

    from coach.sync import sync_history
    s, db = ctx()
    lines: list[str] = []
    asyncio.run(sync_history(s, db, days=3650, log=lines.append))
    return " ".join(lines) or "Historique récupéré."
