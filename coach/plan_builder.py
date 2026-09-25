"""Build a whole periodised plan (base, build, peak, taper) for a race, as local draft that can later be created in
COROS (createTrainingPlan only accepts a start within the next 14 days, so future plans live here until then)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from coach import plan_edit as pe
from coach import workouts as wk
from coach.db import DB

GOALS = {"5 km": 5000, "10 km": 10000, "Semi-marathon": 21097, "Marathon": 42195}
PHASES = {1: "Préparation", 2: "Base", 3: "Développement", 4: "Spécifique", 5: "Course", 6: "Transition"}
WEEKDAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
LONG_MAX = {"5 km": 16, "10 km": 20, "Semi-marathon": 24, "Marathon": 34}


@dataclass
class Params:
    name: str
    goal: str
    race_date: date
    weeks: int
    run_days: list[int] = field(default_factory=lambda: [1, 2, 3, 5, 6])  # 0 = Monday
    quality: int = 3
    start_km: float = 50
    peak_km: float = 70
    vma: float = 17 / 3.6  # m/s
    threshold_pace: float = 262
    goal_time: float = 2400  # s
    long_day: int = 6


def phases(weeks: int) -> list[tuple[int, int]]:
    """(phaseType, weeks): base ~30 %, build ~40 %, peak ~20 %, race week."""
    race = 1
    peak = max(1, round((weeks - race) * 0.25))
    base = max(1, round((weeks - race) * 0.3))
    build = weeks - race - peak - base
    return [(2, base), (3, build), (4, peak), (5, race)]


def volumes(p: Params) -> list[float]:
    """Weekly km: +~7 %/week towards the peak with an easier week every 4th, two taper weeks at ~75 % and ~55 %."""
    n_train = p.weeks - 2
    out, v = [], p.start_km
    step = (p.peak_km - p.start_km) / max(1, n_train - 1 - n_train // 4)
    for i in range(n_train):
        if (i + 1) % 4 == 0:
            out.append(round(v * 0.8))
        else:
            out.append(round(min(p.peak_km, v)))
            v += step
    return out + [round(p.peak_km * 0.75), round(p.peak_km * 0.5)]


def _quality_week(phase: int, week_in_phase: int, goal: str) -> list[str]:
    """Workout keys (coach.workouts) for the quality slots of a week, by phase."""
    if phase == 2:
        return [["400", "30-30", "300", "1-1"][week_in_phase % 4], ["seuil-10", "seuil-15", "tempo-25"][week_in_phase % 3]]
    if phase == 3:
        return [["1000", "800", "1200", "3min"][week_in_phase % 4], ["seuil-15", "seuil-2k", "seuil-20"][week_in_phase % 3]]
    if goal in ("5 km", "10 km"):
        return [["spe-2k", "1000", "spe-1k", "800"][week_in_phase % 4], ["spe-3k", "seuil-2k", "spe-1600"][week_in_phase % 3]]
    return [["seuil-20", "spe-2k", "seuil-2k"][week_in_phase % 3], ["tempo-25", "seuil-15"][week_in_phase % 2]]


def _goal_named(course: dict, goal: str) -> dict:
    """Goal-pace workouts are written "Allure 10 km" in the library; name them after the actual race."""
    if goal != "10 km":
        course["courseName"] = course["courseName"].replace("Allure 10 km", f"Allure {goal.lower()}")
        course["courseDescription"] = course["courseDescription"].replace("allure 10 km", f"allure {goal.lower()}")
    return course


def _quality_days(candidates: list[int], long_day: int, n: int) -> list[int]:
    """Hard days as far apart as possible: never two in a row, and not the day before the long run if avoidable."""
    from itertools import combinations
    if n <= 0:
        return []
    best, best_key = candidates[:n], None
    for combo in combinations(candidates, min(n, len(candidates))):
        days = sorted(combo) + [long_day]
        gaps = [(b - a) % 7 for a, b in zip(days, days[1:])]
        key = (min(gaps) > 1, (long_day - 1) not in combo, min(gaps), sum(gaps))
        if best_key is None or key > best_key:
            best, best_key = sorted(combo), key
    return best


def build(p: Params) -> dict:
    """{"start", "weeks", "phases": [...], "days": {iso date: [course, ...]}, "overview"}."""
    start = p.race_date - timedelta(days=p.race_date.weekday()) - timedelta(weeks=p.weeks - 1)
    goal_pace = p.goal_time / (GOALS[p.goal] / 1000)
    a_easy = (int(5 * round(1000 / (p.vma * 0.72) / 5)), int(5 * round(1000 / (p.vma * 0.64) / 5)))
    vols = volumes(p)
    ph, days = [], {}
    w0 = 0
    for ptype, n in phases(p.weeks):
        ph.append({"phaseType": ptype, "name": PHASES[ptype], "start": (start + timedelta(weeks=w0)).isoformat(),
                   "end": (start + timedelta(weeks=w0 + n, days=-1)).isoformat(), "weeks": n})
        for k in range(n):
            wi = w0 + k
            ws = start + timedelta(weeks=wi)
            run_days = sorted(p.run_days)
            q_keys = _quality_week(ptype, k, p.goal)[: max(0, p.quality - 1)] if ptype != 5 else []
            long_d = p.long_day if p.long_day in run_days else run_days[-1]
            q_days = _quality_days([d for d in run_days if d != long_d], long_d, len(q_keys))
            week_courses = {}
            for key, d in zip(q_keys, q_days):
                w = wk.by_key(key)
                week_courses[d] = _goal_named(wk.build(w, p.vma, p.threshold_pace, goal_pace, a_easy), p.goal)
            vol = vols[wi]
            q_km = sum(pe.course_km(c) for c in week_courses.values())
            long_km = 0.0
            if ptype != 5:
                long_km = min(LONG_MAX[p.goal], max(10.0, round(vol * 0.3)))
                with_pace = ptype in (3, 4) and p.quality >= 3
                if with_pace:
                    fast = round(min(8.0, long_km * 0.3))
                    week_courses[long_d] = pe.build("longue_allure", {"km": long_km, "fast_km": fast,
                                                                       "pace": (round(goal_pace) - 2, round(goal_pace) + 6)
                                                                       if p.goal in ("Semi-marathon", "Marathon")
                                                                       else (round(p.threshold_pace) - 3, round(p.threshold_pace) + 7),
                                                                       "easy": a_easy})
                else:
                    week_courses[long_d] = pe.build("longue", {"km": long_km, "easy": a_easy})
            easy_days = [d for d in run_days if d not in week_courses]
            left = max(0.0, vol - q_km - long_km)
            for i, d in enumerate(easy_days):
                km = max(5.0, round(left / len(easy_days) * 2) / 2) if easy_days else 0
                tpl = "footing_acc" if d == long_d - 1 or (i == len(easy_days) - 1 and ptype != 5) else "footing"
                week_courses[d] = pe.build(tpl, {"km": km, "easy": a_easy})
            if ptype == 5:  # race week: short sharpening, then the race
                race_wd = p.race_date.weekday()
                week_courses = {d: c for d, c in week_courses.items() if d < race_wd - 1}
                if race_wd >= 3:
                    sharpen = wk.customise(wk.by_key("spe-1k"), reps=3, rec=120)
                    week_courses[min(1, race_wd - 3)] = _goal_named(wk.build(sharpen, p.vma, p.threshold_pace, goal_pace, a_easy), p.goal)
                week_courses[race_wd - 1] = pe.build("footing_acc", {"km": 4, "easy": a_easy, "strides": 4})
                m, sec = divmod(round(p.goal_time), 60)
                week_courses[race_wd] = {"sportType": 1, "courseName": f"COURSE - {p.goal}",
                                         "courseDescription": f"Jour J : {p.goal}, objectif {m // 60 and f'{m // 60}:{m % 60:02d}' or m}:{sec:02d} "
                                                              "soit " + f"{int(goal_pace // 60)}:{int(goal_pace % 60):02d}/km. Départ prudent, accélère après la mi-course.",
                                         "sections": [pe.section("work", "distance", GOALS[p.goal], (round(goal_pace) - 4, round(goal_pace) + 4))]}
            for d, c in week_courses.items():
                days[(ws + timedelta(days=d)).isoformat()] = [c]
        w0 += n
    overview = (f"{p.weeks} semaines vers le {p.goal} du {p.race_date.strftime('%d/%m/%Y')}, objectif "
                f"{int(p.goal_time // 3600) and str(int(p.goal_time // 3600)) + ':' or ''}{int(p.goal_time % 3600 // 60):02d}:{int(p.goal_time % 60):02d}. "
                f"{len(p.run_days)} sorties par semaine dont {p.quality} de qualité, de {p.start_km:.0f} à {p.peak_km:.0f} km par semaine, "
                "semaine plus légère toutes les 4 semaines, affûtage sur les 2 dernières.")
    return {"start": start.isoformat(), "weeks": p.weeks, "phases": ph, "days": days, "overview": overview,
            "volumes": vols}


# ---- drafts stored locally --------------------------------------------------------------------------------

def drafts(db: DB) -> list[dict]:
    return json.loads(db.get_meta("plan_drafts") or "[]")


def save_draft(db: DB, p: Params, plan: dict, draft_id: str | None = None) -> str:
    items = [d for d in drafts(db) if d["id"] != draft_id]
    did = draft_id or f"d{len(items) + 1}-{date.today().strftime('%Y%m%d%H%M%S')}"
    items.append({"id": did, "params": {**asdict(p), "race_date": p.race_date.isoformat()}, "plan": plan,
                  "created": date.today().isoformat(), "status": "brouillon"})
    db.set_meta("plan_drafts", json.dumps(items))
    return did


def delete_draft(db: DB, draft_id: str) -> None:
    db.set_meta("plan_drafts", json.dumps([d for d in drafts(db) if d["id"] != draft_id]))


def set_draft_day(db: DB, draft_id: str, day: str, courses: list[dict]) -> None:
    items = drafts(db)
    for d in items:
        if d["id"] == draft_id:
            if courses:
                d["plan"]["days"][day] = courses
            else:
                d["plan"]["days"].pop(day, None)
    db.set_meta("plan_drafts", json.dumps(items))


def creatable_from(draft: dict) -> date:
    """COROS accepts a new plan only if it starts within the next 14 days."""
    return date.fromisoformat(draft["plan"]["start"]) - timedelta(days=14)


def to_coros(draft: dict) -> dict:
    """createTrainingPlan arguments (ASCII names, as the watch shows them)."""
    plan, prm = draft["plan"], draft["params"]
    start = date.fromisoformat(plan["start"])
    course_list = []
    for day, cs in sorted(plan["days"].items()):
        n = (date.fromisoformat(day) - start).days
        course_list += [pe.to_coros(c, n) for c in cs if c.get("sportType") != 4]
    per = [{"phaseType": x["phaseType"], "startDate": int(x["start"].replace("-", "")),
            "endDate": int(x["end"].replace("-", "")), "durationWeeks": x["weeks"]} for x in plan["phases"]]
    return {"planInfo": {"planName": pe._ascii(prm["name"])[:90], "planOverview": pe._ascii(plan["overview"])[:800],
                         "planStartDate": start.strftime("%Y%m%d"), "totalWeeks": plan["weeks"]},
            "courseList": course_list, "phaseInfo": {"periodization": per}}


async def create_in_coros(s, db: DB, draft_id: str, client=None) -> str:
    from coach.sources.coros_mcp import CorosMCP
    d = next(x for x in drafts(db) if x["id"] == draft_id)
    today = date.today()
    start = date.fromisoformat(d["plan"]["start"])
    if not today <= start <= today + timedelta(days=14):
        raise pe.PlanError(f"COROS n'accepte un nouveau plan que s'il démarre dans les 14 jours (celui-ci : {start:%d/%m/%Y}).")
    args = to_coros(d)
    errs = [e for c in args["courseList"] for e in pe.validate(c)]
    if errs:
        raise pe.PlanError(" ; ".join(errs[:8]))

    async def run(c):
        await c.call("queryTrainingPlanLibrary", {"statusList": [0, 1]})
        return await c.call("createTrainingPlan", args)
    msg = await run(client) if client is not None else await _with(CorosMCP(s), run)
    items = drafts(db)
    for x in items:
        if x["id"] == draft_id:
            x["status"] = "créé dans COROS"
    db.set_meta("plan_drafts", json.dumps(items))
    return "\n".join(ln for ln in msg.splitlines() if "Plan ID" not in ln)


async def _with(ctx, fn):
    async with ctx as c:
        return await fn(c)
