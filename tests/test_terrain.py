import numpy as np
import pandas as pd

from coach.metrics.session import effort_factor, grade_bins, km_splits


def test_effort_factor_shape():
    f = effort_factor(np.array([-0.3, -0.1, 0.0, 0.1, 0.2]))
    assert f[2] == 1 and 1.35 < f[3] < 1.45 and 0.85 < f[1] < 0.9 and f[4] > f[3] and f[0] > f[1]


def test_km_splits_on_a_climb():
    n = 1500  # 1500 s at 2 m/s, climbing 10 % then flat
    dist = np.arange(n) * 2.0
    alt = np.where(dist < 1500, dist * 0.1, 150.0)
    df = pd.DataFrame({"distance": dist, "speed": 2.0, "altitude": alt, "hr": 150.0, "elapsed": np.arange(n)})
    grade = np.where(dist < 1500, 0.1, 0.0)
    sp = km_splits(df, grade, np.ones(n, bool))
    assert sp[0]["km"] == 1 and abs(sp[0]["up"] - 100) < 5 and sp[0]["effort_pace"] < sp[0]["pace"]
    assert {b["name"] for b in grade_bins(np.full(n, 2.0), grade, np.ones(n, bool))} == {"8 à 15 %", "plat"}
