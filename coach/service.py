"""Read-side views shared by the dashboard, the HTTP API and the MCP server."""
from __future__ import annotations

import json
import statistics
from datetime import date, timedelta

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
        "findings": v.get("findings", []), "flags": v.get("flags", []),
        "load": m.get("load"), "ef": m.get("ef"), "decoupling": (m.get("decoupling") or {}).get("decoupling_pct"),
        "easy_share": sum((m.get("zones_hr") or {}).get(k, 0) for k in ("Z1 récup", "Z2 endurance")) if m.get("zones_hr") else None,
        "coach_verdict": coach,
    }


def sessions(db: DB, days: int = 60) -> list[dict]:
    since = (date.today() - timedelta(days=days)).isoformat()
    an = db.analyses()
    return [_session_row(a, an.get(a["label_id"]), db.verdict(a["label_id"])) for a in db.activities(since)]


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


def load_model(db: DB) -> dict:
    an = db.analyses()
    acts = db.activities()
    items = [(a["date"], an[a["label_id"]]["metrics"].get("load") or 0) for a in acts if a["label_id"] in an]
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
    _, dur42 = best(42)
    cs = prog.critical_speed(dur42)
    D = s.goal_distance_m
    preds = {}
    coros = [f for f in db.fitness() if f.get("p10")]
    if coros:
        preds["COROS"] = coros[-1]["p10"]
    if cs:
        preds["Vitesse critique"] = prog.predict_from_cs(cs, D)
    if "5000" in eff90:
        preds["Riegel (meilleur 5 km)"] = prog.riegel(eff90["5000"][0], 5000, D)
    vds = [prog.vdot(int(k), eff90[k][0]) for k in ("3000", "5000", "10000", "21097") if k in eff90]
    vd = max(vds) if vds else None
    if vd:
        preds["VDOT"] = prog.time_for_vdot(vd, D)

    series = [(date.fromisoformat(f["date"]), f["p10"]) for f in coros]
    if len(series) < 3:
        series = []
        for w in range(8, -1, -1):
            end = today - timedelta(weeks=w)
            e, _ = best(42, end)
            vs = [prog.vdot(int(k), e[k][0]) for k in ("3000", "5000", "10000") if k in e]
            if vs:
                series.append((end, prog.time_for_vdot(max(vs), D)))
    goal_day = date.fromisoformat(s.goal_date) if s.goal_date else None
    proj = prog.projection(series, goal_day) if goal_day and series else None
    probs = {}
    if proj:
        for label, t in (("A", s.goal_a), ("B", s.goal_b)):
            if t:
                probs[label] = prog.prob_under(t, proj)
    return {"athlete": a.__dict__ | {"lt_hr": a.lt_hr}, "ref_hr": ref_hr, "pace_at_hr": pace_hr, "ef_rows": ef_rows,
            "best_efforts": eff90, "critical_speed": cs, "vdot": vd, "predictions": preds,
            "prediction_series": series, "projection": proj, "probabilities": probs}


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
        "projection": pr["projection"],
        "probabilites": pr["probabilities"],
        "vitesse_critique": pr["critical_speed"],
        "dernieres_seances": [{k: r[k] for k in ("label_id", "date", "name", "kind_fr", "score", "findings", "distance_km")}
                              for r in sessions(db, 14)],
        "a_venir": [p for p in plan_view(db, s, back=0, ahead=10) if p["status"] == "à venir"],
    }
