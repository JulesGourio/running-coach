from datetime import date

from coach.metrics import sleep as sl


def _rows():
    rows = []
    for i, (tot, bed, wake, nap) in enumerate([(420, "23:30", "07:10", 0), (528, "01:42", "09:08", 95),
                                               (369, "03:21", "08:55", 41), (480, "23:00", "07:00", 0)]):
        d = f"2026-09-{21 + i:02d}"
        rows.append({"date": d, "score": 80, "total_min": tot, "main_min": tot - nap, "main_period_min": tot - nap + 10,
                     "deep_pct": 17, "light_pct": 56, "rem_pct": 24, "awake_pct": 3, "awake_min": 10, "awake_count": 0,
                     "bedtime": f"2026-09-{20 + i:02d} {bed}" if bed >= "12" else f"{d} {bed}", "waketime": f"{d} {wake}",
                     "naps_min": nap, "naps": [{"start": "x", "end": "y"}] if nap else []})
    return rows


def test_frame_debt_and_bedtime_math():
    df = sl.frame(_rows())
    assert sl.hhmm(df["bed_h"].iloc[1], evening=True) == "01:42" and sl.hhmm(df["bed_h"].iloc[0], evening=True) == "23:30"
    assert sl.debt(df) == (480 - 420) + (480 - 369)
    rec = sl.recommended(df, hard_yesterday=True, load_ratio=1.4, today=date(2026, 9, 25))
    assert rec["minutes"] == 540 and len(rec["reasons"]) == 3
    assert 0 <= rec["bedtime"] < 24


def test_averages_by_period():
    df = sl.frame(_rows())
    w = sl.by_period(df, "weekday")
    assert w["nights"].sum() == 4 and set(w.columns) >= {"total", "naps", "nap_days"}
    assert sl.by_period(df, "year")["key"].tolist() == [2026]


def test_frame_rebuilds_durations_from_bed_and_wake():
    from coach.metrics import sleep as sl
    df = sl.frame([{"date": "2026-07-05", "score": 70.0, "total_min": None, "main_min": None, "main_period_min": None,
                    "deep_pct": 12.0, "light_pct": 67.0, "rem_pct": 19.0, "awake_pct": 2.0, "awake_min": 8.0, "awake_count": None,
                    "bedtime": "2026-07-05 00:20", "waketime": "2026-07-05 08:10", "naps_min": 30.0, "naps": []}])
    assert df.loc[0, "main_min"] == 470 - 8 and df.loc[0, "total_min"] == 462 + 30
