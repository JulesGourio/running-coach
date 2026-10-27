"""PC ↔ phone archive: what an import accepts, and that it never writes outside the data folder."""
import sqlite3
import zipfile

import pytest

from coach import transfer
from coach.config import Settings
from coach.db import DB


@pytest.fixture
def s(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path / "data"))
    st = Settings()
    st.data_dir.mkdir(parents=True)
    st.fit_dir.mkdir()
    return st


def _source_db(path, fit_path=None):
    db = DB(path)
    db.upsert_activity({"label_id": "a1", "sport_type": 100, "date": "2026-10-01", "name": "Footing"})
    if fit_path:
        db.set_fit_path("a1", fit_path)
    return db


def test_bundle_keeps_fit_files_and_rewrites_their_paths(s, tmp_path):
    src = tmp_path / "pc"
    src.mkdir()
    (src / "a1.fit").write_bytes(b"fit")
    _source_db(src / "coach.sqlite", r"C:\Users\jules\running-coach\data\fit\a1.fit")
    bundle = tmp_path / "b.zip"
    with zipfile.ZipFile(bundle, "w") as z:
        z.write(src / "coach.sqlite", "coach.sqlite")
        z.write(src / "a1.fit", "fit/a1.fit")
        z.writestr("profil.json", '{"GOAL_LABEL": "Semi", "INCONNU": "x"}')
        z.writestr("../evil.txt", "x")
        z.writestr("fit/../../evil.fit", "x")
    r = transfer.import_bundle(s, bundle)
    assert r == {"seances": 1, "fit": 1, "fit_absents": 0, "profil": ["GOAL_LABEL"], "profil_ignore": []}
    assert DB(s.db_path).activity("a1")["fit_path"] == str(s.fit_dir / "a1.fit")
    assert not (tmp_path / "evil.txt").exists() and not (s.data_dir / "evil.txt").exists()
    assert not list(tmp_path.rglob("evil*"))


def test_missing_fit_is_cleared_so_the_sync_downloads_it_again(s, tmp_path):
    _source_db(tmp_path / "coach.sqlite", "/home/jules/data/fit/a1.fit")
    r = transfer.import_bundle(s, tmp_path / "coach.sqlite")
    assert r["fit_absents"] == 1
    assert DB(s.db_path).activity("a1")["fit_path"] is None


def test_previous_database_is_kept(s, tmp_path):
    _source_db(s.db_path)
    _source_db(tmp_path / "new.sqlite")
    transfer.import_bundle(s, tmp_path / "new.sqlite")
    assert list(s.data_dir.glob("coach-avant-import-*.sqlite"))


@pytest.mark.parametrize("content", [b"not a database", None])
def test_rejects_what_is_not_a_coach_database(s, tmp_path, content):
    p = tmp_path / "x.sqlite"
    if content is None:
        sqlite3.connect(p).execute("CREATE TABLE autre (x)").connection.commit()
    else:
        p.write_bytes(content)
    with pytest.raises(ValueError):
        transfer.import_bundle(s, p)
    assert not s.db_path.exists()


def test_export_contains_the_profile_from_the_environment(s, tmp_path, monkeypatch):
    monkeypatch.setenv("GOAL_LABEL", "Marathon")
    _source_db(s.db_path)
    out = tmp_path / "out.zip"
    transfer.export_bundle(s, out)
    with zipfile.ZipFile(out) as z:
        assert '"Marathon"' in z.read("profil.json").decode()
        assert "coach.sqlite" in z.namelist()


def test_bad_profile_values_are_skipped_not_fatal(s, tmp_path):
    _source_db(tmp_path / "coach.sqlite")
    bundle = tmp_path / "b.zip"
    with zipfile.ZipFile(bundle, "w") as z:
        z.write(tmp_path / "coach.sqlite", "coach.sqlite")
        z.writestr("profil.json", '{"ATHLETE_SEX": "m", "GOAL_LABEL": "Semi", "GOAL_DISTANCE_M": "0"}')
    r = transfer.import_bundle(s, bundle)
    assert r["profil"] == ["GOAL_LABEL"] and r["profil_ignore"] == ["ATHLETE_SEX", "GOAL_DISTANCE_M"]
