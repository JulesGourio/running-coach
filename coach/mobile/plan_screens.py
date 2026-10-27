"""Plan (week view, pending changes sent to COROS after confirmation, suggestions, drafts and the generator),
one day's editor, the workout library and the race-day plan. Same rules as the dashboard: past or completed
days never change, paces stay between 120 and 1499 s/km (`plan_edit.validate`)."""
from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta

from appkit import Result, ui

from coach import plan_edit as pe
from coach.mobile import app, ctx, fmt

# ---- pending changes, kept in the database between screens ----------------------------------------------------


def _plan_id(db) -> str | None:
    return (json.loads(db.get_meta("plan") or "null") or {}).get("id")


def pending_get(db) -> dict:
    """The queued changes (by date), only for the plan they were made on: a change of plan drops them,
    since their day numbers would point at other days."""
    d = json.loads(db.get_meta("mobile_pending_plan") or "{}")
    if not d.get("changes") or d.get("plan_id") != _plan_id(db):
        return {}
    return d["changes"]


def pending_save(db, pending: dict) -> None:
    db.set_meta("mobile_pending_plan", json.dumps({"plan_id": _plan_id(db), "changes": pending}))


def fingerprint(pending: dict) -> str:
    """What the confirmation showed: sending refuses if the queue changed since."""
    import hashlib
    items = sorted((c["date"], json.dumps(c["after"], sort_keys=True)) for c in pending.values())
    return hashlib.sha1(json.dumps(items).encode()).hexdigest()[:16]


def queue(db, changes: list[dict]) -> int:
    pending = pending_get(db)
    for ch in changes:
        pe.queue_change(pending, ch)
    pending_save(db, pending)
    return len(pending)


def effective(day: dict, pending: dict) -> list[dict]:
    ch = pending.get(day["date"])
    return [c for c in ch["after"] if c.get("sportType") != 4] if ch else pe.day_courses(day)


def editable(day: dict | None) -> bool:
    return bool(day) and day["date"] >= date.today().isoformat() and not pe.day_is_done(day)


def kind_label(courses: list[dict], a) -> str:
    from coach.verdict import TYPE_FR, classify
    c = next((x for x in courses if x.get("sportType") != 4), None)
    if not c:
        return "Repos"
    k = classify(c, {}, a)
    return TYPE_FR.get(k, k)


def _stored(db, plan: dict) -> dict:
    return {d["date"]: d for d in db.plan_days(plan["start"], plan["end"])}


# ---- the plan screen ----------------------------------------------------------------------------------------

@app.screen("plan")
def plan(vue: str = "principal", semaine: int | None = None):
    from coach import plan_builder as pb
    _, db = ctx()
    drafts = pb.drafts(db)
    options = [("principal", "Plan COROS"), *[(d["id"], d["params"]["name"]) for d in drafts], ("nouveau", "+ Nouveau")]
    head = ui.choice("vue", options, vue if vue in {o[0] for o in options} else "principal")
    if vue == "nouveau":
        return ui.page("Nouveau plan", head, *_generator())
    draft = next((d for d in drafts if d["id"] == vue), None)
    if draft:
        return ui.page(draft["params"]["name"], head, *_draft_view(draft, semaine or 0))
    return _main_plan(head, semaine)


def _main_plan(head: dict, semaine: int | None):
    from coach import service
    from coach.text import course_text

    s, db = ctx()
    a = service.athlete(db, s)
    today = date.today()
    plan = json.loads(db.get_meta("plan") or "null")
    if not plan:
        return ui.page("Plan", head, ui.alert("info", "Aucun plan COROS synchronisé"),
                       ui.button("Charger le plan depuis COROS", "plan_recharger", icon="download"))
    pending = pending_get(db)
    start, end = date.fromisoformat(plan["start"]), date.fromisoformat(plan["end"])
    n_weeks = plan.get("weeks") or (end - start).days // 7 + 1
    phases = json.loads(db.get_meta("phases") or "[]")
    stored = _stored(db, plan)
    before = 8
    cur_week = min(max((today - start).days // 7, -before), n_weeks - 1)
    week = cur_week if semaine is None else max(-before, min(n_weeks - 1, semaine))

    blocks = [head, ui.muted(f"{plan['name']} · du {fmt.day(start)} au {fmt.day(end)}"
                             + (" · " + " → ".join(f"{p['name']} ({p['weeks']} sem.)" for p in phases) if phases else ""))]
    if pending:
        changes = sorted(pending.values(), key=lambda c: c["date"])
        blocks.append(ui.card(f"Modifications en attente ({len(changes)})",
                              ui.table(["Jour", "Avant", "Après", "Raison"],
                                       [[fmt.day(c["date"]), pe.describe(c["before"]), pe.describe(c["after"]), c["reason"]] for c in changes]),
                              ui.buttons(ui.button("Envoyer sur COROS", "plan_envoyer", {"empreinte": fingerprint(pending)}, icon="upload",
                                                   confirm=f"{len(changes)} jour(s) vont être réécrits dans ton plan COROS (et sur ta montre) :\n"
                                                           + "\n".join(f"• {fmt.day(c['date'])} : {pe.describe(c['after'])}" for c in changes)
                                                           + "\nLes jours déjà réalisés ne sont jamais modifiés."),
                                         ui.button("Tout annuler", "plan_annuler_tout", style="secondary", confirm="Annuler toutes les modifications ?")),
                              tone="warn"))
    for i, sg in enumerate(pe.suggestions(db, s)):
        blocks.append(ui.card(sg["title"], ui.muted(sg["why"]),
                              ui.button("Proposer", "plan_suggestion", {"index": i, "titre": sg["title"]}, style="secondary"), tone="info"))

    # volume per week, before the plan and during it
    weeks = list(range(-before, n_weeks))
    hist_acts = service.sessions_between(db, (start - timedelta(weeks=before)).isoformat(), end.isoformat())
    done_w, plan_w = {}, {}
    for x in hist_acts:
        i = (date.fromisoformat(x["date"]) - start).days // 7
        done_w[i] = done_w.get(i, 0) + (x.get("distance_km") or 0)
    for k, dy in stored.items():
        i = (date.fromisoformat(k) - start).days // 7
        plan_w[i] = plan_w.get(i, 0) + sum(pe.course_km(c) for c in effective(dy, pending))
    blocks.append(ui.chart("Volume par semaine : réalisé et prévu (km)", [f"S{i + 1}" if i >= 0 else str(i) for i in weeks],
                           ui.series("Réalisé", [done_w.get(i, 0) for i in weeks], fmt.BLUE, "bar"),
                           ui.series("Prévu", [plan_w.get(i) if i >= 0 else None for i in weeks], fmt.GREY, "dash"),
                           kind="bar", y="km", highlight=weeks.index(cur_week)))

    ws = start + timedelta(weeks=week)
    we = ws + timedelta(days=6)
    dates = [ws + timedelta(days=i) for i in range(7)]
    phase = next((p["name"] for p in phases if p["start"] <= ws.isoformat() <= p["end"]), "")
    label = (f"Semaine {week + 1}" + (f" · {phase}" if phase else "")) if week >= 0 else f"{abs(week)} sem. avant le plan"
    blocks.append(ui.pager(label + (" (en cours)" if week == cur_week else ""), {"semaine": week - 1} if week > -before else None,
                           {"semaine": week + 1} if week < n_weeks - 1 else None))
    done_by_day: dict[str, list] = {}
    for x in service.sessions_between(db, ws.isoformat(), we.isoformat()):
        done_by_day.setdefault(x["date"], []).append(x)
    eff = {d.isoformat(): effective(stored[d.isoformat()], pending) if d.isoformat() in stored else [] for d in dates}
    planned_km = sum(pe.course_km(c) for cs in eff.values() for c in cs)
    done_km = sum(x.get("distance_km") or 0 for xs in done_by_day.values() for x in xs)
    n_planned = sum(1 for cs in eff.values() if cs)
    n_done = sum(1 for k, cs in eff.items() if cs and done_by_day.get(k))
    blocks.append(ui.metrics(ui.metric("Prévu", f"{fmt.num(planned_km, 0)} km") if week >= 0 else None,
                             ui.metric("Réalisé", f"{fmt.num(done_km, 1)} km",
                                       f"{done_km - planned_km:+.1f} km".replace(".", ",") if week >= 0 and ws <= today else None),
                             ui.metric("Séances faites", f"{n_done}/{n_planned}") if week >= 0 else None))

    for d in dates:
        k = d.isoformat()
        day, done, courses = stored.get(k), done_by_day.get(k, []), eff.get(k, [])
        parts = []
        if not day:
            parts.append(ui.muted("Avant le plan" if d < start else "Non synchronisé"))
        else:
            if courses:
                parts.append(ui.text(f"**Prévu** · ≈ {fmt.num(sum(pe.course_km(c) for c in courses), 1)} km"
                                     + (" · en attente" if k in pending else "")))
                parts += [ui.muted(f"{c['courseName']} · {course_text(c)}") for c in courses]
            else:
                parts.append(ui.text("**Repos**" + (" · en attente" if k in pending else "")))
            if k in pending:
                parts.append(ui.muted(f"Avant : {pe.describe(pending[k]['before'])}"))
        if done:
            for x in done:
                bits = [f"{fmt.num(x['distance_km'], 1)} km", fmt.dur(x.get("duration_s")) if x.get("duration_s") else None,
                        fmt.pace_km(x["avg_pace"]) if x.get("avg_pace") else None,
                        f"respect {fmt.num(x['score'])}/10" if x.get("score") is not None else None]
                parts.append(ui.rows([ui.row(f"Réalisé : {x.get('structure') or x.get('kind_fr') or x.get('name') or ''}",
                                             sub=" · ".join(b for b in bits if b), badge=fmt.type_badge(x.get("kind_fr")),
                                             open=ui.link("seance", label_id=x["label_id"]))]))
        elif courses and d < today:
            parts.append(ui.text("Pas faite", "muted"))
        title = ("Aujourd'hui · " if d == today else "") + fmt.day(d)
        tone = "warn" if k in pending else ("info" if d == today else None)
        blocks.append(ui.card(title, *parts, tone=tone, open=ui.link("plan_jour", jour=k) if day and editable(day) else None))

    blocks.append(ui.card("Ajuster plusieurs séances d'un coup", ui.form([
        ui.field("portee", "Portée", "select", "semaine", [("semaine", "Cette semaine"), ("restantes", "Toutes les semaines restantes")]),
        ui.field("qualite", "Seulement les séances de qualité", "toggle", False),
        ui.field("volume", "Volume (%)", "number", 100, help="50 à 150 : distances, durées et répétitions"),
        ui.field("allures", "Allures de qualité (s/km, négatif = plus vite)", "number", 0, help="-15 à +15")],
        "plan_ajuster_lot", "Ajouter aux modifications", args={"semaine": week}), collapsed=True))
    hist = db.plan_changes(30)
    if hist:
        blocks.append(ui.card(f"Historique des modifications ({len(hist)})", ui.table(["Envoyée le", "Jour", "Après", "Raison", "Statut"], [
            [h["created_at"][:16].replace("T", " "), fmt.day(h["date"]), pe.describe(h["after"]), h["reason"], h["status"]] for h in hist]),
            collapsed=True))
    blocks.append(ui.button("Recharger le plan depuis COROS", "plan_recharger", style="secondary", icon="refresh"))
    return ui.page("Plan", *blocks)


def _client_run(fn):
    from coach.sources import coros

    async def run():
        s, _ = ctx()
        async with coros.client(s) as c:
            return await fn(c)
    return asyncio.run(run())


@app.action("plan_recharger")
def plan_recharger():
    from coach.sync import refresh_plan
    _, db = ctx()
    plan = _client_run(lambda c: refresh_plan(c, db))
    return "Plan rechargé depuis COROS." if plan else "Aucun plan en cours dans COROS."


@app.action("plan_envoyer")
def plan_envoyer(empreinte: str = ""):
    """Send what the confirmation listed, after checking each day against the plan as stored now: a day that
    became past or done, or that changed since it was queued (Claude, the PC, COROS), is left out."""
    s, db = ctx()
    pending = pending_get(db)
    if not pending:
        raise ValueError("Aucune modification en attente (le plan a peut-être changé) : recharge l'écran.")
    if empreinte != fingerprint(pending):
        raise ValueError("Les modifications en attente ont changé depuis l'affichage : vérifie-les puis renvoie.")
    send, dropped = [], []
    for ch in sorted(pending.values(), key=lambda c: c["date"]):
        day = next(iter(db.plan_days(ch["date"], ch["date"])), None)
        if not editable(day):
            dropped.append(f"{fmt.day(ch['date'])} (passé ou réalisé)")
        elif pe.day_courses(day) != ch["before"]:
            dropped.append(f"{fmt.day(ch['date'])} (modifié ailleurs entre-temps)")
        else:
            send.append({**ch, "day_no": day["day_no"]})
    msg = ""
    if send:
        res = asyncio.run(pe.push_changes(s, db, send))
        msg = f"Plan mis à jour dans COROS : {len(res['applied'])} jour(s) modifié(s)."
        if res["skipped"]:
            msg += f" {len(res['skipped'])} jour(s) déjà réalisé(s) laissé(s) tel(s) quel(s)."
    pending_save(db, {})
    if dropped:
        msg += (" " if msg else "") + "Non envoyés : " + ", ".join(dropped) + "."
    return msg


@app.action("plan_annuler_tout")
def plan_annuler_tout():
    _, db = ctx()
    pending_save(db, {})
    return "Modifications annulées."


@app.action("plan_suggestion")
def plan_suggestion(index: int, titre: str = ""):
    s, db = ctx()
    sugg = pe.suggestions(db, s)
    sg = sugg[index] if 0 <= index < len(sugg) else None
    if sg is None or (titre and sg["title"] != titre):
        raise ValueError("Les suggestions ont changé : recharge l'écran.")
    n = queue(db, sg["changes"])
    return f"Ajoutée aux modifications en attente ({n}). Vérifie puis envoie sur COROS."


@app.action("plan_ajuster_lot")
def plan_ajuster_lot(semaine: int = 0, portee: str = "semaine", qualite: bool = False, volume: int = 100, allures: int = 0):
    from coach import service
    s, db = ctx()
    a = service.athlete(db, s)
    if not 50 <= volume <= 150 or not -15 <= allures <= 15:
        raise ValueError("Volume entre 50 et 150 %, allures entre -15 et +15 s/km.")
    if volume == 100 and allures == 0:
        raise ValueError("Rien à changer : volume 100 % et allures 0.")
    plan = json.loads(db.get_meta("plan") or "null")
    if not plan:
        raise ValueError("Aucun plan COROS synchronisé.")
    pending = pending_get(db)
    stored = _stored(db, plan)
    ws = date.fromisoformat(plan["start"]) + timedelta(weeks=semaine)
    pool = ([stored[(ws + timedelta(days=i)).isoformat()] for i in range(7) if (ws + timedelta(days=i)).isoformat() in stored]
            if portee == "semaine" else [d for _, d in sorted(stored.items())])
    future = [dy for dy in pool if editable(dy) and effective(dy, pending)
              and (not qualite or any(pe.is_quality_course(c, a.threshold_pace) for c in effective(dy, pending)))]
    if not future:
        raise ValueError("Aucune séance modifiable dans cette portée.")
    why = ", ".join(([f"volume {volume} %"] if volume != 100 else []) + ([f"allures {allures:+d} s/km"] if allures else []))
    changes = [pe.make_change(dy, [pe.shift_paces(pe.scale(c, volume / 100), allures, a.threshold_pace) for c in effective(dy, pending)],
                              f"{'Semaine' if portee == 'semaine' else 'Plan'} ajusté : {why}") for dy in future]
    n = queue(db, changes)
    return f"{len(changes)} séance(s) ajustée(s), {n} modification(s) en attente."


# ---- one day ------------------------------------------------------------------------------------------------

DEFAULT_TPL = {"Footing": "footing", "Sortie longue": "longue", "Sortie longue avec allure spécifique": "longue_allure",
               "VMA / VO2max": "vma", "Seuil": "seuil", "Allure spécifique": "allure"}


def _paces(db, s):
    from coach import service
    a = service.athlete(db, s)
    vma = service.progress(db, s)["vma"].get("retenue")
    return a, vma, pe.default_paces(a, vma, s.goal_a, s.goal_b)


def _template_fields(tpl: str, P: dict, km_now: float) -> list[dict]:
    def pp(name: str, label: str, pr: tuple) -> list[dict]:
        show = lambda v: fmt.pace(v) if isinstance(v, (int, float)) else ""  # noqa: E731
        return [ui.field(f"{name}_de", f"{label} : de (min:s/km)", "text", show(pr[0])),
                ui.field(f"{name}_a", "à (min:s/km)", "text", show(pr[1]))]
    if tpl in ("footing", "footing_acc"):
        f = [ui.field("km", "Distance (km)", "decimal", fmt.num(km_now if 5 <= km_now <= 16 else 9, 1)), *pp("allure", "Allure", P["easy"])]
        return f + ([ui.field("strides", "Accélérations de 100 m", "number", 6)] if tpl == "footing_acc" else [])
    if tpl == "vma":
        return [ui.field("reps", "Répétitions", "number", 8),
                ui.field("rep_m", "Distance de chaque répétition", "select", 400, [(m, f"{m} m") for m in (200, 300, 400, 500, 600, 800, 1000, 1200, 1500)]),
                *pp("allure", "Allure (vide : selon la distance)", ("", "")),
                ui.field("rec", "Récupération trottée", "number", 200), ui.field("rec_unit", "en", "select", "m", [("m", "mètres"), ("s", "secondes")])]
    if tpl == "allure":
        return [ui.field("reps", "Répétitions", "number", 4),
                ui.field("rep_m", "Distance (m)", "select", 2000, [(m, f"{m} m") for m in (1000, 1500, 2000, 2500, 3000, 4000)]),
                *pp("allure", "Allure objectif", P["allure"]), ui.field("rec", "Récupération trottée (s)", "number", 120)]
    if tpl == "seuil":
        return [ui.field("blocks", "Blocs", "number", 2), ui.field("block_min", "Minutes par bloc", "number", 15),
                *pp("allure", "Allure seuil", P["seuil"]), ui.field("rec", "Récupération entre blocs (s)", "number", 180)]
    if tpl == "longue":
        return [ui.field("km", "Distance (km)", "decimal", fmt.num(km_now if km_now >= 12 else 16, 1)),
                *pp("allure", "Allure", (P["easy"][0], P["easy"][1] - 5))]
    if tpl == "longue_allure":
        return [ui.field("km", "Distance totale (km)", "decimal", fmt.num(km_now if km_now >= 12 else 18, 1)),
                ui.field("fast_km", "dont en allure (km)", "decimal", "5"), *pp("allure", "Allure de la partie rapide", P["allure"])]
    return []


def _pace_pair(v: dict, default: tuple) -> tuple[int, int]:
    lo, hi = v.get("allure_de", ""), v.get("allure_a", "")
    if not str(lo).strip() and not str(hi).strip():
        return int(default[0]), int(default[1])
    a, b = fmt.parse_clock(lo), fmt.parse_clock(hi)
    if a is None or b is None or not (120 <= a <= 1499 and 120 <= b <= 1499):
        raise ValueError("Allure au format 4:05, entre 2:00 et 24:59/km.")
    return int(min(a, b)), int(max(a, b))


def _f(v, default: float) -> float:
    return float(str(v).replace(",", ".")) if str(v).strip() else default


def _template_params(tpl: str, v: dict, P: dict, vma: float | None, a) -> dict:
    if tpl == "repos":
        return {}
    if tpl == "test_vma":
        vv = vma or 1000 / a.threshold_pace / 0.87
        return {"easy": P["easy"], "vma_guess": (round(1000 / (vv * 1.06)), round(1000 / (vv * 0.97)))}
    if tpl in ("footing", "footing_acc"):
        p = {"km": _f(v.get("km"), 9), "easy": _pace_pair(v, P["easy"])}
        if tpl == "footing_acc":
            p["strides"] = int(_f(v.get("strides"), 6))
        return p
    if tpl == "vma":
        rep_m = int(_f(v.get("rep_m"), 400))
        unit = v.get("rec_unit") or "m"
        return {"reps": int(_f(v.get("reps"), 8)), "rep_m": rep_m,
                "pace": _pace_pair(v, P["vma_short"] if rep_m <= 500 else P["vma_long"]),
                "rec": int(_f(v.get("rec"), 200 if unit == "m" else 90)), "rec_unit": unit, "easy": P["easy"]}
    if tpl == "allure":
        return {"reps": int(_f(v.get("reps"), 4)), "rep_m": int(_f(v.get("rep_m"), 2000)), "pace": _pace_pair(v, P["allure"]),
                "rec": int(_f(v.get("rec"), 120)), "rec_unit": "s", "easy": P["easy"]}
    if tpl == "seuil":
        blocks = int(_f(v.get("blocks"), 2))
        return {"blocks": blocks, "block_min": int(_f(v.get("block_min"), 15)), "pace": _pace_pair(v, P["seuil"]),
                "rec": int(_f(v.get("rec"), 180)) if blocks > 1 else 0, "easy": P["easy"]}
    if tpl == "longue":
        return {"km": _f(v.get("km"), 16), "easy": _pace_pair(v, (P["easy"][0], P["easy"][1] - 5))}
    if tpl == "longue_allure":
        return {"km": _f(v.get("km"), 18), "fast_km": _f(v.get("fast_km"), 5), "pace": _pace_pair(v, P["allure"]), "easy": P["easy"]}
    raise ValueError(f"type de séance inconnu : {tpl}")


def _day(db, jour: str) -> dict:
    day = next(iter(db.plan_days(jour, jour)), None)
    if not day:
        raise ValueError("Jour absent du plan synchronisé.")
    if not editable(day):
        raise ValueError("Jour passé ou déjà réalisé : non modifiable.")
    return day


@app.screen("plan_jour")
def plan_jour(jour: str, modele: str = ""):
    from coach.text import course_text
    s, db = ctx()
    day = next(iter(db.plan_days(jour, jour)), None)
    if not day:
        return ui.page("Séance du plan", ui.alert("bad", "Jour absent du plan synchronisé."))
    pending = pending_get(db)
    a, vma, P = _paces(db, s)
    cur = effective(day, pending)
    blocks = [ui.text(f"{fmt.type_badge(kind_label(cur, a))['text']} · {pe.describe(cur)}")]
    blocks += [ui.muted(f"{c['courseName']} · {course_text(c)}") for c in cur]
    if jour in pending:
        blocks.append(ui.alert("warn", "Modification en attente", f"Avant : {pe.describe(pending[jour]['before'])}"))
        blocks.append(ui.button("Annuler la modification", "plan_jour_annuler", {"jour": jour}, style="secondary"))
    if not editable(day):
        return ui.page(fmt.day(jour), *blocks, ui.muted("Jour passé ou déjà réalisé : non modifiable."))
    if cur:
        blocks.append(ui.card("Ajuster", ui.form([
            ui.field("volume", "Volume (%)", "number", 100, help="Distances, durées, répétitions. Échauffement et retour au calme ne changent pas."),
            ui.field("allures", "Allures de qualité (s/km, négatif = plus vite)", "number", 0)],
            "plan_jour_ajuster", "Ajouter aux modifications", args={"jour": jour})))
    keys = list(pe.TEMPLATES)
    tpl = modele if modele in keys else DEFAULT_TPL.get(kind_label(cur, a), "footing")
    km_now = round(sum(pe.course_km(c) for c in cur))
    blocks.append(ui.card("Remplacer par", ui.choice("modele", [(k, pe.TEMPLATES[k]) for k in keys], tpl),
                          ui.muted("Test VMA : échauffement 20 min, 4 accélérations, 6 minutes à fond, retour au calme. "
                                   "Saisis ensuite la distance dans Progression.") if tpl == "test_vma" else None,
                          ui.form(_template_fields(tpl, P, km_now), "plan_jour_remplacer", "Ajouter aux modifications",
                                  args={"jour": jour, "modele": tpl})))
    d0 = date.fromisoformat(jour)
    plan = json.loads(db.get_meta("plan") or "null") or {"start": jour, "end": jour}
    others = [d for k, d in sorted(_stored(db, plan).items()) if k != jour and editable(d) and abs((date.fromisoformat(k) - d0).days) <= 10]
    if others:
        blocks.append(ui.card("Échanger avec un autre jour", ui.form([
            ui.field("autre", "Jour", "select", others[0]["date"],
                     [(d["date"], f"{fmt.day(d['date'])} · {pe.describe(effective(d, pending))}") for d in others])],
            "plan_jour_echanger", "Échanger les deux jours", args={"jour": jour}), collapsed=True))
    return ui.page(fmt.day(jour), *blocks, subtitle="Modifier la séance")


@app.action("plan_jour_ajuster")
def plan_jour_ajuster(jour: str, volume: int = 100, allures: int = 0):
    s, db = ctx()
    a, _, _ = _paces(db, s)
    if not 50 <= volume <= 150 or not -15 <= allures <= 15:
        raise ValueError("Volume entre 50 et 150 %, allures entre -15 et +15 s/km.")
    if volume == 100 and allures == 0:
        raise ValueError("Rien à changer.")
    day = _day(db, jour)
    cur = effective(day, pending_get(db))
    new = [pe.shift_paces(pe.scale(c, volume / 100), allures, a.threshold_pace) for c in cur]
    why = ", ".join(([f"volume {volume} %"] if volume != 100 else []) + ([f"allures {allures:+d} s/km"] if allures else []))
    n = queue(db, [pe.make_change(day, new, "Ajustement : " + why)])
    return Result(message=f"Ajoutée aux modifications en attente ({n}).", back=True)


@app.action("plan_jour_remplacer")
def plan_jour_remplacer(jour: str, modele: str, **valeurs):
    s, db = ctx()
    a, vma, P = _paces(db, s)
    day = _day(db, jour)
    try:
        new = pe.build(modele, _template_params(modele, valeurs, P, vma, a))
    except (pe.PlanError, KeyError) as e:
        raise ValueError(str(e)) from e
    errs = pe.validate(new)
    if errs:
        raise ValueError(" ; ".join(errs))
    n = queue(db, [pe.make_change(day, [] if new.get("sportType") == 4 else [new], f"Remplacée : {pe.TEMPLATES[modele]}")])
    return Result(message=f"Ajoutée aux modifications en attente ({n}).", back=True)


@app.action("plan_jour_echanger")
def plan_jour_echanger(jour: str, autre: str):
    _, db = ctx()
    a_day, b_day = _day(db, jour), _day(db, autre)
    pending = pending_get(db)
    ca, cb = effective(a_day, pending), effective(b_day, pending)
    n = queue(db, [pe.make_change(a_day, cb or [pe.REST], "Séances interverties"),
                   pe.make_change(b_day, ca or [pe.REST], "Séances interverties")])
    return Result(message=f"Jours échangés ({n} modification(s) en attente).", back=True)


@app.action("plan_jour_annuler")
def plan_jour_annuler(jour: str):
    _, db = ctx()
    pending = pending_get(db)
    pending.pop(jour, None)
    pending_save(db, pending)
    return "Modification annulée."


# ---- drafts and generator -----------------------------------------------------------------------------------

def _generator() -> list:
    from coach import plan_builder as pb
    from coach import service
    s, db = ctx()
    a = service.athlete(db, s)
    vma = service.progress(db, s)["vma"].get("retenue") or 17 / 3.6
    race = date.today() + timedelta(weeks=24)
    return [
        ui.muted("Génère un plan complet (base, développement, spécifique, affûtage). Il reste en brouillon, et se crée dans "
                 "COROS quand son début est à moins de 14 jours (règle COROS)."),
        ui.form([
            ui.field("objectif", "Objectif", "select", "10 km", [(g, g) for g in pb.GOALS]),
            ui.field("course", "Date de la course", "date", race.isoformat()),
            ui.field("temps", "Temps visé (min:s ou h:min:s)", "text", "40:00"),
            ui.field("nom", "Nom du plan (vide : automatique)", "text", ""),
            ui.field("semaines", "Semaines (4 à 16)", "number", 10),
            ui.field("jours", "Jours de course", "multi", [1, 2, 3, 5, 6], [(i, d) for i, d in enumerate(pb.WEEKDAYS)]),
            ui.field("longue", "Sortie longue le", "select", 6, [(i, d) for i, d in enumerate(pb.WEEKDAYS)]),
            ui.field("qualite", "Séances de qualité par semaine (1 à 3)", "number", 3),
            ui.field("depart_km", "Volume de départ (km)", "number", 50),
            ui.field("pic_km", "Volume au pic (km)", "number", 70),
            ui.field("vma", "VMA (km/h)", "decimal", fmt.num(vma * 3.6, 1)),
        ], "plan_brouillon_creer", "Créer le brouillon", args={"seuil": a.threshold_pace}),
    ]


@app.action("plan_brouillon_creer")
def plan_brouillon_creer(objectif: str, course: str, temps: str, seuil: float, nom: str = "", semaines: int = 10,
                         jours: list | None = None, longue: int = 6, qualite: int = 3, depart_km: int = 50, pic_km: int = 70,
                         vma: str = "17"):
    from coach import plan_builder as pb
    _, db = ctx()
    race = date.fromisoformat(course)
    gt = fmt.parse_clock(temps)
    days = sorted({int(d) for d in (jours or [])})
    if len(days) < 3 or not gt:
        raise ValueError("Au moins 3 jours de course et un temps visé au format 1:29:00.")
    if objectif not in pb.GOALS or not 4 <= semaines <= 16 or not 1 <= qualite <= 3:
        raise ValueError("Objectif, semaines (4-16) ou séances de qualité (1-3) invalides.")
    if race < date.today() + timedelta(weeks=4):
        raise ValueError("La course doit être dans 4 semaines au moins.")
    p = pb.Params(name=nom.strip() or f"{objectif} - {race.strftime('%d/%m/%Y')}", goal=objectif, race_date=race, weeks=semaines,
                  run_days=days, quality=qualite, start_km=depart_km, peak_km=pic_km, vma=float(vma.replace(",", ".")) / 3.6,
                  threshold_pace=seuil, goal_time=gt, long_day=longue if longue in days else days[-1])
    did = pb.save_draft(db, p, pb.build(p))
    return Result(message="Brouillon enregistré.", open=ui.link("plan", vue=did))


def _draft_view(draft: dict, week: int) -> list:
    from coach import plan_builder as pb
    from coach import service
    from coach.text import course_text
    s, db = ctx()
    a = service.athlete(db, s)
    plan, prm = draft["plan"], draft["params"]
    start, race, today = date.fromisoformat(plan["start"]), date.fromisoformat(prm["race_date"]), date.today()
    blocks = [ui.muted(f"{prm['goal']} le {fmt.day(race)} · {plan['weeks']} semaines à partir du {fmt.day(start)} · statut : {draft['status']}"),
              ui.text(plan["overview"])]
    frm = pb.creatable_from(draft)
    if draft["status"] != "brouillon":
        blocks.append(ui.alert("good", "Plan créé dans COROS."))
    elif today < frm:
        blocks.append(ui.alert("info", f"Envoi possible à partir du {fmt.day(frm)}", "COROS accepte un plan qui démarre dans les 14 jours."))
    elif start < today:
        blocks.append(ui.alert("warn", "La date de début est passée", "Recrée le plan avec une date plus lointaine."))
    else:
        principal = service.plan_meta(db)
        overlap = principal and principal.get("end") and principal["end"] >= plan["start"]
        blocks.append(ui.button("Créer dans COROS", "plan_brouillon_coros", {"id": draft["id"]}, icon="upload",
                                confirm=f"{prm['name']} : {plan['weeks']} semaines à partir du {fmt.day(start)}. Le plan démarre "
                                        "automatiquement à cette date dans COROS (et sur ta montre)."
                                        + (" Il chevauche le plan en cours." if overlap else "")))
    blocks.append(ui.button("Supprimer le brouillon", "plan_brouillon_supprimer", {"id": draft["id"]}, style="danger",
                            confirm="Supprimer ce brouillon ?"))
    vols = [sum(pe.course_km(c) for d, cs in plan["days"].items() for c in cs
                if (start + timedelta(weeks=w)).isoformat() <= d < (start + timedelta(weeks=w + 1)).isoformat()) for w in range(plan["weeks"])]
    blocks.append(ui.chart("Volume prévu par semaine (km)", [f"S{i + 1}" for i in range(len(vols))], ui.series("km", vols, fmt.BLUE, "bar"),
                           kind="bar", y="km", highlight=week))
    week = max(0, min(plan["weeks"] - 1, week))
    ws = start + timedelta(weeks=week)
    blocks.append(ui.pager(f"S{week + 1} · du {fmt.day(ws)}", {"semaine": week - 1} if week > 0 else None,
                           {"semaine": week + 1} if week < plan["weeks"] - 1 else None))
    rows = []
    for i in range(7):
        d = (ws + timedelta(days=i)).isoformat()
        cs = plan["days"].get(d, [])
        if cs:
            rows.append(ui.row(" + ".join(c["courseName"] for c in cs), sub=f"{fmt.day(d)} · " + " · ".join(course_text(c) for c in cs),
                               badge=fmt.type_badge("Course" if cs[0]["courseName"].startswith("COURSE") else kind_label(cs, a)),
                               value=f"{fmt.num(sum(pe.course_km(c) for c in cs), 1)} km"))
        else:
            rows.append(ui.row("Repos", sub=fmt.day(d), badge=fmt.type_badge("Repos")))
    blocks.append(ui.rows(rows))
    return blocks


@app.action("plan_brouillon_coros")
def plan_brouillon_coros(id: str):  # noqa: A002
    from coach import plan_builder as pb
    s, db = ctx()
    msg = asyncio.run(pb.create_in_coros(s, db, id))
    return msg or "Plan créé dans COROS."


@app.action("plan_brouillon_supprimer")
def plan_brouillon_supprimer(id: str):  # noqa: A002
    from coach import plan_builder as pb
    _, db = ctx()
    pb.delete_draft(db, id)
    return Result(message="Brouillon supprimé.", open=ui.link("plan"))


# ---- workout library ----------------------------------------------------------------------------------------

@app.screen("seances_types")
def seances_types(categorie: str = "", recup: str = "trottee"):
    from coach import service
    from coach import workouts as wk
    s, db = ctx()
    a = service.athlete(db, s)
    vma = service.progress(db, s)["vma"].get("retenue") or 1000 / (a.threshold_pace * 0.87)
    goal = (s.goal_a or 2400) / 10
    walk = recup == "marchee"
    easy = pe.default_paces(a, vma)["easy"]
    cat = categorie if categorie in wk.CATEGORIES else wk.CATEGORIES[0]
    pending = pending_get(db)
    plan = json.loads(db.get_meta("plan") or "null")
    days = [d for d in db.plan_days(date.today().isoformat()) if not pe.day_is_done(d)] if plan else []
    blocks = [ui.muted(f"Allures calculées sur ta VMA d'entraînement ({fmt.kmh(vma)}), ton seuil ({fmt.pace_km(a.threshold_pace)}) "
                       f"et ton objectif ({fmt.pace_km(goal)})."),
              ui.choice("categorie", [(c, c) for c in wk.CATEGORIES], cat),
              ui.choice("recup", [("trottee", "Récup trottée"), ("marchee", "Récup marchée")], recup)]
    if pending:
        blocks.append(ui.rows([ui.row(f"{len(pending)} modification(s) en attente d'envoi", sub="Voir et envoyer depuis le Plan",
                                      open=ui.link("plan"), tone="warn")]))
    for w in (x for x in wk.CATALOG if x.category == cat):
        sm = wk.summary(w, vma, a.threshold_pace, goal, easy, walk)
        lo, hi = sm["pace"]
        parts = [ui.muted(w.objective or wk.describe(w, vma, a.threshold_pace, goal, walk)),
                 ui.metrics(ui.metric("Allure", f"{fmt.pace(lo)}–{fmt.pace(hi)}/km" if w.intensity != "cote" else "Effort en côte",
                                      sm["per_rep"] or None),
                            ui.metric("Total", f"≈ {fmt.num(sm['total_m'] / 1000, 1)} km", f"{fmt.dur(sm['total_s'])} · dont "
                                      f"{fmt.num(sm['work_m'] / 1000, 1)} km d'effort")),
                 ui.muted(sm["rec"])]
        if days:
            parts.append(ui.form([ui.field("jour", "Ajouter au plan le", "select", days[0]["date"],
                                           [(d["date"], f"{fmt.day(d['date'])} · à la place de : {pe.describe(effective(d, pending))}")
                                            for d in days])],
                                 "seance_type_ajouter", "Ajouter au plan", args={"cle": w.key, "recup": recup}))
        blocks.append(ui.card(wk.name_of(w), *parts, tone=fmt.type_color({"Fractionné court": "VMA", "Fractionné long": "VMA",
                                                                          "Seuil": "Seuil", "Allure spécifique 10 km": "Allure",
                                                                          "Côtes": "Côtes"}.get(w.category, "Fartlek")),
                              collapsed=False))
    return ui.page("Séances types", *blocks)


@app.action("seance_type_ajouter")
def seance_type_ajouter(cle: str, jour: str, recup: str = "trottee"):
    from coach import service
    from coach import workouts as wk
    s, db = ctx()
    a = service.athlete(db, s)
    vma = service.progress(db, s)["vma"].get("retenue") or 1000 / (a.threshold_pace * 0.87)
    w = wk.by_key(cle)
    day = _day(db, jour)
    course = wk.build(w, vma, a.threshold_pace, (s.goal_a or 2400) / 10, pe.default_paces(a, vma)["easy"], walk=recup == "marchee")
    errs = pe.validate(course)
    if errs:
        raise ValueError(" ; ".join(errs))
    n = queue(db, [pe.make_change(day, [course], f"Séance type : {wk.name_of(w)}")])
    return f"Ajoutée au {fmt.day(jour)}, en attente dans le Plan ({n})."


# ---- race day -----------------------------------------------------------------------------------------------

@app.screen("jour_j")
def jour_j(cible: str = "A", temps: str = "", sortie: str = "", heure: int = 10, meteo: str = "auto",
           temperature: str = "8", humidite: str = "75", vent: str = "10", direction: str = "300", strategie: str = "reel"):
    from coach import raceplan as rp
    from coach import service
    s, db = ctx()
    race_day = date.fromisoformat(s.goal_date) if s.goal_date else date.today()
    D = s.goal_distance_m
    pr = service.progress(db, s)
    targets = {"A": s.goal_a, "B": s.goal_b}
    opts = [("A", f"Objectif A ({fmt.dur(s.goal_a)})"), ("B", f"Objectif B ({fmt.dur(s.goal_b)})")]
    if pr.get("projection"):
        targets["projection"] = pr["projection"]["projected"]
        opts.append(("projection", f"Projection ({fmt.dur(pr['projection']['projected'])})"))
    opts.append(("autre", "Autre temps"))
    target = (fmt.parse_clock(temps) if cible == "autre" else targets.get(cible)) or s.goal_a

    runs = [x for x in service.sessions(db, 3650) if x.get("distance_km") and x["distance_km"] >= D / 1000 * 0.6]
    near = sorted(runs, key=lambda x: abs(x["distance_km"] - D / 1000))[:40]
    course = None
    if sortie:
        try:
            d = service.session_detail(db, sortie, with_records=True)
            if d and d.get("records") is not None and len(d["records"]):
                course = rp.course_from_records(d["records"])
        except Exception:  # noqa: BLE001 - FIT missing on this device: flat course
            course = None
    if course is None or len(course) < 2:
        course = rp.flat_course(D)
    prof = rp.km_profile(course, D)

    form_fields = [ui.field("cible", "Temps visé", "select", cible, opts),
                   ui.field("temps", "Autre temps (min:s ou h:min:s)", "text", temps or fmt.dur(s.goal_a)),
                   ui.field("sortie", "Parcours", "select", sortie,
                            [("", "Plat"), *[(x["label_id"], f"{fmt.day(x['date'])} · {x['name'] or ''} ({fmt.num(x['distance_km'], 1)} km)")
                                             for x in near]]),
                   ui.field("heure", "Heure de départ", "number", heure),
                   ui.field("strategie", "Stratégie", "select", strategie,
                            [("reel", "Temps réaliste avec la météo"), ("tenir", "Tenir le temps visé")]),
                   ui.field("meteo", "Météo", "select", meteo, [("auto", "Automatique (Open-Meteo)"), ("manuel", "Saisie")])]
    if meteo == "manuel":
        form_fields += [ui.field("temperature", "Température (°C)", "decimal", temperature), ui.field("humidite", "Humidité (%)", "number", humidite),
                        ui.field("vent", "Vent (km/h)", "decimal", vent), ui.field("direction", "Vent venant de (°, 0 = nord)", "number", direction)]
    blocks = [ui.muted(f"{s.goal_label} le {fmt.day(race_day)} · J-{(race_day - date.today()).days}"),
              ui.card("Réglages", ui.form(form_fields, "noop", "Calculer", live=True), collapsed=False)]

    wx = None
    if meteo == "auto":
        lat = course["lat"].dropna().iloc[0] if course["lat"].notna().any() else 43.6
        lon = course["lon"].dropna().iloc[0] if course["lon"].notna().any() else 1.44
        try:
            wx = rp.weather(round(lat, 2), round(lon, 2), race_day, int(heure))
            blocks.append(ui.muted(f"{fmt.num(wx['temp'], 0)} °C, humidité {wx['humidity']:.0f} %, vent {fmt.num(wx['wind'] * 3.6, 0)} km/h "
                                   f"venant du {int(wx['wind_dir'])}° · {wx['source']}"))
        except Exception as e:  # noqa: BLE001
            blocks.append(ui.alert("warn", "Météo indisponible", f"{e} — choisis « Saisie »."))
    if wx is None:
        f = lambda v, d: float(str(v).replace(",", ".")) if str(v).strip() else d  # noqa: E731
        wx = {"source": "saisie", "temp": f(temperature, 8), "humidity": f(humidite, 75), "wind": f(vent, 10) / 3.6,
              "wind_dir": f(direction, 300)}
    res = rp.plan(prof, target, wx, start_conservative=True, weather_adjusted=strategie == "reel")
    r = res["rows"]
    blocks += [
        ui.metrics(ui.metric("Temps prévu", fmt.dur(res["total"]), f"{fmt.pace_km(res['total'] / (D / 1000))} en moyenne"),
                   ui.metric("Effet de la chaleur", f"+{fmt.num(res['heat'] * 100, 1)} %" if res["heat"] else "aucun",
                             f"+{fmt.dur(target * res['heat'])}" if res["heat"] else None),
                   ui.metric("Effet du vent", f"{res['wind_effect'] * 100:+.1f} %".replace(".", ",")),
                   ui.metric("Dénivelé", f"+{prof['climb'].clip(lower=0).sum():.0f} / {prof['climb'].clip(upper=0).sum():.0f} m")),
        ui.muted("Tu tiens le temps visé quelles que soient les conditions : l'effort sera plus élevé si la météo est défavorable."
                 if strategie == "tenir" else "Le temps visé correspond à des conditions idéales ; le plan ajoute ce que coûtent chaleur et vent."),
        ui.chart("Allure par km", [str(int(k)) for k in r["km"]], ui.series("Allure", r["pace"], fmt.BLUE, "points"), y="pace", reverse=True,
                 lines=[ui.hline(res["base_pace"], f"sur plat {fmt.pace(res['base_pace'])}")]),
    ]
    wind_txt = []
    for b in r["bearing"]:
        f_ = rp.wind_factor(wx.get("wind", 0), wx.get("wind_dir"), b)
        wind_txt.append("face" if f_ > 1.01 else "dos" if f_ < 0.995 else "—")
    blocks.append(ui.table(["Km", "Allure", "Passage", "Pente", "Vent"], [
        [int(k), fmt.pace_km(p), fmt.dur(sp), f"{g * 100:+.1f} %".replace(".", ","), w_]
        for k, p, sp, g, w_ in zip(r["km"], r["pace"], r["split"], r["grade"], wind_txt)]))
    race_row = next(iter(db.plan_days(race_day.isoformat(), race_day.isoformat())), None)
    if race_row and not pe.day_is_done(race_row):
        blocks.append(ui.button("Mettre ce plan sur la montre le jour J", "jour_j_montre", icon="watch",
                                args={"cible": cible, "temps": temps, "sortie": sortie, "heure": heure, "meteo": meteo,
                                      "temperature": temperature, "humidite": humidite, "vent": vent, "direction": direction,
                                      "strategie": strategie}))
        blocks.append(ui.muted("La séance du jour de course dans COROS sera remplacée par ce plan, un segment par km (envoi depuis le Plan)."))
    return ui.page("Jour J", *blocks)


@app.action("noop")
def noop(**_):
    return Result()


@app.action("jour_j_montre")
def jour_j_montre(**reglages):
    from coach import raceplan as rp
    s, db = ctx()
    race_day = date.fromisoformat(s.goal_date)
    day = _day(db, race_day.isoformat())
    res = _race_result(s, db, reglages)
    queue(db, [pe.make_change(day, [rp.watch_course(res, s.goal_label)], "Plan de course km par km")])
    return Result(message="Mis en attente : envoie-le depuis le Plan.", open=ui.link("plan"))


def _race_result(s, db, g: dict) -> dict:
    from coach import raceplan as rp
    from coach import service
    D = s.goal_distance_m
    pr = service.progress(db, s)
    targets = {"A": s.goal_a, "B": s.goal_b, "projection": (pr.get("projection") or {}).get("projected")}
    target = (fmt.parse_clock(g.get("temps", "")) if g.get("cible") == "autre" else targets.get(g.get("cible", "A"))) or s.goal_a
    course = None
    if g.get("sortie"):
        d = service.session_detail(db, g["sortie"], with_records=True)
        if d and d.get("records") is not None and len(d["records"]):
            course = rp.course_from_records(d["records"])
    if course is None or len(course) < 2:
        course = rp.flat_course(D)
    prof = rp.km_profile(course, D)
    f = lambda v, d: float(str(v).replace(",", ".")) if str(v).strip() else d  # noqa: E731
    wx = None
    if g.get("meteo", "auto") == "auto":
        try:
            lat = course["lat"].dropna().iloc[0] if course["lat"].notna().any() else 43.6
            lon = course["lon"].dropna().iloc[0] if course["lon"].notna().any() else 1.44
            wx = rp.weather(round(lat, 2), round(lon, 2), date.fromisoformat(s.goal_date), int(g.get("heure", 10)))
        except Exception:  # noqa: BLE001
            wx = None
    if wx is None:
        wx = {"temp": f(g.get("temperature", ""), 8), "humidity": f(g.get("humidite", ""), 75), "wind": f(g.get("vent", ""), 10) / 3.6,
              "wind_dir": f(g.get("direction", ""), 300)}
    return rp.plan(prof, target, wx, start_conservative=True, weather_adjusted=g.get("strategie", "reel") == "reel")
