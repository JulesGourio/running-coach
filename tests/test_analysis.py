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


def test_vma_from_intervals_and_10k_prediction():
    # 12 x 400 m in 88 s (3:40/km) and 6 x 1 km at 4:02: a runner around VMA 15.3 km/h, 10 km ~43-44 min.
    s400 = [{"duration_s": 88.0, "distance_m": 400.0, "avg_pace": 220.0, "avg_hr": 185.0}] * 12
    s1k = [{"duration_s": 242.0, "distance_m": 1000.0, "avg_pace": 242.0, "avg_hr": 186.0}] * 6
    easy = [{"duration_s": 95.0, "distance_m": 400.0, "avg_pace": 250.0, "avg_hr": 160.0}] * 8
    sessions = [(date(2026, 9, 16), s400), (date(2026, 9, 24), s1k), (date(2026, 9, 20), easy)]
    v = prog.estimate_vma(sessions, threshold_pace=262, hr_max=200, end=date(2026, 9, 25))
    assert 15.0 < v["vma"] * 3.6 < 15.7
    assert "2026-09-20" not in v["sessions"]  # HR never near max: not a capacity signal
    assert 42 * 60 < prog.predict_from_vma(v["vma"], 10000) < 44.5 * 60
    assert prog.session_vma(s400[:2], 262) is None  # too few reps


def test_projection_ignores_noisy_trend_and_never_regresses():
    noisy = [(date(2026, 8, 1) + (date(2026, 8, 8) - date(2026, 8, 1)) * i, t)
             for i, t in enumerate([2660, 2660, 2760, 2760, 2720, 2613])]
    p = prog.projection_from_current(2606, noisy, date(2026, 12, 13), date(2026, 9, 25))
    assert p["basis"] == "typique" and p["low"] < p["projected"] < p["high"] <= 2606


def test_readiness_flags_low_hrv():
    base = [{"date": f"2026-09-{d:02d}", "hrv": 85 + (d % 3), "rhr": 52, "sleep_score": 85} for d in range(1, 25)]
    good = readiness(base + [{"date": "2026-09-25", "hrv": 86, "rhr": 52, "sleep_score": 88}], tsb=0)
    bad = readiness(base + [{"date": "2026-09-25", "hrv": 58, "rhr": 60, "sleep_score": 55}], tsb=-25)
    assert good["level"] == "vert" and bad["level"] == "rouge" and len(bad["reasons"]) >= 3


def test_vma_from_heart_rate_speed_line():
    from coach.metrics.session import compute_session_metrics
    from coach.metrics.zones import Athlete
    from tests.synth import build
    segs = [{"pace": 360, "hr": 138, "sec": 900}]
    for _ in range(5):
        segs += [{"pace": 240, "hr": 182, "m": 1000}, {"pace": 420, "hr": 150, "sec": 120}]
    df, _ = build(segs)
    a = Athlete(hr_max=200, hr_rest=55, lthr=188, threshold_pace=262)
    fit = compute_session_metrics(df, a)["hr_speed"]
    assert fit and fit["r2"] > 0.95 and fit["slope"] > 0
    v = prog.vma_from_hr_fits([(date(2026, 9, 24), fit)], 200, date(2026, 9, 25))
    # reps at 15 km/h with HR in the low 180s: extrapolated to 97 % of 200 bpm, clearly faster than the reps
    assert 15.5 < v["vma"] * 3.6 < 18 and v["vma_at_95"] < v["vma"] < v["vma_at_max"]
    assert prog.vma_from_hr_fits([(date(2026, 9, 24), {**fit, "r2": 0.5})], 200, date(2026, 9, 25)) is None


def test_vma_from_field_tests():
    assert prog.vma_from_test("6min", distance_m=1700) * 3.6 == pytest.approx(17.0)
    assert 17.4 < prog.vma_from_test("effort", distance_m=3000, time_s=630) * 3.6 < 17.8
    assert prog.vma_from_test("effort", distance_m=1500, time_s=320) * 3.6 == pytest.approx(16.875)
    assert prog.vma_from_test("manuel", kmh=17) == pytest.approx(17 / 3.6)


def test_records_ignore_gps_jumps_non_running_and_downhill():
    import numpy as np
    from coach.metrics.session import records
    t = np.arange(0, 3000, 1.0)
    speed = np.full(len(t), 3.3)          # 5:03/km running
    speed[1000:1300] = 7.0                # 300 s at 25 km/h …
    cad = np.full(len(t), 172.0)
    cad[1000:1300] = 0.0                  # … with no cadence: a car or a bike
    dist = np.cumsum(speed)
    r = records(t, dist, cad)
    assert r["1000"] > 290                # the fast stretch isn't a record
    alt = 500 - dist * 0.05               # 5 % downhill all the way
    assert "1000" not in records(t, np.cumsum(np.full(len(t), 3.3)), np.full(len(t), 172.0), alt)
    dist_jump = np.cumsum(np.full(len(t), 3.3))
    dist_jump[2000:] += 500               # a 500 m GPS jump
    r = records(t, dist_jump, np.full(len(t), 172.0))
    assert r["1000"] >= 1000 / 3.3 - 1
