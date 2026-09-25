"""Rule-based judgement of a session: type, score out of 10 and findings with numbers."""
from __future__ import annotations

from coach.metrics.intervals import evaluate_steps, flatten_course, is_quality, is_stride, planned_distance
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
            # middle of the target range: a seuil block written 4:12-4:22 is still seuil, not 10 km pace
            ratio = min((st.pace_lo + st.pace_hi) / 2 for st in q) / a.threshold_pace
            rep_m = max(st.target_value if st.target_type == 1 else st.target_value * 1000 / st.pace_hi
                        for st in q if st.target_value)
            if ratio < 0.93 and rep_m <= 1300:
                return "vma"
            return "specifique" if ratio < 0.97 else "seuil"
        return "longue" if planned_distance(course) >= 14000 else "footing"
    hard = hard_segments(metrics, a)
    fast_s = sum(s["duration_s"] for s in hard if s["avg_pace"] < a.threshold_pace * 1.05)
    tempo_s = sum(s["duration_s"] for s in hard)
    if fast_s >= 180 or tempo_s >= 900:
        return "qualite_libre"
    return "longue" if (metrics.get("distance_m") or 0) >= 15000 else "footing"


def hard_segments(metrics: dict, a: Athlete) -> list[dict]:
    """Detected segments that are real work: tempo or faster (under 114 % of threshold pace), not the
    upper end of an easy run."""
    return [s for s in metrics.get("quality_segments") or []
            if s.get("avg_pace") and s["avg_pace"] < a.threshold_pace * 1.14]


CATEGORIES = ["Récupération", "Footing", "Footing + accélérations", "Sortie longue", "Sortie longue avec allure",
              "VMA courte", "VMA longue", "Allure spécifique", "Seuil", "Tempo", "Fartlek", "Côtes", "Course / effort à fond"]


def _median(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2


def _dist(m: float) -> str:
    if m < 1000:
        return f"{round(m / 50) * 50:.0f} m"
    km = round(m / 100) / 10
    return (f"{km:g}".replace(".", ",")) + " km"


def _dur(s: float) -> str:
    return f"{round(s / 60):.0f} min" if abs(s / 60 - round(s / 60)) < 0.08 and s >= 120 else f"{int(s // 60)}:{int(round(s % 60)):02d}"


def structure(segs: list[dict]) -> str:
    """What was run, e.g. "12 × 400 m", "5 × 3 min", "3 × 2 km", "8 km continu"."""
    n = len(segs)
    if not n:
        return ""
    d, t = [s["distance_m"] for s in segs], [s["duration_s"] for s in segs]
    md, mt = _median(d), _median(t)
    if n == 1:
        return f"{_dist(md)} continu"
    if all(abs(x - md) <= 0.08 * md for x in d):
        return f"{n} × {_dist(md)}"
    if all(abs(x - mt) <= 0.10 * mt for x in t):
        return f"{n} × {_dur(mt)}"
    return f"{n} efforts de {_dist(min(d))} à {_dist(max(d))}"


def describe_done(metrics: dict, a: Athlete, sport_type: int | None = None) -> dict:
    """Session type from what was actually run, whatever the plan said: the detected reps (watch laps or
    GPS stream), their duration, their pace relative to threshold pace and their slope."""
    dist, mov = metrics.get("distance_m") or 0, metrics.get("moving_s") or 0
    suffix = {101: " (tapis)", 102: " (trail)", 103: " (piste)"}.get(sport_type or 0, "")
    thr = a.threshold_pace
    long_run = dist >= 16000 or mov >= 75 * 60
    segs = hard_segments(metrics, a)
    # downhill stretches (trail) are fast without being an effort
    work = [s for s in segs if s["duration_s"] >= 40 and s.get("grade", 0) > -0.04]
    strides = [s for s in metrics.get("quality_segments") or [] if s["duration_s"] < 40 and s.get("avg_pace")
               and s["avg_pace"] < thr]
    fast_s = sum(s["duration_s"] for s in work if s["avg_pace"] < thr * 1.05)
    tempo_s = sum(s["duration_s"] for s in work)
    if fast_s < 180 and tempo_s < 900:
        z2_slow = a.pace_zone_bounds()[1][2]
        if long_run:
            cat = "Sortie longue"
        elif len(strides) >= 3:
            cat = "Footing + accélérations"
        elif mov < 35 * 60 and (metrics.get("avg_pace") or 0) > z2_slow:
            cat = "Récupération"
        else:
            cat = "Footing"
        return {"category": cat, "structure": "", "label": f"{cat}{suffix} · {_dist(dist)}" if dist else cat + suffix}
    r = _median([s["avg_pace"] for s in work]) / thr
    d_med = _median([s["duration_s"] for s in work])
    n = len(work)
    durs = [s["duration_s"] for s in work]
    cv = (sum((x - sum(durs) / n) ** 2 for x in durs) / n) ** 0.5 / (sum(durs) / n)
    if long_run and tempo_s < 0.6 * mov:
        cat = "Sortie longue avec allure"
    elif n >= 3 and _median([s.get("grade", 0) for s in work]) >= 0.04:
        cat = "Côtes"
    elif n == 1 or (n == 2 and d_med >= 900):
        cat = ("Course / effort à fond" if r < 0.93 and d_med >= 600 else "Allure spécifique" if r < 0.98
               else "Seuil" if r < 1.05 else "Tempo")
    elif n >= 4 and cv > 0.35:
        cat = "Fartlek"
    elif d_med <= 120 and r < 1.0:
        cat = "VMA courte"
    elif d_med <= 360 and r < 0.97:
        cat = "VMA longue"
    else:
        cat = "Allure spécifique" if r < 0.97 else "Seuil" if r < 1.05 else "Tempo"
    struct = structure(work)
    if cat == "Sortie longue avec allure":
        struct = f"{_dist(dist)} dont {_dist(sum(s['distance_m'] for s in work))} rapides"
    return {"category": cat, "structure": struct, "label": f"{cat}{suffix} · {struct}"}


TYPE_FR = {"footing": "Footing", "longue": "Sortie longue", "longue_specifique": "Sortie longue avec allure spécifique",
           "seuil": "Seuil", "vma": "VMA / VO2max", "specifique": "Allure spécifique", "course": "Course",
           "qualite_libre": "Séance intense (hors plan)"}


def judge(metrics: dict, a: Athlete, course: dict | None = None, df=None, laps=None, sport_type: int | None = None) -> dict:
    kind = classify(course, metrics, a)
    done_type = describe_done(metrics, a, sport_type)
    findings: list[str] = []
    flags: list[str] = []
    score = 10.0
    libre_segments: list[dict] = []
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
            lo = min((st.pace_lo for st in flatten_course(course) if st.pace_lo and not is_stride(st)), default=None)
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
        segs = hard_segments(metrics, a)
        paces = [sg["avg_pace"] for sg in segs]
        if paces:
            n, total_m = len(segs), sum(sg.get("distance_m") or 0 for sg in segs)
            unit, e = (("bloc", "") if done_type["category"].startswith(("Sortie longue", "Tempo", "Seuil", "Course"))
                       else ("répétition", "e"))
            pl = "s" if n > 1 else ""
            findings.append(f"{n} {unit}{pl} rapide{pl} détecté{e}{pl} "
                            f"({fkm(total_m)} au total), {fpace(sum(paces) / len(paces))}/km en moyenne "
                            f"pour une allure seuil de {fpace(a.threshold_pace)}/km.")
            if len(paces) > 2 and unit == "répétition":
                mean_p = sum(paces) / len(paces)
                sd = (sum((p - mean_p) ** 2 for p in paces) / len(paces)) ** 0.5
                findings.append(f"Régularité : écart-type de {f1(sd)} s/km entre les répétitions"
                                + (" — très homogène." if sd <= 3 else "." if sd <= 8 else " — allures dispersées."))
                if paces[-1] < paces[0] - 3:
                    findings.append(f"Finie plus vite qu'entamée ({fpace(paces[0])} → {fpace(paces[-1])}/km) : bonne gestion.")
            libre_segments = [{"n": i + 1, "duration_s": sg["duration_s"], "distance_m": sg.get("distance_m"),
                               "pace": sg.get("avg_pace"), "avg_hr": sg.get("avg_hr"), "source": sg.get("source")}
                              for i, sg in enumerate(segs)]
        else:
            findings.append(f"Séance intense hors plan : {1 - easy_share:.0%} du temps au-dessus de Z2.")
        score = None

    if metrics.get("hr_p99") and metrics["hr_p99"] > a.hr_max + 2:
        flags.append("fc_max_depassee")
        findings.append(f"FC jusqu'à {metrics['hr_p99']:.0f} bpm, au-dessus de la FC max configurée : "
                        "vérifie le capteur ou mets à jour ATHLETE_HR_MAX.")

    if not course:
        flags.append("hors_plan")
        score = None  # a mark only means "how well the plan was followed": nothing to compare without a plan
    elif score is not None:
        score = round(max(0.0, min(10.0, score)), 1)
    return {"type": kind, "type_fr": done_type["category"], "structure": done_type["structure"],
            "headline": done_type["label"], "score": score, "findings": findings, "flags": flags,
            "planned": planned, "reps": reps, "segments": libre_segments}
