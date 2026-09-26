"""Library of interval workouts, by category, with paces computed from the athlete's VMA, threshold pace and
goal pace. Every workout is parameterised (reps, rep length, intensity, recovery, sets) and turns into a COROS
course (plan_edit.section / group) ready to be put in the plan."""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from coach.plan_edit import JOG, section
from coach.verdict import fpace

CATEGORIES = ["Fractionné court", "Fractionné long", "Seuil", "Allure spécifique 10 km", "Pyramides et mixtes", "Côtes"]
WALK = (700, 1000)
REC_PACE = {False: 415, True: 720}  # s/km: jogged (~8,7 km/h) or walked (~5 km/h) recovery


@dataclass(frozen=True)
class Workout:
    key: str
    category: str
    name: str
    reps: int
    unit: str  # "m" (distance) or "s" (time)
    value: float
    intensity: str  # "vma" (% of VMA) | "seuil" (s/km around threshold) | "objectif" (race goal pace) | "cote" (HR)
    lo: float  # % of VMA, or s/km offset
    hi: float
    rec: float
    rec_unit: str = "s"
    sets: int = 1
    set_rec_s: float = 0
    objective: str = ""
    ladder: tuple = field(default_factory=tuple)  # pyramids: ((metres, %VMA lo, %VMA hi, recovery s), ...)


CATALOG = [
    Workout("15-15", "Fractionné court", "15/15", 10, "s", 15, "vma", 105, 110, 15, sets=2, set_rec_s=180,
            objective="Vitesse maximale aérobie avec très peu d'accumulation : idéal pour démarrer la VMA."),
    Workout("30-30", "Fractionné court", "30/30", 12, "s", 30, "vma", 100, 105, 30,
            objective="Le classique : beaucoup de temps près de VO2max pour une fatigue modérée."),
    Workout("45-15", "Fractionné court", "45/15", 10, "s", 45, "vma", 98, 102, 15,
            objective="Récupération courte : VO2max atteinte vite et maintenue."),
    Workout("1-1", "Fractionné court", "1 min / 1 min", 10, "s", 60, "vma", 98, 103, 60,
            objective="Transition entre VMA courte et longue."),
    Workout("200", "Fractionné court", "200 m", 12, "m", 200, "vma", 105, 110, 45,
            objective="Vitesse et économie de course, peu de fatigue."),
    Workout("300", "Fractionné court", "300 m", 10, "m", 300, "vma", 103, 107, 60),
    Workout("400", "Fractionné court", "400 m", 10, "m", 400, "vma", 100, 105, 75,
            objective="La référence de la VMA courte."),
    Workout("500", "Fractionné court", "500 m", 8, "m", 500, "vma", 100, 103, 90),
    Workout("600", "Fractionné long", "600 m", 8, "m", 600, "vma", 97, 100, 120),
    Workout("800", "Fractionné long", "800 m", 6, "m", 800, "vma", 96, 100, 120,
            objective="VMA longue : endurance à haute intensité, clé pour le 10 km."),
    Workout("1000", "Fractionné long", "1000 m", 6, "m", 1000, "vma", 95, 98, 120,
            objective="La séance reine du 10 km : temps long au-dessus de l'allure course."),
    Workout("1200", "Fractionné long", "1200 m", 5, "m", 1200, "vma", 93, 96, 150),
    Workout("1500", "Fractionné long", "1500 m", 4, "m", 1500, "vma", 91, 94, 150),
    Workout("3min", "Fractionné long", "3 min", 6, "s", 180, "vma", 96, 100, 120),
    Workout("4min", "Fractionné long", "4 min", 5, "s", 240, "vma", 94, 97, 120),
    Workout("seuil-10", "Seuil", "Seuil 3 × 10 min", 3, "s", 600, "seuil", -5, 5, 120,
            objective="Repousser le seuil : l'allure que tu tiens ~1 h."),
    Workout("seuil-15", "Seuil", "Seuil 2 × 15 min", 2, "s", 900, "seuil", -3, 5, 180),
    Workout("seuil-20", "Seuil", "Seuil 2 × 20 min", 2, "s", 1200, "seuil", 0, 8, 180),
    Workout("seuil-2k", "Seuil", "Seuil 4 × 2000 m", 4, "m", 2000, "seuil", -5, 3, 90),
    Workout("tempo-25", "Seuil", "Tempo 25 min continu", 1, "s", 1500, "seuil", 0, 8, 0),
    Workout("spe-1k", "Allure spécifique 10 km", "10 × 1000 m allure 10 km", 10, "m", 1000, "objectif", -3, 3, 60,
            objective="Habituer le corps à l'allure objectif, récupération courte."),
    Workout("spe-1600", "Allure spécifique 10 km", "6 × 1600 m allure 10 km", 6, "m", 1600, "objectif", -3, 3, 90),
    Workout("spe-2k", "Allure spécifique 10 km", "5 × 2000 m allure 10 km", 5, "m", 2000, "objectif", -3, 3, 120,
            objective="La séance test de fin de préparation : 10 km à l'allure objectif."),
    Workout("spe-3k", "Allure spécifique 10 km", "3 × 3000 m allure 10 km", 3, "m", 3000, "objectif", -3, 3, 180),
    Workout("pyr", "Pyramides et mixtes", "Pyramide 200-400-600-800-600-400-200", 1, "m", 0, "vma", 0, 0, 0,
            objective="Varier les allures dans une même séance.",
            ladder=((200, 105, 110, 45), (400, 100, 105, 75), (600, 97, 101, 90), (800, 95, 99, 120),
                    (600, 97, 101, 90), (400, 100, 105, 75), (200, 105, 110, 0))),
    Workout("echelle", "Pyramides et mixtes", "Échelle 1000-800-600-400-200 (de plus en plus vite)", 1, "m", 0, "vma", 0, 0, 0,
            objective="Finir vite sur la fatigue.",
            ladder=((1000, 94, 97, 120), (800, 96, 99, 105), (600, 98, 101, 90), (400, 101, 104, 75), (200, 105, 110, 0))),
    Workout("fartlek", "Pyramides et mixtes", "Fartlek 8 × (2 min vite / 1 min lent)", 8, "s", 120, "vma", 92, 96, 60),
    Workout("cote-30", "Côtes", "10 × 30 s en côte", 10, "s", 30, "cote", 0, 0, 90,
            objective="Force et foulée : côte à 5-8 %, retour en descente trottée."),
    Workout("cote-1", "Côtes", "8 × 1 min en côte", 8, "s", 60, "cote", 0, 0, 120),
]


def by_key(key: str) -> Workout:
    return next(w for w in CATALOG if w.key == key)


def pace_range(w: Workout, vma: float, threshold_pace: float, goal_pace: float, lo=None, hi=None) -> tuple[int, int]:
    """(fast, slow) s/km for the work part."""
    lo, hi = (w.lo if lo is None else lo), (w.hi if hi is None else hi)
    if w.intensity == "vma":
        return round(1000 / (vma * hi / 100)), round(1000 / (vma * lo / 100))
    if w.intensity == "seuil":
        return round(threshold_pace + lo), round(threshold_pace + hi)
    if w.intensity == "objectif":
        return round(goal_pace + lo), round(goal_pace + hi)
    return round(1000 / (vma * 0.95)), round(1000 / (vma * 0.80))  # hills: effort-based, pace only as a guide


def _rec_section(value: float, unit: str, walk: bool) -> dict:
    return section("recovery", "time" if unit == "s" else "distance", value, WALK if walk else JOG)


def build(w: Workout, vma: float, threshold_pace: float, goal_pace: float, easy: tuple[int, int],
          walk: bool = False, warmup_s: int = 1200, cooldown_s: int = 600) -> dict:
    """COROS course: warm-up, the workout, cool-down."""
    from coach.plan_edit import group
    wu = section("warmup", "time", warmup_s, easy)
    cd = section("cooldown", "time", cooldown_s, (easy[0], easy[1] + 5))
    body = []
    if w.ladder:
        for m, plo, phi, rec in w.ladder:
            p = (round(1000 / (vma * phi / 100)), round(1000 / (vma * plo / 100)))
            body.append(section("work", "distance", m, p))
            if rec:
                body.append(_rec_section(rec, "s", walk))
    else:
        p = pace_range(w, vma, threshold_pace, goal_pace)
        work = section("work", "time" if w.unit == "s" else "distance", w.value, p)
        rep = work if w.reps == 1 or not w.rec else group(w.reps, work, _rec_section(w.rec, w.rec_unit, walk))
        if w.reps > 1 and not w.rec:
            rep = group(w.reps, work, _rec_section(30, "s", walk))
        for i in range(w.sets):
            body.append(rep)
            if w.sets > 1 and i < w.sets - 1 and w.set_rec_s:
                body.append(_rec_section(w.set_rec_s, "s", walk))
    return {"sportType": 1, "courseName": name_of(w)[:100], "courseDescription": describe(w, vma, threshold_pace, goal_pace, walk),
            "sections": [wu, *body, cd]}


def _len(w: Workout) -> str:
    if w.unit == "m":
        return f"{w.value / 1000:g} km".replace(".", ",") if w.value >= 1000 and w.value % 1000 == 0 else f"{w.value:g} m"
    return f"{w.value / 60:g} min".replace(".", ",") if w.value >= 60 else f"{w.value:g} s"


def name_of(w: Workout) -> str:
    if w.ladder:
        return w.name
    if w.key.startswith(("15-15", "30-30", "45-15")):
        body = f"{w.reps} × {w.name}"
    elif w.reps == 1:
        return f"{w.category.split(' ')[0]} {_len(w)} continu" if w.intensity != "seuil" else f"Tempo {_len(w)} continu"
    else:
        body = f"{w.reps} × {_len(w)}"
    pre = {"Fractionné court": "VMA courte", "Fractionné long": "VMA longue", "Seuil": "Seuil",
           "Allure spécifique 10 km": "Allure 10 km", "Côtes": "Côtes", "Pyramides et mixtes": "Fartlek"}[w.category]
    return f"{pre} {f'{w.sets} séries de ' if w.sets > 1 else ''}{body}"


def describe(w: Workout, vma: float, threshold_pace: float, goal_pace: float, walk: bool = False) -> str:
    rec = "marchée" if walk else "trottée"
    if w.ladder:
        return f"20 min d'échauffement, {w.name.split(' ', 1)[1]} ({', '.join(f'{m} m' for m, *_ in w.ladder)}), récup {rec}, 10 min de retour au calme."
    lo, hi = pace_range(w, vma, threshold_pace, goal_pace)
    what = f"{w.reps} x {_len(w)}" + (f" en {w.sets} séries" if w.sets > 1 else "")
    inten = "effort soutenu en côte" if w.intensity == "cote" else f"à {fpace(lo)}-{fpace(hi)}/km"
    r = f", récup {w.rec:g} {'s' if w.rec_unit == 's' else 'm'} {rec}" if w.reps > 1 and w.rec else ""
    return f"20 min d'échauffement, {what} {inten}{r}, 10 min de retour au calme. {w.objective}".strip()


def summary(w: Workout, vma: float, threshold_pace: float, goal_pace: float, easy: tuple[int, int], walk: bool = False) -> dict:
    """Per-rep time or distance, recovery, work volume, total distance and duration (warm-up and cool-down
    included). A walked recovery covers about 60 % of the ground of a jogged one in the same time."""
    rp = REC_PACE[walk]
    how = "marchée" if walk else "trottée"
    if w.ladder:
        lo, hi = round(1000 / (vma * max(b for _, _, b, _ in w.ladder) / 100)), round(1000 / (vma * min(a for _, a, _, _ in w.ladder) / 100))
    else:
        lo, hi = pace_range(w, vma, threshold_pace, goal_pace)
    mid = (lo + hi) / 2
    easy_speed = 2000 / (easy[0] + easy[1])
    if w.ladder:
        work_m = sum(m for m, *_ in w.ladder)
        work_s = sum(m * 1000 / (vma * (a + b) / 200) / 1000 for m, a, b, _ in w.ladder)
        rec_s = sum(r for *_, r in w.ladder)
        per = ""
        rec_txt = f"récup {how} entre chaque (~{rec_s * 1000 / rp:.0f} m au total)"
    else:
        per_s = w.value if w.unit == "s" else w.value * mid / 1000
        per_m = w.value if w.unit == "m" else w.value / mid * 1000
        n = w.reps * w.sets
        work_s, work_m = per_s * n, per_m * n
        rec_one = w.rec if w.rec_unit == "s" else w.rec * rp / 1000
        rec_s = rec_one * (w.reps - 1) * w.sets + w.set_rec_s * (w.sets - 1)
        per = (f"{fpace(per_s)} par répétition" if w.unit == "m" else f"~{per_m:.0f} m par répétition")
        if w.reps > 1 and w.rec:
            rec_txt = (f"récup {fpace(w.rec)} {how} (~{w.rec * 1000 / rp:.0f} m)" if w.rec_unit == "s"
                       else f"récup {w.rec:g} m {how} (~{fpace(rec_one)})")
        else:
            rec_txt = "effort continu" if w.reps == 1 else f"récup {how}"
    rec_m = rec_s * 1000 / rp
    total_s = 1200 + 600 + work_s + rec_s
    total_m = (1800 * easy_speed) + work_m + rec_m
    return {"pace": (lo, hi), "per_rep": per, "rec": rec_txt, "rec_s": rec_s, "rec_m": rec_m, "work_m": work_m, "work_s": work_s, "total_m": total_m, "total_s": total_s}


def customise(w: Workout, **changes) -> Workout:
    return replace(w, **{k: v for k, v in changes.items() if v is not None})
