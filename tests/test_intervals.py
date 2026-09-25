from coach.metrics.intervals import quality_segments
from coach.metrics.session import best_durations, best_efforts
from tests.synth import build, vo2_segments

THRESHOLD_PACE = 270.0  # s/km


def test_quality_segments_isolates_reps_from_recovery():
    df, _ = build(vo2_segments())
    segs = quality_segments(df, THRESHOLD_PACE)
    assert len(segs) == 6
    for seg in segs:
        assert 350 <= seg["distance_m"] <= 420
        assert 225 <= seg["avg_pace"] <= 245
    # the warmup (357 s/km) and recoveries (400-450 s/km) must not be picked up
    assert sum(seg["distance_m"] for seg in segs) < 3000


def test_quality_segments_empty_for_easy_run():
    df, _ = build([{"pace": 330, "hr": 140, "sec": 1800}])
    assert quality_segments(df, THRESHOLD_PACE) == []


def test_best_efforts_does_not_invent_long_distances_from_broken_up_reps():
    # 6 x 1 km at 235 s/km with a slow 90 s jog recovery — like a real interval session, never a
    # continuous 5 km or 10 km effort. Regression test for the dilution bug: best_efforts() used to
    # search the whole continuous stream and would report a fake "best 10 km" at roughly the session's
    # average pace (recovery included) whenever the total distance happened to reach 10 km.
    reps = []
    for _ in range(6):
        reps += [{"pace": 235, "hr": 180, "m": 1050}, {"pace": 420, "hr": 150, "sec": 90}]
    df, _ = build([{"pace": 355, "hr": 140, "sec": 600}] + reps + [{"pace": 355, "hr": 138, "sec": 300}])
    segments = quality_segments(df, THRESHOLD_PACE)
    t, dist, speed = df["elapsed"].to_numpy(), df["distance"].to_numpy(), df["speed"].to_numpy()
    be = best_efforts(t, dist, segments)
    assert "10000" not in be
    assert "5000" not in be
    assert be["1000"] < 245  # a real isolated km, not diluted by the recovery jogs around it


def test_best_durations_restricted_to_a_single_segment():
    reps = []
    for _ in range(6):
        reps += [{"pace": 235, "hr": 180, "m": 1050}, {"pace": 420, "hr": 150, "sec": 90}]
    df, _ = build([{"pace": 355, "hr": 140, "sec": 600}] + reps)
    segments = quality_segments(df, THRESHOLD_PACE)
    speed = df["speed"].to_numpy()
    bd = best_durations(speed, segments)
    # each segment is ~235s: long enough for the 180s bucket, not for 360s+ (that would require
    # spanning into the recovery, i.e. diluting the average).
    assert "180" in bd
    assert "360" not in bd
