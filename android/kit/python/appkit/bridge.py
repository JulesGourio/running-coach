"""What the Kotlin shell calls (through Chaquopy). Always strings in, a JSON string out:
``{"ok": true, "data": …}`` or ``{"ok": false, "erreur": "…"}``.

- ``start(module, data_dir, secrets, notifier)`` once: imports the app's module (which defines ``app = App(...)``);
- ``manifest()``, ``screen(name, args_json)``, ``action(name, args_json)``;
- ``sync()`` from the background worker and the « Synchroniser » button, one at a time.
"""
from __future__ import annotations

import importlib
import inspect
import json
import logging
import math
import threading
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from appkit.app import App, Result

log = logging.getLogger("appkit")
_app: App | None = None
_sync_lock = threading.Lock()


class ForeignStore:
    """The Kotlin secret store (Android Keystore); Java strings and nulls come back as str and None."""

    def __init__(self, store: Any) -> None:
        self.store = store

    def get(self, name: str) -> str | None:
        v = self.store.get(name)
        return None if v is None else str(v)

    def set(self, name: str, value: str) -> None:  # noqa: A003
        self.store.set(name, value)

    def delete(self, name: str) -> None:
        self.store.delete(name)


def safe(x: Any) -> Any:
    """JSON-safe: NaN/inf -> None, dates -> ISO, numpy and pandas scalars -> Python."""
    if isinstance(x, dict):
        return {str(k): safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [safe(v) for v in x]
    if isinstance(x, float):
        return None if math.isnan(x) or math.isinf(x) else x
    if isinstance(x, (date, datetime)):
        return x.isoformat()
    if hasattr(x, "item") and not isinstance(x, (str, bytes)):
        try:
            return safe(x.item())
        except (ValueError, TypeError):
            return str(x)
    return x


def _reply(fn: Callable[[], Any]) -> str:
    try:
        data = fn()
        return json.dumps({"ok": True, "data": safe(data)}, ensure_ascii=False, default=str)
    except Exception as e:  # noqa: BLE001 - the app shows the message, the log keeps the trace
        log.error("%s", traceback.format_exc())
        return json.dumps({"ok": False, "erreur": str(e) or e.__class__.__name__}, ensure_ascii=False)


def _coerce(fn: Callable, args: dict) -> dict:
    """Keep the arguments `fn` accepts and convert form strings to the type of each parameter's default
    (or of its annotation): "12" -> 12, "true" -> True, "" -> default."""
    sig = inspect.signature(fn)
    takes_any = any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values())
    out = {}
    for k, v in args.items():
        p = sig.parameters.get(k)
        if p is None:
            if takes_any:
                out[k] = v
            continue
        out[k] = _convert(v, p)
    return out


def _convert(v: Any, p: inspect.Parameter) -> Any:
    ann = p.annotation if isinstance(p.annotation, str) else getattr(p.annotation, "__name__", "")
    default = None if p.default is p.empty else p.default
    want = type(default).__name__ if default is not None else ""
    for t in ("bool", "int", "float"):
        if not want and t in str(ann):
            want = t
    if isinstance(v, str):
        s = v.strip()
        if s == "" and want in ("int", "float", "bool"):
            return default
        if want == "bool":
            return s.lower() in ("1", "true", "oui", "yes", "on")
        if want == "int":
            try:
                return int(float(s.replace(",", ".")))
            except ValueError as e:
                raise ValueError(f"{p.name} : nombre attendu") from e
        if want == "float":
            try:
                return float(s.replace(",", "."))
            except ValueError as e:
                raise ValueError(f"{p.name} : nombre attendu") from e
    if want == "int" and isinstance(v, float) and v.is_integer():
        return int(v)
    if want == "float" and isinstance(v, int) and not isinstance(v, bool):
        return float(v)
    return v


def _loads(args_json: str | None) -> dict:
    args = json.loads(args_json or "{}")
    if not isinstance(args, dict):
        raise ValueError("les arguments doivent être un objet JSON")
    return args


def _need_app() -> App:
    if _app is None:
        raise RuntimeError("moteur non démarré")
    return _app


def setup_logging(data_dir: Path) -> None:
    logs = data_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if not any(isinstance(h, logging.FileHandler) for h in root.handlers):
        h = logging.FileHandler(logs / f"app-{date.today().isoformat()}.log", encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(h)
        root.setLevel(logging.INFO)


def load(module: str) -> App:
    """Import the app's module and return its `app` (also used by the tests)."""
    global _app
    m = importlib.import_module(module)
    app = getattr(m, "app", None)
    if not isinstance(app, App):
        raise RuntimeError(f"{module} ne définit pas `app = App(...)`")
    _app = app
    return app


def start(module: str, data_dir: str, secrets: Any = None, notifier: Any = None) -> str:
    def run() -> dict:
        d = Path(data_dir)
        d.mkdir(parents=True, exist_ok=True)
        setup_logging(d)
        app = load(module)
        if app.start_fn:
            store = ForeignStore(secrets) if secrets is not None else None
            show = (lambda t, m, p: bool(notifier.show(t, m, int(p)))) if notifier is not None else None
            app.start_fn(d, store, show)
        return app.manifest()
    return _reply(run)


def manifest() -> str:
    return _reply(lambda: _need_app().manifest())


def screen(name: str, args_json: str = "{}") -> str:
    def run() -> dict:
        app = _need_app()
        fn = app.screens.get(name)
        if fn is None:
            raise ValueError(f"écran inconnu : {name}")
        out = fn(**_coerce(fn, _loads(args_json)))
        if isinstance(out, list):
            out = {"title": app.title, "blocks": out}
        return out
    return _reply(run)


def action(name: str, args_json: str = "{}") -> str:
    def run() -> dict:
        app = _need_app()
        fn = app.actions.get(name)
        if fn is None:
            raise ValueError(f"action inconnue : {name}")
        out = fn(**_coerce(fn, _loads(args_json)))
        if out is None:
            out = Result()
        elif isinstance(out, str):
            out = Result(message=out)
        elif isinstance(out, dict):
            out = Result(**out)
        return out.to_json()
    return _reply(run)


def sync() -> str:
    def run() -> dict:
        app = _need_app()
        if app.sync_fn is None:
            return {"lignes": []}
        if not _sync_lock.acquire(blocking=False):
            return {"deja_en_cours": True, "lignes": ["Synchronisation déjà en cours."]}
        try:
            return {"lignes": list(app.sync_fn() or [])}
        finally:
            _sync_lock.release()
    return _reply(run)


def syncing() -> bool:
    return _sync_lock.locked()
