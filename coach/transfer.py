"""Moving the data between the PC and the phone: one zip with the database, the FIT files and the profile.

`uv run coach export-mobile` writes the bundle on the PC; the phone imports it (Réglages → Importer) and can
write one back the same way. The COROS logins are never in it: each device signs in on its own.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from coach import config
from coach.config import Settings
from coach.db import DB

REQUIRED_TABLES = {"activities", "analyses", "daily", "meta"}


def _backup_db(src: Path, dest: Path) -> None:
    """A consistent copy even while the database is being written (SQLite backup API)."""
    with sqlite3.connect(src) as a, sqlite3.connect(dest) as b:
        a.backup(b)


def check_database(path: Path) -> int:
    """Integrity check and required tables; returns the number of activities."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as e:
        raise ValueError(f"base illisible : {e}") from e
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("base abîmée (contrôle d'intégrité)")
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = REQUIRED_TABLES - tables
        if missing:
            raise ValueError(f"ce n'est pas une base du coach (tables manquantes : {', '.join(sorted(missing))})")
        return con.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    except sqlite3.DatabaseError as e:
        raise ValueError(f"ce n'est pas une base SQLite : {e}") from e
    finally:
        con.close()


def effective_profile(s: Settings) -> dict[str, str]:
    """The profile as this device sees it (environment or profil.json), to carry it to the other device."""
    return {k: v for k in config.PROFILE_KEYS if (v := config.env(k))}


def export_bundle(s: Settings, dest: Path) -> dict:
    db = DB(s.db_path)
    acts = [a for a in db.activities(sports="all") if a.get("fit_path")]
    n_fit = 0
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "coach.sqlite"
        _backup_db(s.db_path, copy)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(copy, "coach.sqlite")
            for a in acts:
                p = Path(a["fit_path"])
                if p.exists():
                    z.write(p, f"fit/{p.name}")
                    n_fit += 1
            z.writestr("profil.json", json.dumps(effective_profile(s), ensure_ascii=False, indent=1))
            z.writestr("bundle.json", json.dumps({"made": datetime.now().isoformat(timespec="seconds"),
                                                  "activities": len(db.activities(sports="all")), "fit": n_fit}))
    return {"fichier": str(dest), "seances": len(db.activities(sports="all")), "fit": n_fit}


def _safe_member(name: str) -> str | None:
    """Only `coach.sqlite`, `profil.json` and `fit/<name>.fit`: nothing can be written outside the data folder."""
    if name in ("coach.sqlite", "profil.json", "bundle.json"):
        return name
    parts = name.split("/")
    if len(parts) == 2 and parts[0] == "fit" and parts[1].lower().endswith(".fit") and "\\" not in parts[1] \
            and parts[1] not in ("", ".", ".."):
        return name
    return None


def import_bundle(s: Settings, path: Path) -> dict:
    """Replace this device's data with a bundle (.zip) or a bare database (.sqlite). The previous database is
    kept next to it as `coach-avant-import-<date>.sqlite`. FIT paths are rewritten to this device's folder."""
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.fit_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=s.data_dir) as tmp:
        tmp = Path(tmp)
        profile: dict | None = None
        fit_names: list[str] = []
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                if "coach.sqlite" not in names:
                    raise ValueError("archive sans coach.sqlite : exporte-la avec `uv run coach export-mobile`")
                for n in names:
                    if _safe_member(n) is None:
                        continue
                    target = tmp / n
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(n) as src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out)
                    if n.startswith("fit/"):
                        fit_names.append(target.name)
            new_db = tmp / "coach.sqlite"
            if (tmp / "profil.json").exists():
                profile = json.loads((tmp / "profil.json").read_text(encoding="utf-8"))
        else:
            new_db = tmp / "coach.sqlite"
            shutil.copyfile(path, new_db)
        n_acts = check_database(new_db)

        for name in fit_names:
            shutil.move(str(tmp / "fit" / name), str(s.fit_dir / name))
        con = sqlite3.connect(new_db)
        try:
            rows = con.execute("SELECT label_id, fit_path FROM activities WHERE fit_path IS NOT NULL").fetchall()
            kept = 0
            for label, fp in rows:
                local = s.fit_dir / Path(fp.replace("\\", "/")).name
                if local.exists():
                    con.execute("UPDATE activities SET fit_path=? WHERE label_id=?", (str(local), label))
                    kept += 1
                else:
                    con.execute("UPDATE activities SET fit_path=NULL WHERE label_id=?", (label,))
            con.commit()
        finally:
            con.close()

        if s.db_path.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            _backup_db(s.db_path, s.data_dir / f"coach-avant-import-{stamp}.sqlite")
        os.replace(new_db, s.db_path)
        for side in ("-wal", "-shm"):
            Path(str(s.db_path) + side).unlink(missing_ok=True)

    applied = {}
    if profile:
        current = config.profile()
        applied = {k: v for k, v in profile.items() if k in config.PROFILE_KEYS and k not in current}
        if applied:
            config.save_profile(applied)
    return {"seances": n_acts, "fit": kept, "fit_absents": len(rows) - kept, "profil": sorted(applied)}
