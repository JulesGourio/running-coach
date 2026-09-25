from datetime import date, timedelta

from coach import alerts as al
from coach import plan_edit as pe
from coach.config import get_settings
from coach.db import DB


def test_alerts_short_sleep_before_hard_session_load_and_rhr(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    s = get_settings()
    db = DB(s.db_path)
    today = date(2026, 10, 5)
    for i in range(30):
        d = (today - timedelta(days=29 - i)).isoformat()
        db.upsert_daily(d, rhr=52 if i < 27 else 60, load_ratio=1.1 if i < 27 else 1.6)
    for i, mins in enumerate([470, 480, 350, 360, 340]):
        db.upsert_sleep({"date": (today - timedelta(days=4 - i)).isoformat(), "score": 60, "total_min": mins, "naps": []})
    vma = pe.build("vma", {"reps": 10, "rep_m": 400, "pace": (214, 222), "rec": 200})
    db.upsert_plan_day((today + timedelta(days=1)).isoformat(), 8, False,
                       [{"status": "Not started", "name": vma["courseName"], "json": vma}])
    titles = [a["title"] for a in al.alerts(db, s, today)]
    assert titles[0] == "Charge excessive"
    assert any(t.startswith("Sommeil court avant la séance") for t in titles)
    assert "FC de repos en hausse" in titles
