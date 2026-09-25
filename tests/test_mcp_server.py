import asyncio
import json
from datetime import date, timedelta

from mcp import Client

from coach.config import get_settings
from coach.db import DB
from coach.sync import analyze
from tests.synth import VO2_COURSE, vo2_segments, write_fit


def test_tools_over_mcp(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ATHLETE_HR_MAX", "197")
    monkeypatch.setenv("ATHLETE_THRESHOLD_PACE", "4:22")
    s = get_settings()
    db = DB(s.db_path)
    day = (date.today() - timedelta(days=1)).isoformat()
    db.upsert_activity({"label_id": "x1", "sport_type": 100, "date": day, "name": "VO2max 6x400m"})
    db.set_fit_path("x1", str(write_fit(tmp_path / "x1.fit", vo2_segments())))
    db.upsert_plan_day(day, 8, False, [{"status": "Completed", "name": "VO2max 6x400m", "json": VO2_COURSE}])
    analyze(s, db, log=lambda _: None)

    from coach.mcp_server import server

    async def run():
        async with Client(server) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            assert {"resume", "seances", "analyse_seance", "enregistrer_verdict", "synchroniser"} <= names
            r = await c.call_tool("seances", {"jours": 7})
            rows = (r.structured_content or json.loads(r.content[0].text))["seances"]
            assert rows[0]["kind"] == "vma" and rows[0]["score"] == 10
            r = await c.call_tool("enregistrer_verdict", {"label_id": "x1", "texte": "Très propre.", "note": 9})
            assert "enregistré" in r.content[0].text
            r = await c.call_tool("resume", {})
            assert not r.is_error

    asyncio.run(run())
    assert DB(s.db_path).verdict("x1")["text"] == "Très propre."
