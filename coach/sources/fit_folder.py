"""Import FIT files dropped in a folder (COROS app export or any other source)."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from coach.db import DB
from coach.fit import read_fit


def import_folder(folder: Path, db: DB, fit_dir: Path) -> list[str]:
    imported = []
    for p in sorted(Path(folder).glob("**/*.fit")) + sorted(Path(folder).glob("**/*.FIT")):
        digest = hashlib.sha1(p.read_bytes()).hexdigest()[:16]
        label = f"file-{digest}"
        if db.activity(label):
            continue
        act = read_fit(p)
        if act.records.empty:
            continue
        start = act.start
        local = start.astimezone() if start else None
        dist = act.session.get("distance_m") or float(act.records["distance"].iloc[-1])
        dur = act.session.get("timer_s") or float(act.records["elapsed"].iloc[-1])
        dest = fit_dir / f"{label}.fit"
        shutil.copyfile(p, dest)
        db.upsert_activity({
            "label_id": label, "sport_type": 100, "date": local.strftime("%Y-%m-%d") if local else None,
            "start_ts": int(start.timestamp()) if start else None, "name": p.stem, "type": "Course",
            "distance_km": dist / 1000 if dist else None, "duration_s": dur,
            "avg_pace": dur / (dist / 1000) if dist and dur else None, "avg_hr": act.session.get("avg_hr"),
            "source": "fichier",
        })
        db.set_fit_path(label, str(dest))
        imported.append(label)
    return imported
