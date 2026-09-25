from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd


def jsonable(o: Any) -> Any:
    """Convert pandas/numpy/date values into plain JSON-safe structures."""
    if isinstance(o, pd.DataFrame):
        df = o.reset_index() if not isinstance(o.index, pd.RangeIndex) else o
        return [jsonable(r) for r in df.to_dict("records")]
    if isinstance(o, pd.Series):
        return jsonable(o.to_dict())
    if isinstance(o, dict):
        return {str(k.date() if isinstance(k, pd.Timestamp) else k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, pd.Timestamp):
        return o.date().isoformat() if o == o.normalize() else o.isoformat()
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, float):
        return None if math.isnan(o) or math.isinf(o) else round(o, 3)
    return o
