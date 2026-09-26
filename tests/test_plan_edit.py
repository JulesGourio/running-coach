import asyncio
import json
from datetime import date, timedelta

import pytest

from coach import plan_edit as pe
from coach.config import get_settings
from coach.db import DB
from coach.metrics.zones import Athlete

A = Athlete(hr_max=200, hr_rest=56, lthr=190, threshold_pace=262)
P = pe.default_paces(A, vma=15.3 / 3.6, goal_a=2400, goal_b=2490)


@pytest.mark.parametrize("template,params", [
    ("footing", {"km": 10, "easy": P["easy"]}),
    ("footing_acc", {"km": 9, "easy": P["easy"], "strides": 6}),
    ("vma", {"reps": 10, "rep_m": 400, "pace": P["vma_short"], "rec": 200, "easy": P["easy"]}),
    ("allure", {"reps": 4, "rep_m": 2000, "pace": P["allure"], "rec": 120, "rec_unit": "s", "easy": P["easy"]}),
    ("seuil", {"blocks": 2, "block_min": 15, "pace": P["seuil"], "rec": 180, "easy": P["easy"]}),
    ("seuil", {"blocks": 1, "block_min": 25, "pace": P["seuil"], "easy": P["easy"]}),
    ("longue", {"km": 18, "easy": P["easy"]}),
    ("longue_allure", {"km": 18, "fast_km": 5, "pace": P["allure"], "easy": P["easy"]}),
    ("repos", {}),
])
def test_templates_build_valid_coros_courses(template, params):
    c = pe.build(template, params)
    assert pe.validate(c) == []


def test_default_paces_follow_zones_vma_and_goals():
    assert P["easy"] == (300, 335)
    assert P["seuil"] == (255, 265)
    assert P["allure"] == (240, 250)
    assert 216 <= P["vma_short"][0] <= P["vma_short"][1] <= 230


def test_validate_catches_out_of_bounds_and_bad_groups():
    bad = pe.build("vma", {"reps": 6, "rep_m": 1000, "pace": (100, 110), "rec": 400})
    bad["sections"][1]["repeats"] = 25
    errs = pe.validate(bad)
    assert any("allure" in e for e in errs) and any("répétitions" in e for e in errs)


def test_scale_changes_volume_not_warmup_or_strides():
    c = pe.build("footing_acc", {"km": 10, "easy": P["easy"], "strides": 6})
    light = pe.scale(c, 0.8)
    assert light["sections"][0]["targetValue"] == 8000
    assert light["sections"][1]["repeats"] == 6
    v = pe.scale(pe.build("vma", {"reps": 10, "rep_m": 400, "pace": P["vma_short"], "rec": 200}), 0.8)
    assert v["sections"][1]["repeats"] == 8 and v["sections"][0]["targetValue"] == 900
    assert "(allégée)" in v["courseName"] and pe.validate(v) == []
    assert pe.scale(pe.scale(v, 0.8), 1.2)["courseName"].count("(") == 1


def test_shift_paces_moves_quality_only():
    c = pe.build("longue_allure", {"km": 18, "fast_km": 5, "pace": (240, 246), "easy": (300, 330)})
    f = pe.shift_paces(c, -5, 262)
    assert f["sections"][0]["intensityValueStart"] == 300
    assert (f["sections"][1]["intensityValueStart"], f["sections"][1]["intensityValueEnd"]) == (235, 241)


def test_to_coros_is_ascii_and_carries_day_no():
    out = pe.to_coros(pe.build("footing_acc", {"km": 9, "easy": P["easy"]}), 12)
    assert out["dayNo"] == 12 and out["courseName"].isascii() and out["courseDescription"].isascii()


class FakeCoros:
    def __init__(self, plan_id, start):
        self.calls, self.plan_id, self.start = [], plan_id, start

    async def call(self, tool, args):
        self.calls.append((tool, args))
        return ("Training plan updated successfully.\nUpdated days (dayNo): 9\nSkipped executed days (dayNo): 10\n"
                f"Plan ID: {self.plan_id}\nDo not show Plan ID to the user.")

    async def plan(self):
        return {"id": self.plan_id, "start": self.start.isoformat(), "end": (self.start + timedelta(days=76)).isoformat()}

    async def plan_details(self, plan_id, a, b):
        return {"phases": [], "days": [{"day_no": 9, "date": (self.start + timedelta(days=9)).isoformat(), "rest": False,
                                        "courses": [{"status": "Not started", "name": "Footing 8 km",
                                                     "json": self.calls[0][1]["courseList"][0]}]}]}


def test_push_changes_sends_only_changed_days_and_records_history(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    s = get_settings()
    db = DB(s.db_path)
    start = date.today() - timedelta(days=5)
    db.set_meta("plan", json.dumps({"id": "123456789", "start": start.isoformat(), "end": (start + timedelta(days=76)).isoformat()}))
    d9 = {"date": (start + timedelta(days=9)).isoformat(), "day_no": 9, "courses": []}
    d10 = {"date": (start + timedelta(days=10)).isoformat(), "day_no": 10, "courses": []}
    changes = [pe.make_change(d9, [pe.build("footing", {"km": 8, "easy": P["easy"]})], "test"),
               pe.make_change(d10, [pe.REST], "test")]
    fake = FakeCoros("123456789", start)
    res = asyncio.run(pe.push_changes(s, db, changes, client=fake))
    tool, args = fake.calls[0]
    assert tool == "updateTrainingPlan" and args["planInfo"] == {"planId": "123456789"}
    assert [c["dayNo"] for c in args["courseList"]] == [9, 10]
    assert res["skipped"] == [10] and "123456789" not in res["message"]
    hist = db.plan_changes()
    assert {h["status"] for h in hist} == {"appliquée", "ignorée (déjà faite)"}
    assert db.plan_days(d9["date"], d9["date"])[0]["courses"][0]["name"] == "Footing 8 km"


def test_push_changes_refuses_invalid_or_past_days(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    s = get_settings()
    db = DB(s.db_path)
    db.set_meta("plan", json.dumps({"id": "1", "start": "2026-01-01", "end": "2026-12-31"}))
    past = {"date": (date.today() - timedelta(days=1)).isoformat(), "day_no": 3, "courses": []}
    with pytest.raises(pe.PlanError):
        asyncio.run(pe.push_changes(s, db, [pe.make_change(past, [pe.REST], "x")], client=FakeCoros("1", date.today())))


def test_queue_merges_edits_of_a_day_and_drops_a_revert():
    orig = pe.build("vma", {"reps": 10, "rep_m": 400, "pace": P["vma_short"], "rec": 200})
    day = {"date": "2030-01-08", "day_no": 8, "courses": [{"status": "Not started", "name": orig["courseName"], "json": orig}]}
    pending = {}
    pe.queue_change(pending, pe.make_change(day, [pe.scale(orig, 0.8)], "Forme moyenne"))
    lighter = pending["2030-01-08"]["after"]
    pe.queue_change(pending, pe.make_change(day, [pe.shift_paces(lighter[0], -3, 262)], "Allures"))
    ch = pending["2030-01-08"]
    assert ch["before"] == [orig] and ch["reason"] == "Forme moyenne + Allures"
    pe.queue_change(pending, pe.make_change(day, [orig], "Retour"))
    assert pending == {}


def test_swap_exchanges_two_days_rest_included():
    vma = pe.build("vma", {"reps": 6, "rep_m": 1000, "pace": P["vma_long"], "rec": 400})
    d1 = {"date": "2030-01-08", "day_no": 8, "courses": [{"status": "Not started", "name": "x", "json": vma}]}
    d2 = {"date": "2030-01-09", "day_no": 9, "courses": []}
    a, b = pe.swap(d1, d2)
    assert a["after"] == [pe.REST] and b["after"] == [vma]


def test_typed_in_ramp_test_vma_is_not_used_for_paces(tmp_path, monkeypatch):
    from coach import service
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    db = DB(tmp_path / "coach.db")
    today = date.today()
    service.add_vma_test(db, today.isoformat(), "manuel", 18 / 3.6, "VAMEVAL")
    assert service.latest_vma_test(db, today, functional=True) is None
    assert service.latest_vma_test(db, today + timedelta(days=400), kinds=("manuel",))["detail"] == "VAMEVAL"
    service.add_vma_test(db, today.isoformat(), "6min", 16.5 / 3.6, "test 6 min")
    assert service.latest_vma_test(db, today, functional=True)["kind"] == "6min"
