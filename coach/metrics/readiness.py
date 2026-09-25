"""Daily readiness from HRV, resting HR, sleep and training freshness."""
from __future__ import annotations

import numpy as np


def _z(values: list[float], today: float | None) -> float | None:
    vals = [v for v in values if v is not None]
    if today is None or len(vals) < 5:
        return None
    sd = float(np.std(vals)) or 1.0
    return (today - float(np.mean(vals))) / sd


def readiness(daily: list[dict], tsb: float | None) -> dict:
    """daily: rows sorted by date with hrv, hrv_eval, rhr, sleep_score. The last row is today."""
    if not daily:
        return {"score": None, "level": "inconnu", "reasons": ["Pas de données de récupération."]}
    base, today = daily[-29:-1], daily[-1]
    last_hrv = next((d for d in reversed(daily[-2:]) if d.get("hrv") is not None), {})
    last_rhr = next((d for d in reversed(daily[-2:]) if d.get("rhr") is not None), {})
    last_sleep = next((d for d in reversed(daily[-2:]) if d.get("sleep_score") is not None), {})
    reasons, score = [], 70.0

    z_hrv = _z([d.get("hrv") for d in base], last_hrv.get("hrv"))
    if z_hrv is not None:
        score += 8 * max(-2.5, min(1.5, z_hrv))
        if z_hrv < -1:
            reasons.append(f"VFC basse : {last_hrv['hrv']:.0f} ms, nettement sous ta moyenne récente.")
    elif "below" in (last_hrv.get("hrv_eval") or "").lower():
        score -= 12
        reasons.append(f"VFC sous la normale ({last_hrv['hrv']:.0f} ms).")

    z_rhr = _z([d.get("rhr") for d in base], last_rhr.get("rhr"))
    if z_rhr is not None:
        score -= 6 * max(-1.5, min(2.5, z_rhr))
        if z_rhr > 1:
            reasons.append(f"FC de repos haute : {last_rhr['rhr']:.0f} bpm.")

    s = last_sleep.get("sleep_score")
    if s is not None:
        score += (s - 75) * 0.3
        if s < 65:
            reasons.append(f"Nuit courte ou agitée (score {s:.0f}/100).")

    if tsb is not None:
        score += max(-15.0, min(8.0, tsb * 0.5))
        if tsb < -20:
            reasons.append(f"Fatigue accumulée : fraîcheur (TSB) à {tsb:.0f}.")

    score = float(max(0, min(100, score)))
    level = "vert" if score >= 70 else "orange" if score >= 50 else "rouge"
    if not reasons:
        reasons.append("Indicateurs de récupération dans tes valeurs habituelles.")
    return {"score": round(score), "level": level, "reasons": reasons, "date": today.get("date")}


def advice(level: str, planned_kind: str | None) -> str:
    quality = planned_kind in ("seuil", "vma", "specifique", "longue_specifique")
    if planned_kind is None:
        return "Pas de séance prévue aujourd'hui."
    if level == "rouge":
        return ("Remplace la séance de qualité par 30 à 40 min de footing très facile, ou repose-toi."
                if quality else "Raccourcis le footing et garde-le très facile.")
    if level == "orange":
        return ("Garde la séance mais vise le haut de la fourchette d'allure et retire une répétition si les jambes ne suivent pas."
                if quality else "Séance maintenue, en restant bien en Z1-Z2.")
    return "Feu vert : séance maintenue comme prévu."
