"""Local HTTP API over the same views as the dashboard."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from coach import service
from coach.config import get_settings
from coach.db import DB
from coach.jsonable import jsonable

app = FastAPI(title="Running Coach", version="0.1.0")


def _ctx():
    s = get_settings()
    return s, DB(s.db_path)


@app.get("/overview")
def overview():
    s, db = _ctx()
    return jsonable(service.overview(db, s))


@app.get("/sessions")
def sessions(days: int = 30):
    _, db = _ctx()
    return jsonable(service.sessions(db, days))


@app.get("/sessions/{label_id}")
def session(label_id: str):
    _, db = _ctx()
    d = service.session_detail(db, label_id)
    if not d:
        raise HTTPException(404, "Séance inconnue")
    return jsonable(d)


class Verdict(BaseModel):
    text: str
    score: float | None = None


@app.put("/sessions/{label_id}/verdict")
def put_verdict(label_id: str, v: Verdict):
    _, db = _ctx()
    if not db.activity(label_id):
        raise HTTPException(404, "Séance inconnue")
    db.save_verdict(label_id, v.text, v.score)
    return {"ok": True}


@app.get("/load")
def load():
    _, db = _ctx()
    lm = service.load_model(db)
    return jsonable({"days": lm["model"].tail(90), "weeks": lm["weekly"].tail(16), "monotony": lm["monotony"]})


@app.get("/progress")
def progress():
    s, db = _ctx()
    return jsonable(service.progress(db, s))


@app.get("/plan")
def plan(back: int = 14, ahead: int = 14):
    s, db = _ctx()
    return jsonable(service.plan_view(db, s, back, ahead))
