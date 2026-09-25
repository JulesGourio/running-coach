"""Rule-based judgement of a session: type, score out of 10 and findings with numbers."""
from __future__ import annotations

from coach.metrics.intervals import evaluate_steps, flatten_course, is_quality, planned_distance
from coach.metrics.zones import Athlete


def fpace(sec: float | None) -> str:
    if not sec:
        return "—"
    sec = round(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def f1(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


def fkm(m: float | None) -> str:
    return f"{m / 1000:.1f}".replace(".", ",") + " km" if m else "—"


def classify(course: dict | None, metrics: dict, a: Athlete) -> str:
    if course:
        if (course.get("courseName") or "").lower().startswith("course"):
            return "course"
        steps = flatten_course(course)
        q = [st for st in steps if is_quality(st, a.threshold_pace)]
        if q:
            if len(q) < len([st for st in steps if st.kind == "work"]) and planned_distance(course) >= 14000:
                return "longue_specifique"
            ratio = min(st.pace_lo for st in q) / a.threshold_pace
            rep_m = max(st.target_value if st.target_type == 1 else st.target_value * 1000 / st.pace_hi
                        for st in q if st.target_value)
            if ratio < 0.93 and rep_m <= 1300:
                return "vma"
            return "specifique" if ratio < 0.97 else "seuil"
        return "longue" if planned_distance(course) >= 14000 else "footing"
    z = metrics.get("zones_hr") or {}
    hard = z.get("Z4 seuil", 0) + z.get("Z5 VO2max", 0)
    if hard > 0.2:
        return "qualite_libre"
    return "longue" if (metrics.get("distance_m") or 0) >= 15000 else "footing"


TYPE_FR = {"footing": "Footing", "longue": "Sortie longue", "longue_specifique": "Sortie longue avec allure spécifique",
           "seuil": "Seuil", "vma": "VMA / VO2max", "specifique": "Allure spécifique", "course": "Course",
           "qualite_libre": "Séance intense (hors plan)"}


def judge(metrics: dict, a: Athlete, course: dict | None = None, df=None, laps=None) -> dict:
    kind = classify(course, metrics, a)
    findings: list[str] = []
    flags: list[str] = []
    score = 10.0
    z = metrics.get("zones_hr") or {}
    easy_share = z.get("Z1 récup", 0) + z.get("Z2 endurance", 0)
    dec = metrics.get("decoupling") or {}
    dec_pct = dec.get("decoupling_pct")

    planned = None
    if course:
        pd_m = planned_distance(course)
        planned = {"name": course.get("courseName"), "distance_m": pd_m}
        done = metrics.get("distance_m") or 0
        if pd_m and abs(done - pd_m) / pd_m > 0.15:
            findings.append(f"Distance : {fkm(done)} au lieu de {fkm(pd_m)} prévus.")
            score -= 1.0 if done < pd_m else 0.5

    reps = None
    if kind in ("footing", "longue"):
        if z:
            if easy_share < 0.9:
                penalty = min(4.0, (0.9 - easy_share) * 10)
                score -= penalty
                findings.append(f"Seulement {easy_share:.0%} du temps en zone facile (Z1-Z2), pour 90 % visés : "
                                f"la séance a été courue trop fort.")
                flags.append("trop_intense")
            else:
                findings.append(f"Intensité respectée : {easy_share:.0%} du temps en zone facile.")
        if course:
            lo = min((st.pace_lo for st in flatten_course(course) if st.pace_lo), default=None)
            if lo and metrics.get("avg_pace") and metrics["avg_pace"] < lo - 10:
                score -= 1.5
                findings.append(f"Allure moyenne {fpace(metrics['avg_pace'])}/km, plus rapide que la fourchette prévue "
                                f"(pas plus vite que {fpace(lo)}/km).")
                flags.append("trop_rapide")
        if dec_pct is not None:
            limit = 5.0
            if dec_pct > limit:
                score -= 1.5 if dec_pct > 8 else 1.0
                findings.append(f"Découplage cardiaque de {f1(dec_pct)} % (FC {dec['hr_first']:.0f} → {dec['hr_second']:.0f} bpm "
                                f"entre les deux moitiés) : l'endurance n'a pas suivi sur la durée.")
                flags.append("decouplage")
            else:
                findings.append(f"Découplage cardiaque de {f1(dec_pct)} % : endurance solide sur cette durée.")
    elif kind in ("seuil", "vma", "specifique", "longue_specifique", "course") and course and df is not None:
        reps = evaluate_steps(course, df, laps or [], a.threshold_pace)
        n, found, on = reps["n_planned"], reps["n_found"], reps["n_on_target"]
        if n:
            score = reps["score"]
            if n == 1:
                r0 = reps["reps"][0]
                done = r0["done"] or {}
                findings.append(f"Bloc principal à {fpace(done.get('pace'))}/km pour une cible de "
                                f"{fpace(r0['step']['pace_lo'])}–{fpace(r0['step']['pace_hi'])}/km : {r0['status']}.")
            else:
                findings.append(f"{on} répétitions sur {n} dans la cible d'allure (tolérance ± 3 s/km).")
            fast = [r for r in reps["reps"] if r["status"] == "trop rapide"]
            slow = [r for r in reps["reps"] if r["status"] == "trop lente"]
            if fast:
                findings.append(f"{len(fast)} trop rapide{'s' if len(fast) > 1 else ''} (jusqu'à "
                                f"{abs(min(r['delta_s'] for r in fast)):.0f} s/km sous la cible) : fatigue en plus, sans gain.")
                flags.append("reps_trop_rapides")
            if slow:
                findings.append(f"{len(slow)} trop lente{'s' if len(slow) > 1 else ''} (jusqu'à "
                                f"{max(r['delta_s'] for r in slow):.0f} s/km au-dessus de la cible).")
                flags.append("reps_trop_lentes")
            if found < n:
                findings.append(f"{n - found} répétition{'s' if n - found > 1 else ''} non retrouvée{'s' if n - found > 1 else ''} dans les données.")
            if reps["fade_s"] is not None and reps["fade_s"] > 6:
                score -= 1.0
                findings.append(f"Baisse de régime : dernière répétition {reps['fade_s']:.0f} s/km plus lente que la première.")
                flags.append("baisse_de_regime")
            if reps["pace_sd"] is not None and reps["pace_sd"] <= 3 and on == n:
                findings.append(f"Très régulier : écart-type de {f1(reps['pace_sd'])} s/km entre les répétitions.")
    elif kind == "qualite_libre":
        findings.append(f"Séance intense hors plan : {1 - easy_share:.0%} du temps au-dessus de Z2.")
        flags.append("hors_plan")
        score = None

    if metrics.get("hr_p99") and metrics["hr_p99"] > a.hr_max + 2:
        flags.append("fc_max_depassee")
        findings.append(f"FC jusqu'à {metrics['hr_p99']:.0f} bpm, au-dessus de la FC max configurée : "
                        "vérifie le capteur ou mets à jour ATHLETE_HR_MAX.")

    if score is not None:
        score = round(max(0.0, min(10.0, score)), 1)
    headline = TYPE_FR.get(kind, kind)
    if score is not None:
        headline += f" · {score:.1f}/10".replace(".", ",")
    return {"type": kind, "type_fr": TYPE_FR.get(kind, kind), "score": score, "headline": headline,
            "findings": findings, "flags": flags, "planned": planned, "reps": reps}
