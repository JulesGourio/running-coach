"""The running coach on the phone: screens and actions drawn by the Android kit (`android/kit`).

Every screen is a function returning `appkit.ui` blocks, built from the same `service`, `metrics`, `plan_edit`…
as the Streamlit dashboard. The Kotlin shell starts this module (`appkit.bridge.start("coach.mobile", …)`),
runs `sync` every morning, and never computes anything itself.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path

from appkit import App

from coach.config import Settings, get_settings
from coach.db import DB

log = logging.getLogger(__name__)

app = App(
    "Carnet de course",
    tabs=[("aujourdhui", "Aujourd'hui", "today"), ("seances", "Séances", "run"), ("plan", "Plan", "calendar"),
          ("progression", "Progrès", "trend"), ("plus", "Plus", "more")],
    sync_hour=7, sync_minute=15,
)


def ctx() -> tuple[Settings, DB]:
    s = get_settings()
    return s, DB(s.db_path)


@app.on_start
def start(data_dir: Path, secrets, notifier) -> None:
    os.environ["COACH_DATA_DIR"] = str(data_dir)
    os.environ.setdefault("COACH_COROS_CLIENT", "light")
    from coach import notify, vault
    if secrets is not None:
        vault.use(secrets)
    notify.set_local(notifier)
    s, _ = ctx()
    s.fit_dir.mkdir(parents=True, exist_ok=True)


# ---- background sync ----------------------------------------------------------------------------------------

def run_sync(days: int = 21, max_fit: int = 15) -> list[str]:
    from coach import notify, report, service
    from coach.sources.coros_base import NeedsLogin, describe
    from coach.sync import analyze, sync_mcp, sync_web

    s, db = ctx()
    lines: list[str] = []
    before = set(db.analyses())
    try:
        asyncio.run(sync_mcp(s, db, days=days, max_fit=max_fit, log=lines.append))
    except NeedsLogin as e:
        lines.append(str(e))
        notify.send("COROS à reconnecter", f"{e} La synchro du matin n'a rien récupéré.", 4)
    except Exception as e:  # noqa: BLE001 - try the web API, then report
        lines.append(f"COROS : échec — {describe(e)}")
        if s.coros_email and s.coros_password:
            try:
                sync_web(s, db, days=days, max_fit=max_fit, log=lines.append)
            except Exception as e2:  # noqa: BLE001
                lines.append(f"API web COROS : échec — {describe(e2)}")
    analyze(s, db, log=lines.append)
    try:
        report.ensure_last_week(db, s)
        service.goal_track(db, s)
    except Exception as e:  # noqa: BLE001 - the screens recompute them anyway
        log.exception("bilan")
        lines.append(f"Bilan : {e}")
    notify_news(s, db, before)
    return lines


def notify_news(s: Settings, db: DB, before: set[str]) -> None:
    """One notification for the new alerts of the day, one per newly analysed run, the weekly report on Monday."""
    from coach import alerts as al
    from coach import notify, report, service

    sent = set(json.loads(db.get_meta("mobile_notified") or "[]"))
    today = date.today().isoformat()
    new = [x for x in al.alerts(db, s) if f"{today}|{x['title']}" not in sent]
    if new:
        top = 4 if any(x["level"] == "rouge" for x in new) else 3
        notify.send(new[0]["title"] if len(new) == 1 else f"{len(new)} alertes du coach",
                    "\n".join(f"{x['title']} : {x['advice']}" for x in new), top)
        sent |= {f"{today}|{x['title']}" for x in new}
    for x in service.sessions(db, 3):
        if x["label_id"] not in before and x["label_id"] in db.analyses() and f"seance|{x['label_id']}" not in sent:
            score = f" · {x['score']:.1f}/10".replace(".", ",") if x.get("score") is not None else ""
            notify.send(f"Séance analysée{score}", f"{x['headline'] or x['name']}\n{(x['findings'] or [''])[0]}", 3)
            sent.add(f"seance|{x['label_id']}")
    if date.today().weekday() == 0:
        r = report.ensure_last_week(db, s)
        key = f"bilan|{r['week']}"
        if key not in sent:
            notify.send("Bilan de la semaine", "\n".join(r["summary"][:3] + r["proposals"][:1]), 3)
            sent.add(key)
    db.set_meta("mobile_notified", json.dumps(sorted(sent)[-300:]))


@app.on_sync
def background_sync() -> list[str]:
    return run_sync()


def last_sync(db: DB) -> str | None:
    from datetime import datetime
    v = db.get_meta("last_sync")
    if not v:
        return None
    try:
        return datetime.fromisoformat(v).astimezone().strftime("%d/%m à %H:%M")
    except ValueError:
        return v[:16].replace("T", " à ")


def since(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


# The screens register themselves on `app` when imported.
from coach.mobile import plan_screens, recovery, sessions, settings_screens, today, training  # noqa: E402,F401
