import numpy as np
import pandas as pd

from coach import plan_edit as pe
from coach import raceplan as rp


def test_flat_calm_plan_is_even_and_hits_target():
    prof = rp.km_profile(rp.flat_course(10000), 10000)
    r = rp.plan(prof, 2400, None, start_conservative=False)
    assert len(r["rows"]) == 10 and abs(r["total"] - 2400) < 0.5
    assert np.allclose(r["rows"]["pace"], 240, atol=0.5)


def test_hill_slows_the_climb_and_speeds_the_descent_at_same_total():
    d = np.linspace(0, 10000, 1001)
    alt = np.where(d < 3000, 100.0, np.where(d < 4000, 100 + (d - 3000) * 0.05, np.where(d < 5000, 150 - (d - 4000) * 0.05, 100.0)))
    prof = rp.km_profile(pd.DataFrame({"lat": np.nan, "lon": np.nan, "alt": alt, "dist": d}), 10000)
    r = rp.plan(prof, 2400, None, start_conservative=False)["rows"]
    assert r.loc[3, "pace"] > r.loc[0, "pace"] > r.loc[4, "pace"]  # km 4 up, km 5 down
    assert abs(r["time"].sum() - 2400) < 0.5


def test_heat_and_wind():
    assert rp.heat_penalty(10) == 0 and 0.02 < rp.heat_penalty(20, 70) < 0.04
    assert rp.wind_factor(4, 0, 0) > 1.07 and rp.wind_factor(4, 180, 0) < 0.97  # headwind vs tailwind


def test_gpx_and_watch_course():
    gpx = b"""<?xml version="1.0"?><gpx><trk><trkseg>
    <trkpt lat="43.600" lon="1.440"><ele>140</ele></trkpt><trkpt lat="43.609" lon="1.440"><ele>145</ele></trkpt>
    <trkpt lat="43.618" lon="1.440"><ele>150</ele></trkpt></trkseg></trk></gpx>"""
    c = rp.course_from_gpx(gpx)
    assert 1900 < c["dist"].iloc[-1] < 2100
    prof = rp.km_profile(c, 2000)
    assert prof["bearing"].between(-1, 1).all() or prof["bearing"].between(359, 360).all()
    course = rp.watch_course(rp.plan(prof, 480, None), "2 km")
    assert pe.validate(course) == [] and len(course["sections"]) == 2
