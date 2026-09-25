"""Warnings worth acting on today: short sleep before a hard session, resting HR or HRV off, load running away,
sleep debt, a sudden jump in mileage, missed key sessions."""
from __future__ import annotations

import statistics
from datetime import date, timedelta

from coach.config import Settings
from coach.db import DB

HARD = ("VMA", "Seuil", "Allure", "Tempo", "Fartlek", "Côtes", "Course", "Sortie longue")


def _n(x: float, dec: int = 1) -> str:
    return f"{x:.{dec}f}".replace(".", ",")


def _alert(level: str, title: str, detail: str, advice: str) -> dict:
    return {"level": level, "title": title, "detail": detail, "advice": advice}


def alerts(db: DB, s: Settings, today: date | None = None) -> list[dict]:
    from coach import plan_edit as pe
    from coach import service
    today = today or date.today()
    out = []
    a = service.athlete(db, s)

    # upcoming hard session (plan) in the next 2 days
    upcoming = [d for d in db.plan_days(today.isoformat(), (today + timedelta(days=2)).isoformat())
                if any(pe.is_quality_course(c, a.threshold_pace) or pe.course_km(c) >= 16 for c in pe.day_courses(d))
                and not pe.day_is_done(d)]
    upto = today.isoformat()
    nights = [n for n in db.sleep((today - timedelta(days=4)).isoformat()) if n["date"] <= upto][-3:]
    short = [n for n in nights if (n.get("total_min") or 0) < 390]
    if upcoming and len(short) >= 2:
        d = upcoming[0]
        out.append(_alert("rouge" if len(short) == 3 and all((n["total_min"] or 0) < 360 for n in nights) else "orange",
                          f"Sommeil court avant la séance du {d['date']}",
                          f"{len(short)} des 3 dernières nuits sous 6 h 30 ({', '.join(_n((n['total_min'] or 0) / 60) + ' h' for n in nights)}).",
                          "Vise 8 h 30 cette nuit ; si la nuit reste courte, allège la séance de 20 % (page Plan)."))

    daily = [d for d in db.daily((today - timedelta(days=35)).isoformat()) if d["date"] <= upto]
    rhr = [d["rhr"] for d in daily if d.get("rhr")]
    if len(rhr) >= 10:
        base = statistics.median(rhr[:-3])
        high = [x for x in rhr[-3:] if x >= base + 5]
        if len(high) >= 2:
            out.append(_alert("orange", "FC de repos en hausse",
                              f"{', '.join(f'{x:.0f}' for x in rhr[-3:])} bpm ces 3 derniers jours pour une médiane de {base:.0f} bpm.",
                              "Signe de fatigue, de maladie qui couve ou de chaleur : garde les prochains jours faciles tant qu'elle ne redescend pas."))
    hrv = [d for d in daily if d.get("hrv")][-4:]
    low = [d for d in hrv if (d.get("hrv_lo") and d["hrv"] < d["hrv_lo"]) or "below" in (d.get("hrv_eval") or "").lower()]
    if len(low) >= 3:
        out.append(_alert("orange", "VFC sous la normale",
                          f"{len(low)} des 4 dernières nuits sous ta plage habituelle.",
                          "Récupération incomplète : décale la prochaine séance dure d'un jour ou raccourcis-la."))

    ratios = [d["load_ratio"] for d in daily if d.get("load_ratio")]
    if sum(1 for x in ratios[-3:] if x >= 1.5) >= 2:
        out.append(_alert("rouge", "Charge excessive", f"Ratio de charge COROS à {_n(max(ratios[-3:]), 2)} plusieurs jours de suite.",
                          "Au-delà de 1,5 le risque de blessure grimpe : allège les séances des 7 prochains jours (suggestion dans la page Plan)."))
    elif sum(1 for x in ratios[-5:] if x >= 1.3) >= 3:
        out.append(_alert("orange", "Charge en hausse rapide", f"Ratio de charge au-dessus de 1,3 sur {sum(1 for x in ratios[-5:] if x >= 1.3)} des 5 derniers jours.",
                          "Pas d'ajout de volume cette semaine ; garde une vraie journée facile entre les séances dures."))

    week = [n for n in db.sleep((today - timedelta(days=7)).isoformat()) if n["date"] <= upto]
    debt = sum(max(0, 480 - (n.get("total_min") or 0)) for n in week)
    if len(week) >= 5 and debt >= 300:
        out.append(_alert("orange", "Dette de sommeil", f"{_n(debt / 60)} h sous l'objectif de 8 h sur les 7 dernières nuits.",
                          "Couche-toi plus tôt 2-3 soirs de suite ; une sieste de 20-30 min aide aussi."))

    runs = db.activities((today - timedelta(days=34)).isoformat(), upto)
    last7 = sum(r["distance_km"] or 0 for r in runs if r["date"] > (today - timedelta(days=7)).isoformat())
    prev = [sum(r["distance_km"] or 0 for r in runs if (today - timedelta(days=7 * (k + 1))).isoformat() < r["date"] <= (today - timedelta(days=7 * k)).isoformat())
            for k in range(1, 5)]
    avg_prev = sum(prev) / 4
    if avg_prev >= 10 and last7 > 1.35 * avg_prev:
        out.append(_alert("orange", "Kilométrage en forte hausse", f"{last7:.0f} km sur 7 jours contre {avg_prev:.0f} km en moyenne les 4 semaines précédentes.",
                          "Au-delà de +30 % d'une semaine à l'autre, les blessures de surcharge guettent : stabilise la semaine prochaine."))

    missed = [p for p in service.plan_view(db, s, back=7, ahead=0) if p["status"] == "manquée"
              and p.get("kind") in ("vma", "seuil", "specifique", "longue_specifique")]
    if len(missed) >= 2:
        out.append(_alert("info", f"{len(missed)} séances de qualité manquées cette semaine",
                          "Le plan suppose ces séances ; en rattraper plusieurs d'un coup serait pire que de les laisser.",
                          "Reprogramme au plus une séance (suggestion dans la page Plan), la suite du plan reprend normalement."))
    order = {"rouge": 0, "orange": 1, "info": 2}
    return sorted(out, key=lambda x: order[x["level"]])
