from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    label_id TEXT PRIMARY KEY,
    sport_type INTEGER,
    date TEXT NOT NULL,
    start_ts INTEGER,
    name TEXT,
    type TEXT,
    distance_km REAL,
    duration_s REAL,
    avg_pace REAL,
    avg_hr REAL,
    source TEXT,
    fit_path TEXT,
    synced_at TEXT
);
CREATE INDEX IF NOT EXISTS activities_date ON activities(date);
CREATE TABLE IF NOT EXISTS analyses (
    label_id TEXT PRIMARY KEY,
    computed_at TEXT,
    metrics_json TEXT,
    verdict_json TEXT
);
CREATE TABLE IF NOT EXISTS verdicts (
    label_id TEXT PRIMARY KEY,
    written_at TEXT,
    score REAL,
    text TEXT
);
CREATE TABLE IF NOT EXISTS daily (
    date TEXT PRIMARY KEY,
    hrv REAL, hrv_lo REAL, hrv_hi REAL, hrv_base REAL, hrv_eval TEXT,
    rhr REAL,
    sleep_score REAL, sleep_total TEXT, sleep_deep REAL, sleep_rem REAL,
    load_st REAL, load_lt REAL, load_ratio REAL, load_comment TEXT
);
CREATE TABLE IF NOT EXISTS fitness (
    date TEXT PRIMARY KEY,
    vo2max REAL, level REAL, threshold REAL,
    p5 REAL, p10 REAL, half REAL, marathon REAL,
    recovery_pct REAL
);
CREATE TABLE IF NOT EXISTS plan_days (
    date TEXT PRIMARY KEY,
    day_no INTEGER,
    rest INTEGER,
    courses_json TEXT,
    fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

DAILY_COLS = ["hrv", "hrv_lo", "hrv_hi", "hrv_base", "hrv_eval", "rhr", "sleep_score", "sleep_total",
              "sleep_deep", "sleep_rem", "load_st", "load_lt", "load_ratio", "load_comment"]
FITNESS_COLS = ["vo2max", "level", "threshold", "p5", "p10", "half", "marathon", "recovery_pct"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DB:
    def __init__(self, path: Path | str):
        self.path = str(path)
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # ---- activities ----
    def upsert_activity(self, a: dict[str, Any]) -> None:
        cols = ["label_id", "sport_type", "date", "start_ts", "name", "type", "distance_km", "duration_s",
                "avg_pace", "avg_hr", "source"]
        vals = [a.get(k) for k in cols]
        with self.conn() as c:
            c.execute(
                f"INSERT INTO activities ({','.join(cols)}, synced_at) VALUES ({','.join('?' * len(cols))}, ?) "
                f"ON CONFLICT(label_id) DO UPDATE SET {','.join(f'{k}=excluded.{k}' for k in cols[1:])}, "
                "synced_at=excluded.synced_at",
                [*vals, now_iso()],
            )

    def set_fit_path(self, label_id: str, path: str) -> None:
        with self.conn() as c:
            c.execute("UPDATE activities SET fit_path=? WHERE label_id=?", (path, label_id))

    def activities(self, since: str | None = None, until: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM activities WHERE 1=1", []
        if since:
            q += " AND date>=?"
            args.append(since)
        if until:
            q += " AND date<=?"
            args.append(until)
        q += " ORDER BY date DESC, start_ts DESC"
        with self.conn() as c:
            return [dict(r) for r in c.execute(q, args)]

    def activity(self, label_id: str) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM activities WHERE label_id=?", (label_id,)).fetchone()
            return dict(r) if r else None

    # ---- analyses ----
    def save_analysis(self, label_id: str, metrics: dict, verdict: dict) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO analyses VALUES (?,?,?,?) ON CONFLICT(label_id) DO UPDATE SET "
                "computed_at=excluded.computed_at, metrics_json=excluded.metrics_json, verdict_json=excluded.verdict_json",
                (label_id, now_iso(), json.dumps(metrics), json.dumps(verdict)),
            )

    def analysis(self, label_id: str) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM analyses WHERE label_id=?", (label_id,)).fetchone()
        if not r:
            return None
        return {"computed_at": r["computed_at"], "metrics": json.loads(r["metrics_json"]),
                "verdict": json.loads(r["verdict_json"])}

    def analyses(self) -> dict[str, dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM analyses").fetchall()
        return {r["label_id"]: {"metrics": json.loads(r["metrics_json"]), "verdict": json.loads(r["verdict_json"])}
                for r in rows}

    # ---- coach-written verdicts ----
    def save_verdict(self, label_id: str, text: str, score: float | None) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO verdicts VALUES (?,?,?,?) ON CONFLICT(label_id) DO UPDATE SET "
                "written_at=excluded.written_at, score=excluded.score, text=excluded.text",
                (label_id, now_iso(), score, text),
            )

    def verdict(self, label_id: str) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM verdicts WHERE label_id=?", (label_id,)).fetchone()
            return dict(r) if r else None

    # ---- daily / fitness ----
    def upsert_daily(self, date: str, **fields: Any) -> None:
        fields = {k: v for k, v in fields.items() if k in DAILY_COLS and v is not None}
        if not fields:
            return
        with self.conn() as c:
            c.execute("INSERT INTO daily(date) VALUES (?) ON CONFLICT(date) DO NOTHING", (date,))
            c.execute(f"UPDATE daily SET {','.join(f'{k}=?' for k in fields)} WHERE date=?", [*fields.values(), date])

    def daily(self, since: str | None = None) -> list[dict]:
        with self.conn() as c:
            q = "SELECT * FROM daily" + (" WHERE date>=?" if since else "") + " ORDER BY date"
            return [dict(r) for r in c.execute(q, [since] if since else [])]

    def upsert_fitness(self, date: str, **fields: Any) -> None:
        fields = {k: v for k, v in fields.items() if k in FITNESS_COLS and v is not None}
        if not fields:
            return
        with self.conn() as c:
            c.execute("INSERT INTO fitness(date) VALUES (?) ON CONFLICT(date) DO NOTHING", (date,))
            c.execute(f"UPDATE fitness SET {','.join(f'{k}=?' for k in fields)} WHERE date=?", [*fields.values(), date])

    def fitness(self) -> list[dict]:
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM fitness ORDER BY date")]

    # ---- plan ----
    def upsert_plan_day(self, date: str, day_no: int, rest: bool, courses: list[dict]) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO plan_days VALUES (?,?,?,?,?) ON CONFLICT(date) DO UPDATE SET day_no=excluded.day_no, "
                "rest=excluded.rest, courses_json=excluded.courses_json, fetched_at=excluded.fetched_at",
                (date, day_no, int(rest), json.dumps(courses), now_iso()),
            )

    def plan_days(self, since: str | None = None, until: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM plan_days WHERE 1=1", []
        if since:
            q += " AND date>=?"
            args.append(since)
        if until:
            q += " AND date<=?"
            args.append(until)
        with self.conn() as c:
            rows = c.execute(q + " ORDER BY date", args).fetchall()
        return [{"date": r["date"], "day_no": r["day_no"], "rest": bool(r["rest"]),
                 "courses": json.loads(r["courses_json"] or "[]")} for r in rows]

    # ---- meta ----
    def get_meta(self, key: str) -> str | None:
        with self.conn() as c:
            r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return r["value"] if r else None

    def set_meta(self, key: str, value: str) -> None:
        with self.conn() as c:
            c.execute("INSERT INTO meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
