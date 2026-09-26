import pytest

from coach import plan_edit as pe
from coach import workouts as wk

VMA = 16.0 / 3.6


@pytest.mark.parametrize("w", wk.CATALOG, ids=lambda w: w.key)
def test_every_catalog_workout_builds_a_valid_coros_course(w):
    c = wk.build(w, VMA, 262, 243, (300, 335))
    assert pe.validate(c) == [], (w.key, pe.validate(c))
    s = wk.summary(w, VMA, 262, 243, (300, 335))
    assert 3000 < s["total_m"] < 22000 and s["total_s"] > 1800


def test_paces_follow_vma_percentages():
    w = wk.by_key("400")  # 100-105 % of 16 km/h: 3:34-3:45/km
    assert wk.pace_range(w, VMA, 262, 243) == (214, 225)
    assert wk.pace_range(wk.by_key("seuil-10"), VMA, 262, 243) == (257, 267)
    assert wk.pace_range(wk.by_key("spe-2k"), VMA, 262, 243) == (240, 246)


def test_customised_workout_names_and_sets():
    w = wk.customise(wk.by_key("30-30"), reps=15, sets=2, set_rec_s=180)
    c = wk.build(w, VMA, 262, 243, (300, 335), walk=True)
    assert c["courseName"] == "VMA courte 2 séries de 15 × 30/30"
    assert sum(1 for s in c["sections"] if s.get("intervalGroup")) == 2
    rec = c["sections"][1]["sets"][1]
    assert rec["intensityValueStart"] >= 700  # walked recovery
    assert wk.name_of(wk.customise(wk.by_key("1000"), reps=5)) == "VMA longue 5 × 1 km"


def test_walked_recovery_covers_less_ground():
    w = wk.by_key("400")
    jog, walk = wk.summary(w, VMA, 262, 243, (300, 335)), wk.summary(w, VMA, 262, 243, (300, 335), walk=True)
    assert walk["total_s"] == jog["total_s"] and walk["total_m"] < jog["total_m"] - 500
    assert "marchée" in walk["rec"] and "trottée" in jog["rec"]
    rec = wk.build(w, VMA, 262, 243, (300, 335), walk=True)["sections"][1]["sets"][1]
    assert rec["pace"][0] >= 700 if "pace" in rec else True
