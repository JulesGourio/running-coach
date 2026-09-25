"""Plan editing: build COROS workouts from simple templates, check them against COROS's rules, adjust them
(lighter/heavier, faster/slower, moved), suggest adjustments from readiness and load, and push the changes to
the in-progress COROS plan with updateTrainingPlan (only the changed days; COROS never rewrites a completed day).
"""
from __future__ import annotations

import copy
import json
import re
import unicodedata
from datetime import date, timedelta

from coach.config import Settings
from coach.db import DB
from coach.metrics.intervals import flatten_course, is_quality, is_stride, planned_distance
from coach.metrics.zones import Athlete
from coach.text import course_text
from coach.verdict import fpace

REST = {"sportType": 4, "courseName": "Repos", "courseDescription": "Jour de repos complet.", "sections": []}
JOG = (380, 450)
STRIDES = (190, 210)
KINDS = {"warmup": 1, "work": 2, "recovery": 3, "cooldown": 4}

TEMPLATES = {
    "footing": "Footing",
    "footing_acc": "Footing + accélérations",
    "vma": "VMA (répétitions)",
    "seuil": "Seuil (blocs)",
    "allure": "Allure 10 km (répétitions)",
    "longue": "Sortie longue",
    "longue_allure": "Sortie longue avec allure",
    "repos": "Repos",
}


class PlanError(RuntimeError):
    pass


# ---- building ---------------------------------------------------------------------------------------

def _pace(p: tuple[float, float]) -> dict:
    lo, hi = sorted((int(round(p[0])), int(round(p[1]))))
    return {"intensityType": 2, "intensityValueStart": lo, "intensityValueEnd": hi}


def section(kind: str, target: str, value: float, pace: tuple[float, float] | None = None) -> dict:
    s = {"sectionType": KINDS[kind], "targetType": 1 if target == "distance" else 2, "targetValue": int(round(value))}
    if pace:
        s.update(_pace(pace))
    return s


def group(repeats: int, *sets: dict) -> dict:
    return {"intervalGroup": True, "repeats": int(repeats), "sets": list(sets)}


def _p(p: tuple[float, float]) -> str:
    lo, hi = sorted(p)
    return f"{fpace(lo)}-{fpace(hi)}/km"


def _km(m: float) -> str:
    return f"{m / 1000:g}".replace(".", ",") + " km" if m >= 1000 else f"{m:g} m"


def _recovery(p: dict) -> tuple[dict, str]:
    if p.get("rec_unit", "m") == "s":
        return section("recovery", "time", p["rec"], JOG), f"{int(p['rec'])} s trottées"
    return section("recovery", "distance", p["rec"], JOG), f"{int(p['rec'])} m trottés"


def default_paces(a: Athlete, vma: float | None, goal_a: float | None = None, goal_b: float | None = None) -> dict:
    """Pace ranges (s/km, fast then slow) for each template, from the athlete's zones and estimated VMA."""
    z2 = a.pace_zone_bounds()[1]
    easy = (5 * round(z2[1] / 5), 5 * round(z2[2] / 5))
    thr = a.threshold_pace
    vp = 1000 / vma if vma else thr * 0.88
    goal = (goal_a / 10 if goal_a else vp / 0.9, goal_b / 10 if goal_b else vp / 0.88)
    return {"easy": easy, "seuil": (thr - 7, thr + 3), "allure": (round(goal[0]), round(max(goal) + 1)),
            "vma_short": (round(vp / 1.05) - 4, round(vp / 1.05) + 4),
            "vma_long": (round(vp / 0.98) - 3, round(vp / 0.98) + 3), "strides": STRIDES}


def build(template: str, p: dict) -> dict:
    """COROS course JSON from a template and its parameters (paces as (fast, slow) in s/km)."""
    easy = p.get("easy", (300, 335))
    wu = section("warmup", "time", p.get("warmup_s", 900), easy)
    cd = section("cooldown", "time", p.get("cooldown_s", 600), (easy[0], easy[1] + 5))
    if template == "repos":
        return copy.deepcopy(REST)
    if template in ("footing", "footing_acc"):
        m = p["km"] * 1000
        secs = [section("work", "distance", m, easy)]
        name, desc = f"Footing {_km(m)}", f"Footing en endurance fondamentale (Z2, {_p(easy)})."
        if template == "footing_acc":
            n = int(p.get("strides", 6))
            secs.append(group(n, section("work", "distance", 100, STRIDES), section("recovery", "time", 60, JOG)))
            name = f"Footing {_km(m)} + accélérations"
            desc += f" Puis {n}x100 m d'accélérations progressives, retour trotté."
        return {"sportType": 1, "courseName": name, "courseDescription": desc, "sections": secs}
    if template in ("vma", "allure"):
        rec, rec_txt = _recovery(p)
        reps, rep_m = int(p["reps"]), p["rep_m"]
        label = "VMA" if template == "vma" else "Allure 10 km"
        return {"sportType": 1, "courseName": f"{label} {reps}x{int(rep_m)}m",
                "courseDescription": f"15 min d'échauffement, {reps}x{int(rep_m)} m à {_p(p['pace'])}, "
                                     f"récup {rec_txt}, 10 min de retour au calme.",
                "sections": [wu, group(reps, section("work", "distance", rep_m, p["pace"]), rec), cd]}
    if template == "seuil":
        blocks, mins = int(p["blocks"]), p["block_min"]
        work = section("work", "time", mins * 60, p["pace"])
        body = work if blocks == 1 else group(blocks, work, section("recovery", "time", p.get("rec", 120), JOG))
        name = f"Seuil {int(mins)}min" if blocks == 1 else f"Seuil {blocks}x{int(mins)}min"
        rec_txt = "" if blocks == 1 else f" avec {int(p.get('rec', 120))} s trottées entre les blocs"
        return {"sportType": 1, "courseName": name,
                "courseDescription": f"15 min d'échauffement, {name.split(' ', 1)[1]} au seuil ({_p(p['pace'])}){rec_txt}, "
                                     "10 min de retour au calme.",
                "sections": [wu, body, cd]}
    if template == "longue":
        m = p["km"] * 1000
        return {"sportType": 1, "courseName": f"Sortie longue {_km(m)}",
                "courseDescription": f"Sortie longue en endurance fondamentale ({_p(easy)}).",
                "sections": [section("work", "distance", m, easy)]}
    if template == "longue_allure":
        total, fast = p["km"] * 1000, p["fast_km"] * 1000
        if fast >= total:
            raise PlanError("La partie rapide doit être plus courte que la sortie.")
        return {"sportType": 1, "courseName": f"Sortie longue {_km(total)} dont {_km(fast)} en allure",
                "courseDescription": f"{_km(total - fast)} en endurance ({_p(easy)}) puis {_km(fast)} à {_p(p['pace'])}.",
                "sections": [section("work", "distance", total - fast, easy), section("work", "distance", fast, p["pace"])]}
    raise PlanError(f"Modèle inconnu : {template}")


# ---- checking ---------------------------------------------------------------------------------------

def _check_section(s: dict, path: str, in_group: bool) -> list[str]:
    e = []
    if s.get("intervalGroup"):
        if in_group:
            e.append(f"{path} : pas de groupe imbriqué")
        if not isinstance(s.get("repeats"), int) or not 1 <= s["repeats"] <= 20:
            e.append(f"{path} : répétitions entre 1 et 20")
        if not s.get("sets"):
            e.append(f"{path} : groupe vide")
        for k in ("intensityType", "targetType", "targetValue"):
            if s.get(k) is not None:
                e.append(f"{path} : pas de cible ni d'intensité sur le groupe")
                break
        for i, m in enumerate(s.get("sets") or []):
            e += _check_section(m, f"{path}.{i + 1}", True)
        return e
    if s.get("sectionType") not in (1, 2, 3, 4):
        e.append(f"{path} : type de section invalide")
    if in_group and s.get("sectionType") not in (2, 3):
        e.append(f"{path} : dans un groupe, seulement effort ou récupération")
    if s.get("targetType") not in (1, 2, 4):
        e.append(f"{path} : cible distance, durée ou libre")
    if s.get("targetType") != 4 and (not isinstance(s.get("targetValue"), int) or s["targetValue"] <= 0):
        e.append(f"{path} : cible entière positive")
    if s.get("intensityType") == 2:
        for v in (s.get("intensityValueStart"), s.get("intensityValueEnd")):
            if not isinstance(v, int) or not 120 <= v <= 1499:
                e.append(f"{path} : allure entre 2:00 et 24:59/km")
                break
    if s.get("intensityType") == 1:
        for v in (s.get("intensityValueStart"), s.get("intensityValueEnd")):
            if not isinstance(v, int) or not 30 <= v <= 240:
                e.append(f"{path} : FC entre 30 et 240 bpm")
                break
    return e


def validate(course: dict) -> list[str]:
    e = []
    if course.get("sportType") not in (1, 4, 5):
        e.append("sport : course, trail ou repos")
    name = str(course.get("courseName") or "").strip()
    if not name or len(name) > 100:
        e.append("nom requis (100 caractères max)")
    if not str(course.get("courseDescription") or "").strip():
        e.append("description requise")
    secs = course.get("sections") or []
    if course.get("sportType") == 4 and secs:
        e.append("un repos n'a pas de sections")
    if course.get("sportType") != 4 and not secs:
        e.append("sections requises")
    for i, s in enumerate(secs):
        e += _check_section(s, f"section {i + 1}", False)
    return e


# ---- adjusting --------------------------------------------------------------------------------------

def _round_target(s: dict, factor: float) -> None:
    v = s["targetValue"] * factor
    step = 100 if s["targetType"] == 1 and v >= 1000 else 10 if s["targetType"] == 2 else 50
    s["targetValue"] = max(step, int(round(v / step) * step))


def scale(course: dict, factor: float) -> dict:
    """Volume ×factor: work and easy sections and repetition counts; warmup, cooldown and strides unchanged."""
    if course.get("sportType") == 4 or abs(factor - 1) < 1e-6:
        return copy.deepcopy(course)
    c = copy.deepcopy(course)
    for s in c["sections"]:
        if s.get("intervalGroup"):
            work = [m for m in s.get("sets") or [] if m.get("sectionType") == 2]
            if work and all(m.get("targetValue") and m["targetValue"] < 200 and m["targetType"] == 1 for m in work):
                continue  # strides
            s["repeats"] = max(1, min(20, int(round(s["repeats"] * factor))))
        elif s.get("sectionType") == 2 and s.get("targetValue") and s.get("targetType") in (1, 2):
            _round_target(s, factor)
    pct = round((factor - 1) * 100)
    tag = f"allégée {pct} %" if pct < 0 else f"renforcée +{pct} %"
    c["courseName"] = re.sub(r"\s*\((allégée|renforcée)[^)]*\)$", "", c["courseName"])[:84] + f" ({tag.split()[0]})"
    c["courseDescription"] = f"Version {tag}. " + re.sub(r"^Version (allégée|renforcée)[^.]*\. ", "", c["courseDescription"])
    return c


def shift_paces(course: dict, delta_s: int, threshold_pace: float) -> dict:
    """Quality work sections faster (delta < 0) or slower (delta > 0) by delta s/km; easy running untouched."""
    c = copy.deepcopy(course)

    def walk(secs: list[dict]) -> None:
        for s in secs:
            if s.get("intervalGroup"):
                walk(s.get("sets") or [])
            elif (s.get("sectionType") == 2 and s.get("intensityType") == 2 and s.get("intensityValueEnd")
                  and s["intensityValueEnd"] < threshold_pace * 1.15
                  and not (s.get("targetType") == 1 and (s.get("targetValue") or 0) < 200)):
                s["intensityValueStart"] = min(1499, max(120, s["intensityValueStart"] + delta_s))
                s["intensityValueEnd"] = min(1499, max(120, s["intensityValueEnd"] + delta_s))
    walk(c.get("sections") or [])
    return c


def is_quality_course(course: dict | None, threshold_pace: float) -> bool:
    return bool(course) and any(is_quality(st, threshold_pace) for st in flatten_course(course))


def course_km(course: dict | None) -> float:
    return planned_distance(course) / 1000 if course and course.get("sportType") != 4 else 0.0


def describe(courses: list[dict]) -> str:
    if not courses or all(c.get("sportType") == 4 for c in courses):
        return "Repos"
    return " + ".join(f"{c['courseName']} ({course_text(c)})" for c in courses if c.get("sportType") != 4)


# ---- changes ----------------------------------------------------------------------------------------

def day_courses(day: dict) -> list[dict]:
    """Current course JSONs of a stored plan day ([] for rest)."""
    return [c["json"] for c in day.get("courses") or [] if c.get("json")]


def day_is_done(day: dict) -> bool:
    return any(not re.search(r"not started", c.get("status") or "", re.I) for c in day.get("courses") or [])


def make_change(day: dict, after: list[dict], reason: str) -> dict:
    return {"date": day["date"], "day_no": day["day_no"], "before": day_courses(day),
            "after": [c for c in after if c.get("sportType") != 4] or [copy.deepcopy(REST)], "reason": reason}


def queue_change(pending: dict, ch: dict) -> None:
    """Add a change to the pending set (keyed by date). Several edits of the same day merge, keeping the
    day's original content as "before"; an edit that brings the day back to its original is dropped."""
    prev = pending.get(ch["date"])
    if prev:
        reason = prev["reason"] if ch["reason"] in prev["reason"] else f"{prev['reason']} + {ch['reason']}"
        ch = {**ch, "before": prev["before"], "reason": reason}
    unchanged = ch["after"] == ch["before"] or (not ch["before"] and all(c.get("sportType") == 4 for c in ch["after"]))
    if unchanged:
        pending.pop(ch["date"], None)
    else:
        pending[ch["date"]] = ch


def swap(day_a: dict, day_b: dict, reason: str = "Séances interverties") -> list[dict]:
    return [make_change(day_a, day_courses(day_b) or [REST], reason), make_change(day_b, day_courses(day_a) or [REST], reason)]


def _ascii(text: str) -> str:
    """The watch and the existing plan use plain ASCII names; keep what's written to COROS consistent."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def to_coros(course: dict, day_no: int) -> dict:
    c = {k: v for k, v in course.items() if k != "dayNo"}
    c["courseName"], c["courseDescription"] = _ascii(c["courseName"]), _ascii(c["courseDescription"])
    return {"dayNo": day_no, **c}


def _clean(msg: str, plan_id: str) -> str:
    lines = [ln for ln in msg.splitlines() if "Plan ID" not in ln]
    return "\n".join(lines).replace(plan_id, "…").strip()


async def push_changes(s: Settings, db: DB, changes: list[dict], client=None) -> dict:
    """Write the changed days to the in-progress COROS plan, then re-read them into the local database.
    `client` is an already-open CorosMCP (tests pass a fake); by default a connection is opened."""
    from coach.sources.coros_mcp import CorosMCP
    from coach.sync import refresh_plan

    plan = json.loads(db.get_meta("plan") or "null")
    if not plan:
        raise PlanError("Aucun plan COROS en cours n'est synchronisé : lance une synchronisation.")
    if not changes:
        raise PlanError("Aucune modification à envoyer.")
    today = date.today().isoformat()
    errors = []
    for ch in changes:
        if ch["date"] < today:
            errors.append(f"{ch['date']} : jour passé, non modifiable")
        for c in ch["after"]:
            errors += [f"{ch['date']} : {e}" for e in validate(c)]
    if errors:
        raise PlanError(" ; ".join(errors[:10]))
    course_list = [to_coros(c, ch["day_no"]) for ch in sorted(changes, key=lambda x: x["day_no"]) for c in ch["after"]]

    async def run(c) -> str:
        msg = await c.call("updateTrainingPlan", {"planInfo": {"planId": plan["id"]}, "courseList": course_list})
        dates = sorted(ch["date"] for ch in changes)
        await refresh_plan(c, db, date.fromisoformat(dates[0]), date.fromisoformat(dates[-1]))
        return msg

    try:
        if client is not None:
            msg = await run(client)
        else:
            async with CorosMCP(s) as c:
                msg = await run(c)
    except Exception as e:  # noqa: BLE001 - record the failure, then surface it
        for ch in changes:
            db.add_plan_change(ch, "échec", str(e)[:500])
        raise
    msg = _clean(msg, plan["id"])
    m = re.search(r"Skipped executed days \(dayNo\):\s*(.*)", msg)
    skipped = {int(x) for x in re.findall(r"\d+", m.group(1))} if m else set()
    for ch in changes:
        db.add_plan_change(ch, "ignorée (déjà faite)" if ch["day_no"] in skipped else "appliquée", msg[:500])
    return {"message": msg, "skipped": sorted(skipped), "applied": [ch["date"] for ch in changes if ch["day_no"] not in skipped]}


# ---- suggestions ------------------------------------------------------------------------------------

def suggestions(db: DB, s: Settings) -> list[dict]:
    """Adjustments worth proposing now, each with the ready-made changes: rest or lighten when readiness is
    low, lighten the coming week when the COROS load ratio stays excessive, and reschedule a missed quality
    session onto the next easy day."""
    from coach import service

    a = service.athlete(db, s)
    today = date.today()
    days = {d["date"]: d for d in db.plan_days((today - timedelta(days=5)).isoformat(), (today + timedelta(days=10)).isoformat())}
    upcoming = [d for k, d in sorted(days.items()) if k >= today.isoformat() and not day_is_done(d)]
    qual = [d for d in upcoming if any(is_quality_course(c, a.threshold_pace) for c in day_courses(d))]
    out = []

    r = service.readiness_today(db, s)
    soon = [d for d in qual if d["date"] <= (today + timedelta(days=1)).isoformat()]
    if soon and r["level"] == "rouge":
        d = soon[0]
        easy = build("footing", {"km": 7, "easy": default_paces(a, None)["easy"]})
        easy["courseDescription"] = "Récupération : footing très facile à la place de la séance de qualité."
        out.append({"title": f"Remplacer la séance du {d['date']} par un footing facile",
                    "why": f"Forme du jour rouge ({r['score']}/100) : {' '.join(r['reasons'])}",
                    "changes": [make_change(d, [easy], "Forme basse")]})
    elif soon and r["level"] == "orange":
        d = soon[0]
        out.append({"title": f"Alléger la séance du {d['date']} (-20 %)",
                    "why": f"Forme du jour orange ({r['score']}/100) : {' '.join(r['reasons'])}",
                    "changes": [make_change(d, [scale(c, 0.8) for c in day_courses(d)], "Forme moyenne")]})

    ratios = [d["load_ratio"] for d in db.daily((today - timedelta(days=3)).isoformat()) if d.get("load_ratio")]
    week_q = [d for d in qual if d["date"] <= (today + timedelta(days=7)).isoformat()]
    if sum(1 for x in ratios if x >= 1.5) >= 2 and week_q:
        out.append({"title": "Alléger les séances de qualité des 7 prochains jours (-20 %)",
                    "why": f"Ratio de charge COROS à {max(ratios):.2f} plusieurs jours de suite (excessif au-delà de 1,5).",
                    "changes": [make_change(d, [scale(c, 0.8) for c in day_courses(d)], "Charge excessive") for d in week_q]})

    view = {p["date"]: p for p in service.plan_view(db, s, back=4, ahead=0)}
    missed = [days[k] for k, p in sorted(view.items()) if p["status"] == "manquée" and k in days
              and any(is_quality_course(c, a.threshold_pace) for c in day_courses(days[k]))]
    if missed:
        m = missed[-1]
        qual_dates = {d["date"] for d in qual}
        target = next((d for d in upcoming if d not in qual and day_courses(d) and d["date"] > today.isoformat()
                       and (date.fromisoformat(d["date"]) + timedelta(days=1)).isoformat() not in qual_dates
                       and (date.fromisoformat(d["date"]) - timedelta(days=1)).isoformat() not in qual_dates), None)
        if target:
            out.append({"title": f"Reprogrammer la séance manquée du {m['date']} au {target['date']}",
                        "why": f"« {describe(day_courses(m))} » n'a pas été faite ; le {target['date']} est un jour facile "
                               "sans séance dure la veille ni le lendemain.",
                        "changes": [make_change(target, day_courses(m), "Séance manquée reprogrammée")]})
    return out
