from datetime import date

import pandas as pd
import pytest

from coach.fit import read_fit
from coach.metrics import load as loadm
from coach.metrics import progress as prog
from coach.metrics.intervals import evaluate_steps
from coach.metrics.readiness import readiness
from coach.metrics.session import compute_session_metrics
from coach.metrics.zones import Athlete
from coach.verdict import judge
from tests.synth import EASY_COURSE, VO2_COURSE, build, vo2_segments, write_fit

A = Athlete(hr_max=197, hr_rest=50, lthr=178, threshold_pace=262)


def test_fit_roundtrip(tmp_path):
    path = write_fit(tmp_path / "vo2.fit", vo2_segments())
    act = read_fit(path)
    assert len(act.laps) == 14
    assert act.session["distance_m"] == pytest.approx(act.records["distance"].iloc[-1], rel=0.01)
    assert act.records["hr"].notna().mean() > 0.99
    assert act.records["cadence"].median() == pytest.approx(172, abs=2)


def test_intervals_on_target_from_laps():
    df, laps = build(vo2_segments())
    r = evaluate_steps(VO2_COURSE, df, laps, A.threshold_pace)
    assert r["n_planned"] == 6 and r["n_on_target"] == 6 and r["method"] == "tour"


def test_intervals_detected_without_laps():
    df, _ = build(vo2_segments())
    r = evaluate_steps(VO2_COURSE, df, [], A.threshold_pace)
    assert r["n_found"] == 6 and r["n_on_target"] == 6 and r["method"] == "flux"


def test_fading_reps_are_judged():
    df, laps = build(vo2_segments([233, 235, 236, 238, 250, 252]))
    m = compute_session_metrics(df, A)
    v = judge(m, A, VO2_COURSE, df, laps)
    assert v["type"] == "vma"
    assert v["reps"]["n_on_target"] == 4
    assert "reps_trop_lentes" in v["flags"] and "baisse_de_regime" in v["flags"]
    assert 5 < v["score"] < 7.5


def test_easy_run_discipline():
    easy, _ = build([{"pace": 355, "hr": 145, "sec": 2900}])
    m = compute_session_metrics(easy, A)
    v = judge(m, A, EASY_COURSE, easy, [])
    assert v["type"] == "footing" and v["score"] >= 9 and not v["flags"]

    hard, _ = build([{"pace": 320, "hr": 172, "sec": 2600}])
    m = compute_session_metrics(hard, A)
    v = judge(m, A, EASY_COURSE, hard, [])
    assert "trop_intense" in v["flags"] and "trop_rapide" in v["flags"] and v["score"] <= 6


def test_decoupling_on_drifting_long_run():
    df, _ = build([{"pace": 330, "hr": 140, "sec": 5400}], drift_bpm_per_h=18)
    m = compute_session_metrics(df, A)
    assert m["decoupling"]["decoupling_pct"] > 5
    v = judge(m, A, None, df, [])
    assert v["type"] == "longue" and "decouplage" in v["flags"]


def test_load_metrics():
    df, _ = build([{"pace": 262, "hr": 178, "sec": 3600}])
    m = compute_session_metrics(df, A)
    assert m["rtss"] == pytest.approx(100, rel=0.03)
    assert m["hrtss"] == pytest.approx(100, rel=0.1)
    assert m["best_efforts"]["5000"] == pytest.approx(5 * 262, rel=0.01)


def test_fitness_model_converges():
    s = loadm.daily_load([(d.strftime("%Y-%m-%d"), 60.0) for d in pd.date_range("2026-01-01", periods=300)])
    fm = loadm.fitness_model(s)
    assert fm["ctl"].iloc[-1] == pytest.approx(60, rel=0.01) and abs(fm["tsb"].iloc[-1]) < 1
    assert fm["acwr"].iloc[-1] == pytest.approx(1.0)


def test_predictions():
    assert prog.vdot(10000, 2400) == pytest.approx(51.9, abs=0.3)
    assert prog.time_for_vdot(prog.vdot(5000, 1256), 5000) == pytest.approx(1256, abs=1)
    assert prog.riegel(1200, 5000, 10000) == pytest.approx(2501, abs=2)
    cs = prog.critical_speed({180: 5.0, 360: 4.6, 720: 4.35, 1200: 4.25})
    assert 4.0 < cs["cs"] < 4.3 and cs["d_prime"] > 0
    series = [(date(2026, 9, 1), 2700.0), (date(2026, 9, 15), 2600.0), (date(2026, 9, 29), 2500.0)]
    proj = prog.projection(series, date(2026, 12, 13))
    assert proj["capped"] and proj["projected"] >= 2500 * (1 - 0.01 * 11) - 1
    assert 0 <= prog.prob_under(2400, proj) < prog.prob_under(2490, proj) <= 1


def test_readiness_flags_low_hrv():
    base = [{"date": f"2026-09-{d:02d}", "hrv": 85 + (d % 3), "rhr": 52, "sleep_score": 85} for d in range(1, 25)]
    good = readiness(base + [{"date": "2026-09-25", "hrv": 86, "rhr": 52, "sleep_score": 88}], tsb=0)
    bad = readiness(base + [{"date": "2026-09-25", "hrv": 58, "rhr": 60, "sleep_score": 55}], tsb=-25)
    assert good["level"] == "vert" and bad["level"] == "rouge" and len(bad["reasons"]) >= 3
