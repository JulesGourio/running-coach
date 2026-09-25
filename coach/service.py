"""Read-side views shared by the dashboard, the HTTP API and the MCP server."""
from __future__ import annotations

import json
import statistics
from datetime import date, timedelta

import numpy as np
import pandas as pd

from coach.config import Settings
from coach.db import DB
from coach.metrics import load as loadm
from coach.metrics import progress as prog
from coach.metrics.readiness import advice, readiness
from coach.metrics.zones import Athlete
from coach.sources.parsers import is_done
from coach.text import course_text
from coach.verdict import TYPE_FR, classify

QUALITY = {"seuil", "vma", "specifique", "longue_specifique", "course", "qualite_libre"}


def athlete(db: DB, s: Settings) -> Athlete:
    est = json.loads(db.get_meta("hr_est") or "{}")
    hr_max = s.hr_max or est.get("hr_max") or 195.0
    rhr = [d["rhr"] for d in db.daily((date.today() - timedelta(days=30)).isoformat()) if d.get("rhr")]
    hr_rest = s.hr_rest or (statistics.median(rhr) if rhr else 50.0)
    fit = [f for f in db.fitness() if f.get("threshold")]
    thr = s.threshold_pace or (fit[-1]["threshold"] if fit else 270.0)
    return Athlete(hr_max=hr_max, hr_rest=round(hr_rest), lthr=s.lthr or est.get("lthr"), threshold_pace=thr, sex=s.sex)


def plan_meta(db: DB) -> dict | None:
    p = db.get_meta("plan")
    if not p:
        return None
    plan = json.loads(p)
    plan["phases"] = json.loads(db.get_meta("phases") or "[]")
    return plan


def _session_row(act: dict, an: dict | None, coach: dict | None) -> dict:
    m = (an or {}).get("metrics") or {}
    v = (an or {}).get("verdict") or {}
    return {
        "label_id": act["label_id"], "date": act["date"], "name": act.get("name"), "type": act.get("type"),
        "distance_km": act.get("distance_km"), "duration_s": act.get("duration_s"), "avg_pace": act.get("avg_pace"),
        "avg_hr": act.get("avg_hr"), "has_fit": bool(act.get("fit_path")),
        "kind": v.get("type"), "kind_fr": v.get("type_fr"), "score": v.get("score"), "headline": v.get("headline"),
        "structure": v.get("structure"), "planned": bool(v.get("planned")),
        "findings": v.get("findings", []), "flags": v.get("flags", []),
        "load": m.get("load"), "ef": m.get("ef"), "decoupling": (m.get("decoupling") or {}).get("decoupling_pct"),
        "easy_share": sum((m.get("zones_hr") or {}).get(k, 0) for k in ("Z1 récup", "Z2 endurance")) if m.get("zones_hr") else None,
        "coach_verdict": coach,
    }


def sessions(db: DB, days: int = 60) -> list[dict]:
    since = (date.today() - timedelta(days=days)).isoformat()
    an = db.analyses()
    return [_session_row(a, an.get(a["label_id"]), db.verdict(a["label_id"])) for a in db.activities(since)]


def sessions_between(db: DB, since: str, until: str) -> list[dict]:
    an = db.analyses()
    return [_session_row(a, an.get(a["label_id"]), db.verdict(a["label_id"])) for a in db.activities(since, until)]


def session_detail(db: DB, label_id: str, with_records: bool = False) -> dict | None:
    act = db.activity(label_id)
    if not act:
        return None
    an = db.analysis(label_id)
    out = {"activity": act, "metrics": (an or {}).get("metrics"), "verdict": (an or {}).get("verdict"),
           "coach_verdict": db.verdict(label_id)}
    day = next((d for d in db.plan_days(act["date"], act["date"])), None)
    if day:
        out["planned"] = [{"name": c["name"], "summary": course_text(c.get("json")), "status": c["status"]} for c in day["courses"]]
    if with_records and act.get("fit_path"):
        from coach.fit import read_fit
        fit = read_fit(act["fit_path"])
        out["records"], out["laps"] = fit.records, fit.laps
    return out


def summary_load(act: dict, a: Athlete) -> float:
    """Load of an activity known only by its summary (other sports, or a run without FIT file): 100 per hour at
    threshold heart rate, scaled by the square of the heart-rate reserve fraction (the hrTSS idea); 30 per hour
    without heart rate."""
    hours = (act.get("duration_s") or 0) / 3600
    if act.get("avg_hr") and a.lt_hr > a.hr_rest:
        f = min(1.1, max(0.3, (act["avg_hr"] - a.hr_rest) / (a.lt_hr - a.hr_rest)))
        return hours * 100 * f * f
    return hours * 30


def load_model(db: DB) -> dict:
    from coach.config import get_settings
    an = db.analyses()
    acts = db.activities()
    a = athlete(db, get_settings())
    items = [(x["date"], an[x["label_id"]]["metrics"].get("load") or 0) if x["label_id"] in an else (x["date"], summary_load(x, a))
             for x in acts]
    items += [(x["date"], summary_load(x, a)) for x in db.activities(sports="other")]
    series = loadm.daily_load(items, end=date.today().isoformat())
    model = loadm.fitness_model(series)
    rows = [{"date": a["date"], "distance_m": an[a["label_id"]]["metrics"].get("distance_m") or 0,
             "moving_s": an[a["label_id"]]["metrics"].get("moving_s") or 0, "load": an[a["label_id"]]["metrics"].get("load") or 0,
             "zones_hr": an[a["label_id"]]["metrics"].get("zones_hr")} for a in acts if a["label_id"] in an]
    weekly = loadm.weekly_summary(rows)
    last = model.iloc[-1].to_dict() if len(model) else {}
    return {"model": model, "weekly": weekly, "now": last, **loadm.monotony_strain(series)}


def progress(db: DB, s: Settings) -> dict:
    a = athlete(db, s)
    an = db.analyses()
    acts = [x for x in db.activities() if x["label_id"] in an]
    today = date.today()
    ref_hr = round(0.78 * a.hr_max)

    ef_rows = []
    for x in acts:
        m, v = an[x["label_id"]]["metrics"], an[x["label_id"]]["verdict"]
        if v.get("type") in ("footing", "longue") and m.get("ngp_pace") and m.get("avg_hr"):
            ef_rows.append({"date": x["date"], "avg_hr": m["avg_hr"], "ngp_speed": 1000 / m["ngp_pace"], "ef": m.get("ef")})
    pace_hr = prog.speed_at_hr(ef_rows, ref_hr)

    def best(window_days: int, before: date | None = None):
        end = before or today
        start = (end - timedelta(days=window_days)).isoformat()
        eff, dur = {}, {}
        for x in acts:
            if not (start <= x["date"] <= end.isoformat()):
                continue
            m = an[x["label_id"]]["metrics"]
            for k, t in (m.get("best_efforts") or {}).items():
                if k not in eff or t < eff[k][0]:
                    eff[k] = (t, x["date"])
            for k, v in (m.get("best_durations") or {}).items():
                if int(k) not in dur or v > dur[int(k)]:
                    dur[int(k)] = v
        return eff, dur

    eff90, _ = best(90)
    D = s.goal_distance_m

    # Interval sessions (reps isolated from recovery) are the only near-max efforts in the data: no race or
    # continuous 5/10 km this year. VMA is reverse-engineered from them, then extrapolated to the race.
    rep_sessions = [(date.fromisoformat(x["date"]), an[x["label_id"]]["metrics"].get("quality_segments") or [])
                    for x in acts]
    hr_fits = [(date.fromisoformat(x["date"]), an[x["label_id"]]["metrics"].get("hr_speed")) for x in acts]
    fit = [f for f in db.fitness() if f.get("vo2max") or f.get("p10")]
    last_fit = fit[-1] if fit else {}
    seuil = (1000 / a.threshold_pace) / prog.THRESHOLD_VMA_FRACTION if a.threshold_pace else None
    test = latest_vma_test(db, today)

    def retained(end: date) -> tuple[float | None, str, dict]:
        """Best available VMA at a date: a recent field test, else the heart-rate line of the best interval session
        (never below the paces actually run), else the paces run, else COROS threshold pace."""
        t = latest_vma_test(db, end)
        if t:
            return t["vma"], "manuel" if t["kind"] == "manuel" else "test", {}
        paces = prog.estimate_vma(rep_sessions, a.threshold_pace, a.hr_max, end)
        cardio = prog.vma_from_hr_fits(hr_fits, a.hr_max, end)
        detail = {"paces": paces, "cardio": cardio}
        if cardio:
            return max(cardio["vma"], paces["vma"] if paces else 0), "cardio", detail
        if paces:
            return paces["vma"], "fractionnes", detail
        return seuil, "seuil", detail

    v_ret, source, det = retained(today)
    paces_now, cardio_now = det.get("paces") or prog.estimate_vma(rep_sessions, a.threshold_pace, a.hr_max, today), \
        det.get("cardio") or prog.vma_from_hr_fits(hr_fits, a.hr_max, today)
    vma = {
        "retenue": v_ret, "source": source, "test": test,
        "fractionnes": paces_now["vma"] if paces_now else None,
        "fractionnes_seances": paces_now["sessions"] if paces_now else [],
        "cardio": cardio_now["vma"] if cardio_now else None,
        "cardio_range": (cardio_now["vma_at_95"], cardio_now["vma_at_max"]) if cardio_now else None,
        "cardio_date": cardio_now["date"] if cardio_now else None,
        "seuil": seuil,
        "vo2max": (last_fit["vo2max"] / 3.5) / 3.6 if last_fit.get("vo2max") else None,  # Léger: VO2max ≈ 3.5 × VMA (km/h)
    }
    preds = {}
    if v_ret:
        preds[f"VMA retenue ({VMA_SOURCES[source]})"] = prog.predict_from_vma(v_ret, D)
    # COROS and threshold pace always stay in: converting a VMA to a 10 km time assumes an endurance level (~90 %
    # of VMA held for 40 min) that isn't measured, so no single VMA should decide the prediction alone.
    if last_fit.get("p10"):
        preds["COROS"] = last_fit["p10"]
    if seuil and source != "seuil":
        preds["Allure seuil COROS"] = prog.predict_from_vma(seuil, D)
    estimate = float(np.median(list(preds.values()))) if preds else None

    series = []
    for w in range(8, -1, -1):
        end = today - timedelta(weeks=w)
        v, _, _ = retained(end)
        if v and v != seuil:
            series.append((end, prog.predict_from_vma(v, D)))
    goal_day = date.fromisoformat(s.goal_date) if s.goal_date else None
    spread = (max(preds.values()) - min(preds.values())) / 2 if len(preds) > 1 else 0.0
    proj = prog.projection_from_current(estimate, series, goal_day, today, spread=spread) if goal_day and estimate else None
    probs = {}
    if proj:
        for label, t in (("A", s.goal_a), ("B", s.goal_b)):
            if t:
                probs[label] = prog.prob_under(t, proj)
    # Pace of the reps, session by session, grouped by what kind of session it was: progress on the work
    # actually done, rather than heart-rate based indirect indicators.
    rep_trend = []
    for x in acts:
        if (today - date.fromisoformat(x["date"])).days > 120:
            continue
        v = an[x["label_id"]]["verdict"]
        work = [g for g in an[x["label_id"]]["metrics"].get("quality_segments") or []
                if g.get("avg_pace") and g["duration_s"] >= 40 and g["avg_pace"] < a.threshold_pace * 1.14]
        if work and v.get("type_fr") not in (None, "Footing", "Sortie longue", "Récupération", "Footing + accélérations"):
            rep_trend.append({"date": x["date"], "category": v["type_fr"], "structure": v.get("structure"),
                              "pace": float(np.median([g["avg_pace"] for g in work])),
                              "best": float(min(g["avg_pace"] for g in work)), "n": len(work)})

    return {"athlete": a.__dict__ | {"lt_hr": a.lt_hr}, "ref_hr": ref_hr, "pace_at_hr": pace_hr, "ef_rows": ef_rows,
            "rep_trend": sorted(rep_trend, key=lambda r: r["date"]),
            "best_efforts": eff90, "vma": vma, "estimate": estimate, "predictions": preds,
            "prediction_series": series, "projection": proj, "probabilities": probs}


VMA_SOURCES = {"test": "test", "manuel": "fixée par toi", "cardio": "FC-vitesse", "fractionnes": "allures des fractionnés", "seuil": "seuil COROS"}
TEST_VALID_DAYS = 70


def vma_tests(db: DB) -> list[dict]:
    return json.loads(db.get_meta("vma_tests") or "[]")


def latest_vma_test(db: DB, end: date) -> dict | None:
    """Most recent field test done before `end` and less than 10 weeks old."""
    ok = [t for t in vma_tests(db) if 0 <= (end - date.fromisoformat(t["date"])).days < TEST_VALID_DAYS]
    return max(ok, key=lambda t: t["date"]) if ok else None


def add_vma_test(db: DB, day: str, kind: str, vma: float, detail: str) -> None:
    tests = [t for t in vma_tests(db) if t["date"] != day] + [{"date": day, "kind": kind, "vma": vma, "detail": detail}]
    db.set_meta("vma_tests", json.dumps(sorted(tests, key=lambda t: t["date"])))


def delete_vma_test(db: DB, day: str) -> None:
    db.set_meta("vma_tests", json.dumps([t for t in vma_tests(db) if t["date"] != day]))


RACE_DISTANCES = {"5 km": (5000, "p5"), "10 km": (10000, "p10"), "Semi-marathon": (21097, "half"), "Marathon": (42195, "marathon")}


def predictions_all(db: DB, s: Settings, pr: dict | None = None) -> list[dict]:
    """5 km to marathon: from the retained VMA, from COROS threshold pace, COROS's own predictions, the median of
    those, and the best real run at that distance for reference."""
    from coach import history as hist
    pr = pr or progress(db, s)
    vma = pr["vma"]
    fit = next((f for f in reversed(db.fitness()) if f.get("p10")), {})
    df = hist.frame(db)
    real = {b["distance"]: b for b in hist.best_by_distance(df)} if not df.empty else {}
    out = []
    for name, (dist, key) in RACE_DISTANCES.items():
        m = {}
        if vma.get("retenue"):
            m["VMA retenue"] = prog.predict_from_vma(vma["retenue"], dist)
        if vma.get("seuil"):
            m["Seuil COROS"] = prog.predict_from_vma(vma["seuil"], dist)
        if fit.get(key):
            m["COROS"] = fit[key]
        est = float(np.median(list(m.values()))) if m else None
        r = real.get(name)
        out.append({"distance": name, "meters": dist, "methods": m, "estimate": est,
                    "pace": est / (dist / 1000) if est else None,
                    "real": {"time": r["time"], "date": r["date"].isoformat(), "pace": r["pace"]} if r else None})
    return out


def goal_track(db: DB, s: Settings, pr: dict | None = None) -> list[dict]:
    """Week-by-week record of the estimate, the race-day projection and the chances for goals A and B. The
    current week is (re)written on each call, so the history builds up week after week (earlier weeks aren't
    reconstructed: the estimate combines methods whose past values aren't all known)."""
    pr = pr or progress(db, s)
    track = {t["week"]: t for t in json.loads(db.get_meta("goal_track") or "[]")}
    goal_day = date.fromisoformat(s.goal_date) if s.goal_date else None
    proj = pr["projection"]
    if proj and pr["estimate"]:
        today = date.today()
        wk = (today - timedelta(days=today.weekday())).isoformat()
        track[wk] = {"week": wk, "estimate": pr["estimate"], "projected": proj["projected"], "low": proj["low"],
                     "high": proj["high"], "A": pr["probabilities"].get("A"), "B": pr["probabilities"].get("B"), "source": "mesuré"}
    rows = sorted(track.values(), key=lambda t: t["week"])
    db.set_meta("goal_track", json.dumps(rows))
    return rows


def plan_view(db: DB, s: Settings, back: int = 14, ahead: int = 14) -> list[dict]:
    a = athlete(db, s)
    today = date.today()
    days = db.plan_days((today - timedelta(days=back)).isoformat(), (today + timedelta(days=ahead)).isoformat())
    acts_by_day: dict[str, list] = {}
    an = db.analyses()
    for x in db.activities((today - timedelta(days=back)).isoformat()):
        acts_by_day.setdefault(x["date"], []).append(_session_row(x, an.get(x["label_id"]), None))
    out = []
    for d in days:
        course = next((c["json"] for c in d["courses"] if c.get("json")), None)
        done_acts = acts_by_day.get(d["date"], [])
        if d["rest"] or not d["courses"]:
            status = "repos"
        elif done_acts or any(is_done(c["status"]) for c in d["courses"]):
            status = "faite"
        elif d["date"] < today.isoformat():
            status = "manquée"
        else:
            status = "à venir"
        kind = classify(course, {}, a) if course else None
        out.append({"date": d["date"], "day_no": d["day_no"], "status": status, "kind": kind,
                    "kind_fr": TYPE_FR.get(kind) if kind else None,
                    "courses": [{"name": c["name"], "summary": course_text(c.get("json"))} for c in d["courses"]],
                    "done": done_acts})
    return out


def readiness_today(db: DB, s: Settings) -> dict:
    daily = db.daily((date.today() - timedelta(days=35)).isoformat())
    lm = load_model(db)
    tsb = lm["now"].get("tsb") if lm["now"] else None
    r = readiness(daily, None if tsb is None or pd.isna(tsb) else float(tsb))
    today = next((p for p in plan_view(db, s, back=0, ahead=0) if p["date"] == date.today().isoformat()), None)
    kind = today["kind"] if today and today["status"] == "à venir" else None
    r["today"] = today
    r["advice"] = advice(r["level"], kind) if r["score"] is not None else None
    return r


def overview(db: DB, s: Settings) -> dict:
    """Compact summary for Claude (MCP) and the API."""
    lm = load_model(db)
    now = {k: (None if v is None or pd.isna(v) else round(float(v), 2)) for k, v in lm["now"].items()}
    pr = progress(db, s)
    return {
        "date": date.today().isoformat(),
        "objectif": {"label": s.goal_label, "date": s.goal_date, "temps_A_s": s.goal_a, "temps_B_s": s.goal_b},
        "forme_du_jour": readiness_today(db, s),
        "charge": {**now, "monotony": lm["monotony"], "strain": lm["strain"]},
        "predictions_s": {k: round(v) for k, v in pr["predictions"].items()},
        "estimation_10km_s": round(pr["estimate"]) if pr["estimate"] else None,
        "projection": pr["projection"],
        "probabilites": pr["probabilities"],
        "vma_m_s": pr["vma"],
        "predictions_distances": [{"distance": r["distance"], "estimation_s": round(r["estimate"]) if r["estimate"] else None,
                                   "methodes_s": {k: round(v) for k, v in r["methods"].items()}, "meilleure_reelle": r["real"]}
                                  for r in predictions_all(db, s, pr)],
        "dernieres_seances": [{k: r[k] for k in ("label_id", "date", "name", "kind_fr", "score", "findings", "distance_km")}
                              for r in sessions(db, 14)],
        "a_venir": [p for p in plan_view(db, s, back=0, ahead=10) if p["status"] == "à venir"],
    }
