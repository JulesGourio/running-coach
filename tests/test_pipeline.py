from datetime import date, timedelta

import httpx
import respx

from coach import service
from coach.config import Settings
from coach.db import DB
from coach.sources.coros_web import CorosWeb
from coach.sync import analyze
from tests.synth import EASY_COURSE, VO2_COURSE, vo2_segments, write_fit


@respx.mock
def test_unofficial_api_login_list_download(tmp_path):
    base = "https://teameuapi.coros.com"
    login = respx.post(f"{base}/account/login").mock(
        return_value=httpx.Response(200, json={"result": "0000", "data": {"accessToken": "tok"}}))
    respx.get(f"{base}/activity/query").mock(return_value=httpx.Response(200, json={"result": "0000", "data": {
        "totalPage": 1, "dataList": [
            {"labelId": 111, "sportType": 100, "date": 20261006, "name": "Fractionné", "distance": 8310, "totalTime": 2581, "avgHr": 164},
            {"labelId": 222, "sportType": 200, "date": 20261007, "name": "Vélo", "distance": 30000, "totalTime": 3600}]}}))
    dl = respx.post(f"{base}/activity/detail/download").mock(
        return_value=httpx.Response(200, json={"result": "0000", "data": {"fileUrl": "https://files.example/a.fit"}}))
    respx.get("https://files.example/a.fit").mock(return_value=httpx.Response(200, content=b"FITDATA"))

    web = CorosWeb("me@example.com", "secret", "eu")
    acts = web.activities("20261001", "20261010")
    assert [a["label_id"] for a in acts] == ["111"]
    assert acts[0]["date"] == "2026-10-06" and acts[0]["distance_km"] == 8.31
    assert login.calls[0].request.content == b'{"account":"me@example.com","accountType":2,"pwd":"5ebe2294ecd0e0f08eab7690d2a6ee69"}'
    web.download_fit("111", 100, tmp_path / "a.fit")
    assert (tmp_path / "a.fit").read_bytes() == b"FITDATA"
    assert dl.calls[0].request.headers["accessToken"] == "tok"
    assert "fileType=4" in str(dl.calls[0].request.url)


def test_end_to_end_views(tmp_path):
    s = Settings(data_dir=tmp_path, hr_max=197, hr_rest=50, lthr=178, threshold_pace=262)
    s.fit_dir.mkdir(parents=True, exist_ok=True)
    db = DB(s.db_path)
    today = date.today()
    d1, d2 = (today - timedelta(days=2)).isoformat(), (today - timedelta(days=1)).isoformat()

    for label, day, segs, course in (
        ("a1", d1, vo2_segments(), VO2_COURSE),
        ("a2", d2, [{"pace": 355, "hr": 142, "sec": 2900}], EASY_COURSE),
    ):
        path = write_fit(tmp_path / f"{label}.fit", segs)
        db.upsert_activity({"label_id": label, "sport_type": 100, "date": day, "name": course["courseName"], "type": "Course"})
        db.set_fit_path(label, str(path))
        db.upsert_plan_day(day, 1, False, [{"status": "Completed", "name": course["courseName"], "json": course}])
    db.upsert_plan_day(today.isoformat(), 3, False, [{"status": "Not started", "name": "Seuil 20min", "json": {
        "courseName": "Seuil 20min", "sportType": 1, "sections": [
            {"sectionType": 2, "targetType": 2, "targetValue": 1200, "intensityType": 2, "intensityValueStart": 262, "intensityValueEnd": 270}]}}])
    for i in range(20):
        db.upsert_daily((today - timedelta(days=20 - i)).isoformat(), hrv=85 + i % 3, rhr=52, sleep_score=84)
    db.upsert_fitness(today.isoformat(), p10=2606, threshold=262, vo2max=60)

    assert analyze(s, db, log=lambda _: None) == 2
    rows = {r["label_id"]: r for r in service.sessions(db)}
    assert rows["a1"]["kind"] == "vma" and rows["a1"]["score"] == 10
    assert rows["a2"]["kind"] == "footing" and rows["a2"]["score"] >= 9

    ov = service.overview(db, s)
    assert ov["forme_du_jour"]["today"]["kind"] == "seuil"
    assert ov["predictions_s"]["COROS"] == 2606
    assert {p["status"] for p in service.plan_view(db, s)} == {"faite", "à venir"}

    db.save_verdict("a1", "Séance parfaite.", 9.5)
    detail = service.session_detail(db, "a1", with_records=True)
    assert detail["coach_verdict"]["text"] == "Séance parfaite." and len(detail["laps"]) == 14
