"""Weekly report (Monday to Sunday): done vs planned, key sessions, load, sleep and recovery against the previous
weeks, progress towards the goal, and proposed adjustments. Generated automatically for the week just ended."""
from __future__ import annotations

import json
import statistics
from datetime import date, timedelta

from coach.config import Settings
from coach.db import DB

QUALITY_CATS = ("VMA", "Seuil", "Allure", "Tempo", "Fartlek", "Côtes", "Course", "Sortie longue avec")


def _n(x: float, dec: int = 1) -> str:
    return f"{x:.{dec}f}".replace(".", ",")


def _mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def last_complete_week(today: date) -> date:
    """Monday of the last full week (the week that ended last Sunday)."""
    return today - timedelta(days=today.weekday() + 7)


def build(db: DB, s: Settings, week_start: date) -> dict:
    from coach import alerts as al
    from coach import plan_edit as pe
    from coach import service
    a = service.athlete(db, s)
    ws, we = week_start, week_start + timedelta(days=6)
    iso = lambda d: d.isoformat()  # noqa: E731

    # done vs planned
    plan_days = {d["date"]: d for d in db.plan_days(iso(ws), iso(we))}
    done = service.sessions_between(db, iso(ws), iso(we))
    done_by_day: dict[str, list] = {}
    for x in done:
        done_by_day.setdefault(x["date"], []).append(x)
    days, n_planned, n_done, missed = [], 0, 0, []
    for i in range(7):
        d = iso(ws + timedelta(days=i))
        cs = pe.day_courses(plan_days[d]) if d in plan_days else []
        xs = done_by_day.get(d, [])
        if cs:
            n_planned += 1
            if xs:
                n_done += 1
            else:
                missed.append({"date": d, "planned": pe.describe(cs)})
        days.append({"date": d, "planned": pe.describe(cs) if cs else ("Repos" if d in plan_days else None),
                     "planned_km": sum(pe.course_km(c) for c in cs),
                     "done": [{"headline": x["headline"] or x["name"], "km": x["distance_km"], "score": x["score"],
                               "finding": (x["findings"] or [None])[0]} for x in xs]})
    km_done = sum(x["distance_km"] or 0 for x in done)
    km_planned = sum(d["planned_km"] for d in days)
    others = db.activities(iso(ws), iso(we), sports="other")
    key = [x for x in done if (x["kind_fr"] or "").startswith(QUALITY_CATS)]

    # previous 4 weeks for comparison
    p0 = ws - timedelta(days=28)
    prev_runs = db.activities(iso(p0), iso(ws - timedelta(days=1)))
    km_prev = sum(r["distance_km"] or 0 for r in prev_runs) / 4

    daily = {d["date"]: d for d in db.daily(iso(p0), ) if d["date"] <= iso(we)}
    week_daily = [daily[k] for k in sorted(daily) if iso(ws) <= k <= iso(we)]
    prev_daily = [daily[k] for k in sorted(daily) if k < iso(ws)]
    ratio = [d["load_ratio"] for d in week_daily if d.get("load_ratio")]
    rhr_w, rhr_p = _mean([d.get("rhr") for d in week_daily]), _mean([d.get("rhr") for d in prev_daily])
    hrv_w, hrv_p = _mean([d.get("hrv") for d in week_daily]), _mean([d.get("hrv") for d in prev_daily])
    nights = [n for n in db.sleep(iso(ws + timedelta(days=1))) if n["date"] <= iso(we + timedelta(days=1))]
    sleep_avg = _mean([n.get("total_min") for n in nights])
    short = sum(1 for n in nights if (n.get("total_min") or 0) < 420)
    naps = sum(1 for n in nights if n.get("naps_min"))

    track = {t["week"]: t for t in json.loads(db.get_meta("goal_track") or "[]")}
    est_now = track.get(iso(ws), {}).get("estimate")
    est_prev = track.get(iso(ws - timedelta(days=7)), {}).get("estimate")

    # summary and proposals
    lines, props = [], []
    if n_planned:
        lines.append(f"{n_done} séance{'s' if n_done > 1 else ''} sur {n_planned} prévues, {_n(km_done)} km pour "
                     f"{_n(km_planned, 0)} km prévus.")
    else:
        lines.append(f"{len(done)} sortie{'s' if len(done) > 1 else ''}, {_n(km_done)} km (pas de plan cette semaine).")
    if km_prev:
        lines.append(f"Volume {'en hausse' if km_done > km_prev * 1.1 else 'en baisse' if km_done < km_prev * 0.9 else 'stable'} "
                     f"par rapport aux 4 semaines précédentes ({_n(km_prev)} km/semaine en moyenne).")
    if others:
        h = sum((o["duration_s"] or 0) for o in others) / 3600
        lines.append(f"En plus : {len(others)} activité{'s' if len(others) > 1 else ''} d'autres sports ({_n(h)} h).")
    if key:
        lines.append("Séances clés : " + " ; ".join(f"{x['headline']}" + (f" ({x['findings'][0].rstrip('.')})" if x.get("findings") else "") for x in key) + ".")
    if sleep_avg:
        lines.append(f"Sommeil : {_n(sleep_avg / 60)} h par jour en moyenne, {short} nuit{'s' if short > 1 else ''} sous 7 h"
                     + (f", {naps} sieste{'s' if naps > 1 else ''}." if naps else "."))
    if rhr_w and rhr_p:
        lines.append(f"FC de repos {_n(rhr_w, 0)} bpm ({'+' if rhr_w >= rhr_p else '−'}{_n(abs(rhr_w - rhr_p), 0)} vs les 4 semaines d'avant)"
                     + (f", VFC {_n(hrv_w, 0)} ms ({'+' if hrv_w >= hrv_p else '−'}{_n(abs(hrv_w - hrv_p), 0)})." if hrv_w and hrv_p else "."))
    if est_now and est_prev:
        diff = est_now - est_prev
        lines.append(f"10 km estimé : {int(est_now // 60)}:{int(est_now % 60):02d} ({'−' if diff < 0 else '+'}{abs(diff):.0f} s sur la semaine).")

    if len(missed) >= 2:
        props.append("Deux séances ou plus manquées : ne pas tout rattraper, garder la semaine suivante telle quelle.")
    if sleep_avg and sleep_avg < 420:
        props.append("Sommeil sous 7 h en moyenne : avancer le coucher de 30 min, surtout la veille des séances dures.")
    if ratio and max(ratio) >= 1.5:
        props.append(f"Ratio de charge monté à {_n(max(ratio), 2)} : alléger de 20 % les séances de la semaine suivante.")
    if rhr_w and rhr_p and rhr_w >= rhr_p + 4:
        props.append("FC de repos nettement plus haute : une journée facile de plus en début de semaine.")
    if key and all((x.get("score") or 10) >= 8 for x in key) and not props:
        props.append("Séances clés bien exécutées et récupération correcte : on continue" + (" le plan, sans rien ajouter." if n_planned else "."))
    if not props:
        props.append("Rien à signaler : suivre le plan de la semaine suivante.")
    return {"week": iso(ws), "end": iso(we), "created": date.today().isoformat(), "summary": lines, "proposals": props,
            "days": days, "n_planned": n_planned, "n_done": n_done, "missed": missed, "km_done": km_done,
            "km_planned": km_planned, "km_prev": km_prev, "sleep_avg": sleep_avg, "rhr": rhr_w, "hrv": hrv_w,
            "load_ratio_max": max(ratio) if ratio else None, "estimate": est_now,
            "alerts": al.alerts(db, s, we)}


def reports(db: DB) -> dict[str, dict]:
    return json.loads(db.get_meta("weekly_reports") or "{}")


def ensure_last_week(db: DB, s: Settings, today: date | None = None) -> dict:
    """The report of the week that ended last Sunday, generated the first time it's asked for (so on Monday)."""
    ws = last_complete_week(today or date.today())
    items = reports(db)
    if ws.isoformat() not in items:
        items[ws.isoformat()] = build(db, s, ws)
        db.set_meta("weekly_reports", json.dumps(items))
    return items[ws.isoformat()]


def regenerate(db: DB, s: Settings, week_start: date) -> dict:
    items = reports(db)
    items[week_start.isoformat()] = build(db, s, week_start)
    db.set_meta("weekly_reports", json.dumps(items))
    return items[week_start.isoformat()]
