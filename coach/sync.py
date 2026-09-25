"""Fetch data from COROS into the local database, then analyze new activities."""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date, timedelta
from typing import Callable

import numpy as np

from coach.config import Settings
from coach.db import DB
from coach.fit import read_fit
from coach.metrics.session import compute_session_metrics
from coach.service import athlete
from coach.sources.coros_mcp import CorosError, CorosMCP
from coach.sources.coros_web import CorosWeb
from coach.verdict import judge

Log = Callable[[str], None]


def ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


async def sync_mcp(s: Settings, db: DB, days: int = 30, max_fit: int = 15, interactive: bool = False,
                   log: Log = print) -> dict:
    today = date.today()
    start = today - timedelta(days=days)
    stats = {"activities": 0, "fit": 0, "fit_errors": 0}
    async with CorosMCP(s, interactive=interactive) as c:
        for a in await c.sport_records(ymd(start), ymd(today)):
            db.upsert_activity({**a, "source": "coros"})
            stats["activities"] += 1
        stats["fit"], stats["fit_errors"] = await _download_missing(db, s, max_fit, c.download_fit, log)

        fit = await c.fitness()
        rec = await c.recovery()
        db.upsert_fitness(today.isoformat(), **(fit or {}), recovery_pct=(rec or {}).get("pct"))
        for r in await c.load(min(days, 60)):
            db.upsert_daily(r["date"], load_st=r["st"], load_lt=r["lt"], load_ratio=r["ratio"], load_comment=r["comment"])
        for r in await c.hrv(ymd(today - timedelta(days=6)), ymd(today)):
            db.upsert_daily(**r)
        for r in await c.sleep(7):
            db.upsert_daily(**r)
        for r in await c.rhr(min(days, 60)):
            db.upsert_daily(**r)

        await refresh_plan(c, db)
    log(f"COROS : {stats['activities']} séances, {stats['fit']} fichiers FIT téléchargés.")
    return stats


async def refresh_plan(c: CorosMCP, db: DB, start: date | None = None, end: date | None = None) -> dict | None:
    """Store the in-progress plan (the whole plan by default) locally, in 28-day windows (the COROS maximum)."""
    plan = await c.plan()
    if not plan:
        return None
    db.set_meta("plan", json.dumps(plan))
    p0, p1 = date.fromisoformat(plan["start"]), date.fromisoformat(plan["end"])
    a, stop = max(start or p0, p0), min(end or p1, p1)
    while a <= stop:
        b = min(a + timedelta(days=27), stop)
        details = await c.plan_details(plan["id"], ymd(a), ymd(b))
        if details["phases"]:
            db.set_meta("phases", json.dumps(details["phases"]))
        for d in details["days"]:
            db.upsert_plan_day(d["date"], d["day_no"], d["rest"], d["courses"])
        a = b + timedelta(days=1)
    return plan


def sync_web(s: Settings, db: DB, days: int = 30, max_fit: int = 15, log: Log = print) -> dict:
    today = date.today()
    web = CorosWeb(s.coros_email, s.coros_password, s.coros_region)
    acts = web.activities(ymd(today - timedelta(days=days)), ymd(today))
    for a in acts:
        db.upsert_activity({**a, "source": "coros-web"})

    async def dl(label, sport, dest):
        return web.download_fit(label, sport, dest)

    n, errs = asyncio.run(_download_missing(db, s, max_fit, dl, log))
    log(f"COROS (API non officielle) : {len(acts)} séances, {n} fichiers FIT téléchargés.")
    return {"activities": len(acts), "fit": n, "fit_errors": errs}


async def _download_missing(db: DB, s: Settings, max_fit: int, download, log: Log) -> tuple[int, int]:
    todo = [a for a in db.activities() if not a["fit_path"] and a["sport_type"]][:max_fit]
    ok = err = 0
    for a in todo:
        dest = s.fit_dir / f"{a['label_id']}.fit"
        try:
            await download(a["label_id"], a["sport_type"], dest)
            db.set_fit_path(a["label_id"], str(dest))
            ok += 1
        except (CorosError, OSError, ValueError) as e:
            err += 1
            log(f"FIT {a['date']} ({a['label_id']}) non téléchargé : {e}")
            if "limit" in str(e).lower():
                break
    return ok, err


def _profile_key(a) -> str:
    return hashlib.sha1(json.dumps(a.__dict__, sort_keys=True, default=str).encode()).hexdigest()


def estimate_heart_rates(db: DB, days: int = 120) -> dict:
    """HR max: second highest per-activity 99.5th percentile (ignores a single sensor spike).
    LTHR: best 20-minute average HR while running, the classic field-test proxy for threshold HR."""
    since = (date.today() - timedelta(days=days)).isoformat()
    peaks, best20 = [], []
    for a in db.activities(since):
        if not a["fit_path"]:
            continue
        try:
            rec = read_fit(a["fit_path"]).records
        except Exception:  # noqa: BLE001 - one corrupt file must not stop the estimate
            continue
        hr = rec["hr"].where(rec["speed"] > 1.2)
        if hr.notna().sum() > 300:
            peaks.append(float(np.nanpercentile(hr, 99.5)))
        if hr.notna().sum() > 1200:
            best20.append(float(hr.rolling(1200, min_periods=1000).mean().max()))
    out = {}
    if peaks:
        peaks.sort(reverse=True)
        out["hr_max"] = round(peaks[1] if len(peaks) > 2 else peaks[0])
    if best20:
        out["lthr"] = round(max(best20))
        out["hr_max"] = max(out.get("hr_max", 0), round(out["lthr"] / 0.95))
    return out


def analyze(s: Settings, db: DB, force: bool = False, log: Log = print) -> int:
    done = db.analyses()
    pending = [x for x in db.activities() if x["fit_path"] and x["label_id"] not in done]
    if force or pending or db.get_meta("hr_est") is None:
        est = estimate_heart_rates(db)
        if est:
            db.set_meta("hr_est", json.dumps(est))
    a = athlete(db, s)
    key = _profile_key(a)
    if db.get_meta("profile_key") != key:
        force = True
        db.set_meta("profile_key", key)
    plan = {d["date"]: d for d in db.plan_days()}
    n = 0
    for act in db.activities():
        if not act["fit_path"] or (act["label_id"] in done and not force):
            continue
        try:
            fit = read_fit(act["fit_path"])
        except Exception as e:  # noqa: BLE001
            log(f"Lecture impossible de {act['fit_path']} : {e}")
            continue
        m = compute_session_metrics(fit.records, a, fit.session, fit.laps)
        day = plan.get(act["date"])
        course = next((c["json"] for c in (day or {}).get("courses", []) if c.get("json") and c["json"].get("sportType") in (1, 5)), None)
        v = judge(m, a, course, fit.records, fit.laps, act.get("sport_type"))
        db.save_analysis(act["label_id"], m, v)
        n += 1
    log(f"{n} séance{'s' if n > 1 else ''} analysée{'s' if n > 1 else ''}.")
    return n
