"""The phone app's screens and actions, through the same bridge the Android shell calls (appkit.bridge)."""
from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "android" / "kit" / "python"))

from appkit import bridge  # noqa: E402

BLOCK_KEYS = {
    "title": {"text"}, "text": {"text", "style"}, "bullets": {"items"}, "alert": {"level", "title"}, "divider": set(),
    "metrics": {"items"}, "big": {"label", "value"}, "rows": {"items"}, "card": {"blocks"}, "table": {"columns", "rows"},
    "chart": {"kind", "labels", "series", "y"}, "route": {"points"}, "choice": {"name", "options", "value"},
    "pager": {"label"}, "button": {"label", "action", "args"}, "buttons": {"items"}, "form": {"fields", "action", "submit"},
    "file": {"label", "action"}, "export": {"label", "action", "filename"}, "sync": set(),
}
TONES = {"good", "bad", "warn", "info", "muted"}


class Store:
    def __init__(self):
        self.values = {}

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value):
        self.values[name] = value

    def delete(self, name):
        self.values.pop(name, None)


class Notifier:
    def __init__(self):
        self.shown = []

    def show(self, title, message, priority):
        self.shown.append((title, message, priority))
        return True


def _demo(cache_dir: Path) -> None:
    """Demo data (8 weeks of simulated training, a plan, nights) written once a day into `cache_dir`."""
    import os
    os.environ["COACH_DATA_DIR"] = str(cache_dir)
    sys.path.insert(0, str(ROOT))
    from scripts import demo_data
    demo_data.main()
    from coach.config import get_settings
    from coach.db import DB
    db = DB(get_settings().db_path)
    rnd = random.Random(3)
    for i in range(40):
        day = date.today() - timedelta(days=39 - i)
        night = day - timedelta(days=1)
        db.upsert_sleep({"date": day.isoformat(), "score": 80 + rnd.random() * 10, "total_min": 430 + rnd.random() * 60,
                         "main_min": 420 + rnd.random() * 50, "main_period_min": 450, "deep_pct": 18, "light_pct": 52,
                         "rem_pct": 22, "awake_pct": 4, "awake_min": 15, "awake_count": 2,
                         "bedtime": f"{night.isoformat()} 23:{rnd.randint(0, 50):02d}", "waketime": f"{day.isoformat()} 07:05",
                         "naps_min": 20 if i % 7 == 0 else 0,
                         "naps": [{"start": f"{day.isoformat()} 14:00", "end": f"{day.isoformat()} 14:20"}] if i % 7 == 0 else []})


@pytest.fixture(scope="module")
def phone(tmp_path_factory, request):
    """A phone's data folder: a copy of the day's demo data, so every test run starts from the same state."""
    import hashlib
    import os
    import shutil
    import sqlite3
    old = {k: os.environ.get(k) for k in ("COACH_DATA_DIR", "COACH_COROS_CLIENT")}
    key = hashlib.sha1((ROOT / "scripts" / "demo_data.py").read_bytes() + (ROOT / "tests" / "synth.py").read_bytes()).hexdigest()[:8]
    name = f"demo-{date.today().isoformat()}-{key}"
    store = getattr(request.config, "cache", None)
    cache = Path(store.mkdir(name)) if store is not None else tmp_path_factory.mktemp(name)
    if not (cache / "ready").exists():
        shutil.rmtree(cache, ignore_errors=True)
        cache.mkdir(parents=True)
        _demo(cache)
        (cache / "ready").write_text("ok")
    d = tmp_path_factory.mktemp("phone")
    shutil.copytree(cache, d, dirs_exist_ok=True)
    con = sqlite3.connect(d / "coach.sqlite")
    con.execute("UPDATE activities SET fit_path = replace(fit_path, ?, ?)", (str(cache), str(d)))
    con.commit()
    con.close()
    notifier, store = Notifier(), Store()
    manifest = _ok(bridge.start("coach.mobile", str(d), store, notifier))
    yield {"dir": d, "manifest": manifest, "notifier": notifier, "store": store}
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    from coach import notify, vault
    vault.use(vault.NoBackend())
    notify.set_local(None)


def _ok(raw: str):
    r = json.loads(raw)
    assert r["ok"], r.get("erreur")
    return r["data"]


def _screen(name, **args):
    return _ok(bridge.screen(name, json.dumps(args)))


def _action(name, **args):
    return _ok(bridge.action(name, json.dumps(args)))


def _check_tone(t):
    assert t is None or t in TONES or (isinstance(t, str) and t.startswith("#") and len(t) == 7), t


def _walk(blocks, links, actions):
    for b in blocks:
        t = b["t"]
        assert t in BLOCK_KEYS, t
        assert BLOCK_KEYS[t] <= set(b), (t, b)
        _check_tone(b.get("tone"))
        if b.get("open"):
            links.append(b["open"])
        if t in ("button", "form", "file", "export"):
            actions.add(b["action"])
        if t == "card":
            _walk(b["blocks"], links, actions)
        if t == "buttons":
            _walk(b["items"], links, actions)
        if t in ("rows", "metrics"):
            for it in b["items"]:
                _check_tone(it.get("tone"))
                if it.get("badge"):
                    _check_tone(it["badge"].get("tone"))
                if it.get("open"):
                    links.append(it["open"])
                if it.get("action"):
                    actions.add(it["action"]["name"])
        if t == "chart":
            for sr in b["series"]:
                assert len(sr["values"]) == len(b["labels"]), (b["title"], sr["name"])
            assert b["kind"] in ("line", "bar", "stack", "hbar") and b["y"] in ("num", "int", "pace", "time", "pct", "hours", "km")
        if t == "table":
            assert all(len(r) == len(b["columns"]) for r in b["rows"]), b["columns"]
        if t == "choice":
            assert any(o["value"] == b["value"] for o in b["options"]), b
        if t == "form":
            for f in b["fields"]:
                assert f["kind"] in ("text", "number", "decimal", "secret", "multiline", "date", "time", "select", "toggle", "multi")


def test_manifest_lists_tabs_that_exist(phone):
    m = phone["manifest"]
    assert m["title"] == "Carnet de course" and 2 <= len(m["tabs"]) <= 5
    assert all(t["screen"] in m["screens"] for t in m["tabs"])


def test_every_reachable_screen_renders(phone):
    """Open the tabs, then every screen linked from them (two levels), with the choices of each screen."""
    m = phone["manifest"]
    todo = [{"screen": t["screen"], "args": {}} for t in m["tabs"]]
    seen, actions, n = set(), set(), 0
    while todo and n < 120:
        link = todo.pop(0)
        key = (link["screen"], json.dumps(link["args"], sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        assert link["screen"] in m["screens"], link
        page = _screen(link["screen"], **link["args"])
        json.dumps(page)
        assert page["title"] and isinstance(page["blocks"], list)
        links: list = []
        _walk(page["blocks"], links, actions)
        n += 1
        for b in page["blocks"]:
            if b["t"] == "choice" and not link["args"]:
                for o in b["options"][:4]:
                    todo.append({"screen": link["screen"], "args": {b["name"]: o["value"]}})
            if b["t"] == "pager" and b.get("prev") and not link["args"]:
                todo.append({"screen": link["screen"], "args": b["prev"]})
        todo += [lk for lk in links if lk["screen"] not in ("seance",) or len([s for s in seen if s[0] == "seance"]) < 4]
    screens = {s for s, _ in seen}
    assert {"aujourdhui", "seances", "seance", "plan", "plan_jour", "progression", "plus", "charge", "recuperation",
            "historique", "seances_types", "jour_j", "bilan", "reglages", "aide"} <= screens
    assert actions <= set(m["actions"]), actions - set(m["actions"])


def test_unknown_screen_and_bad_args_are_errors(phone):
    assert not json.loads(bridge.screen("nope", "{}"))["ok"]
    r = json.loads(bridge.screen("charge", '{"jours": "beaucoup"}'))
    assert not r["ok"] and "nombre" in r["erreur"]


def test_recovery_views(phone):
    for vue in ("nuit", "stats", "vfc"):
        page = _screen("recuperation", vue=vue)
        assert len(page["blocks"]) > 3


def test_session_detail_has_charts_and_verdict_form(phone):
    from coach.config import get_settings
    from coach.db import DB
    db = DB(get_settings().db_path)
    label = db.activities()[-1]["label_id"]
    page = _screen("seance", label_id=label)
    kinds = [b["t"] for b in page["blocks"]]
    assert "chart" in kinds and "metrics" in kinds
    assert _action("verdict_enregistrer", label_id=label, texte="Bonne séance.", note="8,5")["reload"]
    assert db.verdict(label)["score"] == 8.5
    assert not json.loads(bridge.action("verdict_enregistrer", json.dumps({"label_id": label, "texte": "x", "note": "12"})))["ok"]


def test_vma_test_round_trip(phone):
    r = _action("vma_test_ajouter", kind="6min", jour=date.today().isoformat(), distance="1650")
    assert "VMA" in r["message"]
    page = _screen("progression")
    assert "test" in json.dumps(page, ensure_ascii=False)
    _action("vma_test_supprimer", jour=date.today().isoformat())


def _future_day():
    from coach import plan_edit as pe
    from coach.config import get_settings
    from coach.db import DB
    db = DB(get_settings().db_path)
    return next(d for d in db.plan_days((date.today() + timedelta(days=1)).isoformat()) if pe.day_courses(d) and not pe.day_is_done(d))


def test_plan_day_edits_are_queued_then_cancelled(phone):
    day = _future_day()
    r = _action("plan_jour_ajuster", jour=day["date"], volume="80", allures="0")
    assert r["back"] and "attente" in r["message"]
    page = _screen("plan")
    assert "Modifications en attente" in json.dumps(page, ensure_ascii=False)
    r = _action("plan_jour_remplacer", jour=day["date"], modele="footing", km="7,5", allure_de="5:40", allure_a="6:00")
    assert r["back"]
    bad = json.loads(bridge.action("plan_jour_remplacer", json.dumps({"jour": day["date"], "modele": "footing", "allure_de": "0:30",
                                                                      "allure_a": "6:00"})))
    assert not bad["ok"]
    past = (date.today() - timedelta(days=2)).isoformat()
    assert not json.loads(bridge.action("plan_jour_ajuster", json.dumps({"jour": past, "volume": 80})))["ok"]
    _action("plan_annuler_tout")
    assert "Modifications en attente" not in json.dumps(_screen("plan"), ensure_ascii=False)


def test_plan_push_goes_through_the_coros_client(phone, monkeypatch):
    from coach.sources import coros
    from tests.test_plan_edit import FakeCoros

    day = _future_day()
    _action("plan_jour_ajuster", jour=day["date"], volume="90")
    plan = json.loads(__import__("coach.db", fromlist=["DB"]).DB(
        __import__("coach.config", fromlist=["get_settings"]).get_settings().db_path).get_meta("plan"))
    fake = FakeCoros(plan["id"], date.fromisoformat(plan["start"]))

    class Ctx:
        async def __aenter__(self):
            return fake

        async def __aexit__(self, *a):
            return False
    monkeypatch.setattr(coros, "client", lambda s, interactive=False: Ctx())
    assert not json.loads(bridge.action("plan_envoyer", json.dumps({"empreinte": "autre"})))["ok"]
    r = _action("plan_envoyer", empreinte=_send_button()["args"]["empreinte"])
    assert "mis à jour" in r["message"]
    assert fake.calls and fake.calls[0][0] == "updateTrainingPlan"


def _send_button():
    def find(blocks):
        for b in blocks:
            if b.get("action") == "plan_envoyer":
                return b
            found = find(b.get("blocks", []) + b.get("items", []))
            if found:
                return found
        return None
    return find(_screen("plan")["blocks"])


def test_send_leaves_out_days_that_changed_or_passed(phone, monkeypatch):
    from coach.config import get_settings
    from coach.db import DB
    from coach.mobile import plan_screens as ps
    db = DB(get_settings().db_path)
    day = _future_day()
    _action("plan_jour_ajuster", jour=day["date"], volume="90")
    pending = ps.pending_get(db)
    past = (date.today() - timedelta(days=1)).isoformat()
    pending[past] = {**pending[day["date"]], "date": past}
    pending[day["date"]]["before"] = [{"courseName": "autre chose"}]  # changed elsewhere since it was queued
    ps.pending_save(db, pending)
    r = _action("plan_envoyer", empreinte=ps.fingerprint(pending))
    assert "Non envoyés" in r["message"] and "modifié ailleurs" in r["message"] and "passé" in r["message"]
    assert ps.pending_get(db) == {}


def test_a_new_plan_drops_the_queue(phone):
    from coach.config import get_settings
    from coach.db import DB
    from coach.mobile import plan_screens as ps
    db = DB(get_settings().db_path)
    _action("plan_jour_ajuster", jour=_future_day()["date"], volume="90")
    assert ps.pending_get(db)
    plan = json.loads(db.get_meta("plan"))
    db.set_meta("plan", json.dumps({**plan, "id": "autre-plan"}))
    try:
        assert ps.pending_get(db) == {}
    finally:
        db.set_meta("plan", json.dumps(plan))
        _action("plan_annuler_tout")


def test_notified_keys_are_pruned_by_kind():
    from coach.mobile import prune_notified
    today = date(2026, 10, 27)
    sent = {f"seance|x{i:04d}" for i in range(400)} | {"2026-10-27|Alerte", "2026-10-01|Vieille", "bilan|2026-10-19"}
    kept = prune_notified(sent, today)
    assert "2026-10-27|Alerte" in kept and "2026-10-01|Vieille" not in kept and "bilan|2026-10-19" in kept
    assert sum(k.startswith("seance|") for k in kept) == 300


def test_draft_generator_and_library(phone):
    r = _action("plan_brouillon_creer", objectif="10 km", course=(date.today() + timedelta(weeks=20)).isoformat(),
                temps="40:00", seuil=262, semaines="10", jours=[1, 2, 3, 5, 6], longue="6", qualite="3",
                depart_km="50", pic_km="70", vma="17,5")
    did = r["open"]["args"]["vue"]
    page = _screen("plan", vue=did)
    assert any(b["t"] == "chart" for b in page["blocks"])
    assert _action("plan_brouillon_supprimer", id=did)["open"]["screen"] == "plan"
    day = _future_day()
    assert "attente" in _action("seance_type_ajouter", cle="400", jour=day["date"])["message"]
    _action("plan_annuler_tout")


def test_race_day_screen_with_manual_weather(phone):
    page = _screen("jour_j", meteo="manuel", temperature="18", vent="20", cible="B")
    assert "Temps prévu" in json.dumps(page, ensure_ascii=False)


def test_profile_and_secrets(phone):
    _action("profil_enregistrer", GOAL_LABEL="Semi", GOAL_TIME_A="1:25:00", ATHLETE_HR_MAX="")
    from coach.config import Settings
    assert Settings().goal_label == "Semi" and Settings().goal_a == 5100
    assert not json.loads(bridge.action("profil_enregistrer", json.dumps({"GOAL_TIME_A": "vite"})))["ok"]
    _action("profil_enregistrer", GOAL_LABEL="10 km", GOAL_TIME_A="40:00")
    _action("secrets_enregistrer", coros_email="me@x.fr", coros_password="pw")
    assert phone["store"].values["coros_password"] == "pw"
    assert Settings().coros_email == "me@x.fr"


def test_coros_login_returns_a_web_sign_in(phone, monkeypatch):
    from coach.sources import coros_light
    monkeypatch.setattr(coros_light, "login_start", lambda s: "https://auth.coros.com/authorize?x=1")
    r = _action("coros_connexion")
    assert r["webauth"]["finish"] == "coros_connexion_fin" and r["webauth"]["prefix"].startswith("http://127.0.0.1")
    monkeypatch.setattr(coros_light, "login_finish", lambda s, url: None)
    assert _action("coros_connexion_fin", url="http://127.0.0.1:8765/callback?code=1")["sync"]


def test_export_then_import_round_trip(phone, tmp_path):
    dest = tmp_path / "coach-mobile.zip"
    r = _action("donnees_exporter", dest=str(dest))
    assert dest.exists() and "Archive" in r["message"]
    r = _action("donnees_importer", path=str(dest))
    assert "séances importées" in r["message"]
    assert _screen("aujourdhui")["blocks"]


def test_sync_reports_needs_login_and_notifies(phone, monkeypatch):
    phone["notifier"].shown.clear()
    out = _ok(bridge.sync())
    assert any("COROS" in line for line in out["lignes"])
    assert any("reconnecter" in t for t, _, p in phone["notifier"].shown if p >= 4)


def test_notification_test(phone):
    assert _action("notification_test")["message"] == "Notification envoyée."


def test_bridge_coerces_form_values():
    import inspect

    def f(a: int = 1, b: float = 0.0, c: bool = False, d: str = "", e: int | None = None):
        return a, b, c, d, e
    out = bridge._coerce(f, {"a": "12", "b": "3,5", "c": "true", "d": 4, "e": "7", "zz": 1})
    assert out == {"a": 12, "b": 3.5, "c": True, "d": 4, "e": 7}
    assert bridge._coerce(f, {"a": ""}) == {"a": 1}
    assert inspect.signature(f)
