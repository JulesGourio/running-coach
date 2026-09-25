from datetime import date

import pytest

from coach import plan_builder as pb
from coach import plan_edit as pe


@pytest.mark.parametrize("goal,weeks,race", [("Semi-marathon", 12, date(2027, 4, 11)), ("10 km", 8, date(2027, 3, 7)),
                                              ("Marathon", 16, date(2027, 10, 31)), ("5 km", 6, date(2027, 2, 14))])
def test_generated_plans_are_valid_coros_plans(goal, weeks, race):
    p = pb.Params(name=f"Test {goal}", goal=goal, race_date=race, weeks=weeks, start_km=45, peak_km=65, goal_time=pb.GOALS[goal] / 1000 * 250)
    plan = pb.build(p)
    start = date.fromisoformat(plan["start"])
    assert start.weekday() == 0 and sum(ph["weeks"] for ph in plan["phases"]) == weeks
    assert plan["phases"][0]["start"] == plan["start"] and plan["phases"][-1]["end"] == race.isoformat() or race.weekday() != 6
    assert race.isoformat() in plan["days"] and plan["days"][race.isoformat()][0]["courseName"].startswith("COURSE")
    for day, cs in plan["days"].items():
        for c in cs:
            assert pe.validate(c) == [], (day, c["courseName"], pe.validate(c))
    args = pb.to_coros({"plan": plan, "params": {"name": p.name}})
    assert args["planInfo"]["totalWeeks"] == weeks and all(c["dayNo"] >= 0 for c in args["courseList"])
    vols = plan["volumes"]
    assert len(vols) == weeks and max(vols) <= 65 and vols[-1] < vols[-3]


def test_weekly_structure_follows_run_days_and_quality():
    p = pb.Params(name="x", goal="10 km", race_date=date(2027, 3, 7), weeks=8, run_days=[1, 3, 5, 6], quality=3)
    plan = pb.build(p)
    start = date.fromisoformat(plan["start"])
    week2 = [date.fromisoformat(d).weekday() for d in plan["days"] if 7 <= (date.fromisoformat(d) - start).days < 14]
    assert sorted(week2) == [1, 3, 5, 6]
