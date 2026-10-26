from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

from coach.config import ROOT, get_settings
from coach.db import DB
from coach.sources import coros
from coach.sources.coros_base import describe


def _db():
    s = get_settings()
    return s, DB(s.db_path)


async def _probe(interactive: bool) -> None:
    s = get_settings()
    async with coros.client(s, interactive=interactive) as c:
        names = await c.tool_names()
    print(f"Connexion COROS officielle OK : {len(names)} outils disponibles.")
    print(", ".join(sorted(names)))


def cmd_login(_: argparse.Namespace) -> None:
    try:
        asyncio.run(_probe(interactive=True))
    except Exception as e:  # noqa: BLE001 - surface any OAuth/transport failure to the user
        print(f"\nÉchec de la connexion officielle COROS : {describe(e)}")
        print("Solution de repli : renseigne COROS_EMAIL et COROS_PASSWORD dans .env puis lance "
              "`uv run coach sync --source web`, ou importe des fichiers avec `uv run coach import-fit <dossier>`.")
        sys.exit(1)


def cmd_probe(_: argparse.Namespace) -> None:
    try:
        asyncio.run(_probe(interactive=False))
    except Exception as e:  # noqa: BLE001
        print(describe(e))
        sys.exit(1)


def cmd_history(ns: argparse.Namespace) -> None:
    from coach.sync import sync_history
    s, db = _db()
    try:
        asyncio.run(sync_history(s, db, days=ns.days))
    except Exception as e:  # noqa: BLE001
        print(f"Historique COROS impossible : {describe(e)}")
        sys.exit(1)


def cmd_sync(ns: argparse.Namespace) -> None:
    from coach.sync import analyze, sync_mcp, sync_web
    s, db = _db()
    source = ns.source
    if source in ("auto", "mcp"):
        try:
            asyncio.run(sync_mcp(s, db, days=ns.days, max_fit=ns.max_fit, interactive=True))
        except Exception as e:  # noqa: BLE001
            if source == "mcp" or not (s.coros_email and s.coros_password):
                print(f"Synchronisation COROS officielle impossible : {describe(e)}")
                if source == "auto":
                    print("Renseigne COROS_EMAIL / COROS_PASSWORD dans .env pour essayer l'API non officielle.")
                sys.exit(1)
            print(f"Connexion officielle impossible ({describe(e)}) : essai avec l'API non officielle.")
            source = "web"
    if source == "web":
        sync_web(s, db, days=ns.days, max_fit=ns.max_fit)
    analyze(s, db)


def cmd_import(ns: argparse.Namespace) -> None:
    from coach.sources.fit_folder import import_folder
    from coach.sync import analyze
    s, db = _db()
    labels = import_folder(Path(ns.folder), db, s.fit_dir)
    print(f"{len(labels)} fichier{'s' if len(labels) > 1 else ''} importé{'s' if len(labels) > 1 else ''}.")
    analyze(s, db)


def cmd_analyze(ns: argparse.Namespace) -> None:
    from coach.sync import analyze
    s, db = _db()
    analyze(s, db, force=ns.force)


def cmd_status(_: argparse.Namespace) -> None:
    from coach import service
    s, db = _db()
    r = service.readiness_today(db, s)
    score = f"{r['score']}/100" if r["score"] is not None else "score indisponible"
    print(f"Forme du jour : {r['level']} ({score})")
    for x in r["reasons"]:
        print(f"  - {x}")
    if r.get("advice"):
        print(f"Conseil : {r['advice']}")
    for x in service.sessions(db, 10)[:5]:
        print(f"{x['date']}  {x['headline'] or x['name']}")


def cmd_export_mobile(ns: argparse.Namespace) -> None:
    from coach.transfer import export_bundle
    s, _ = _db()
    out = Path(ns.out).expanduser() if ns.out else Path.home() / "Downloads" / "coach-mobile.zip"
    r = export_bundle(s, out)
    print(f"{r['fichier']} : {r['seances']} séances, {r['fit']} fichiers FIT. Copie-le sur le téléphone puis "
          "Réglages → « Importer des données ».")


def cmd_import_mobile(ns: argparse.Namespace) -> None:
    from coach.transfer import import_bundle
    s, _ = _db()
    r = import_bundle(s, Path(ns.file).expanduser())
    print(f"{r['seances']} séances importées, {r['fit']} fichiers FIT.")


def cmd_login_light(_: argparse.Namespace) -> None:
    """The phone's COROS login (httpx only), tried on the PC: browser + a one-shot local callback server."""
    import threading
    import webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from coach.sources import coros_light
    s, _ = _db()
    got: dict[str, str] = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if "code=" in self.path or "error=" in self.path:
                got["url"] = f"http://127.0.0.1:{s.oauth_port}{self.path}"
                done.set()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<meta charset='utf-8'><p>Connexion COROS terminée.</p>".encode())

        def log_message(self, *a) -> None:
            pass

    httpd = HTTPServer(("127.0.0.1", s.oauth_port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = coros_light.login_start(s)
    print(f"Ouvre cette adresse pour autoriser l'accès à COROS :\n{url}\n")
    webbrowser.open(url)
    if not done.wait(300):
        httpd.shutdown()
        sys.exit("Délai dépassé.")
    httpd.shutdown()
    coros_light.login_finish(s, got["url"])
    print("Connexion COROS (client léger) OK. Pour l'utiliser sur le PC : COACH_COROS_CLIENT=light.")


def cmd_dashboard(_: argparse.Namespace) -> None:
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(ROOT / "app" / "main.py")], check=False)


def cmd_api(ns: argparse.Namespace) -> None:
    import uvicorn
    uvicorn.run("coach.api:app", host="127.0.0.1", port=ns.port, reload=False)


def main() -> None:
    # Windows opens stdout/stderr in the legacy console codepage by default, which mangles accented
    # characters in this French-language CLI; force UTF-8 so `coach status` etc. print correctly.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except ValueError:
                pass
    p = argparse.ArgumentParser(prog="coach", description="Coach de course à pied branché sur COROS")
    sub = p.add_subparsers(required=True)
    sub.add_parser("login", help="Connexion au serveur officiel COROS (ouvre le navigateur)").set_defaults(fn=cmd_login)
    sub.add_parser("probe", help="Vérifie la connexion COROS officielle").set_defaults(fn=cmd_probe)
    sp = sub.add_parser("sync", help="Récupère les données COROS et analyse les nouvelles séances")
    sp.add_argument("--days", type=int, default=30)
    sp.add_argument("--max-fit", type=int, default=15, help="Nombre maximum de fichiers FIT à télécharger")
    sp.add_argument("--source", choices=["auto", "mcp", "web"], default="auto")
    sp.set_defaults(fn=cmd_sync)
    hp = sub.add_parser("history", help="Récupère l'historique long (séances résumées et sommeil, sans fichiers FIT)")
    hp.add_argument("--days", type=int, default=365)
    hp.set_defaults(fn=cmd_history)
    ip = sub.add_parser("import-fit", help="Importe des fichiers .fit depuis un dossier")
    ip.add_argument("folder")
    ip.set_defaults(fn=cmd_import)
    ap = sub.add_parser("analyze", help="Recalcule les analyses")
    ap.add_argument("--force", action="store_true")
    ap.set_defaults(fn=cmd_analyze)
    sub.add_parser("status", help="Forme du jour et dernières séances").set_defaults(fn=cmd_status)
    ep = sub.add_parser("export-mobile", help="Archive pour le téléphone : base, fichiers FIT et profil")
    ep.add_argument("--out", help="Fichier .zip (par défaut ~/Downloads/coach-mobile.zip)")
    ep.set_defaults(fn=cmd_export_mobile)
    mp = sub.add_parser("import-mobile", help="Remplace les données du PC par une archive du téléphone")
    mp.add_argument("file")
    mp.set_defaults(fn=cmd_import_mobile)
    sub.add_parser("login-light", help="Connexion COROS du téléphone (client léger), testée sur le PC").set_defaults(fn=cmd_login_light)
    sub.add_parser("dashboard", help="Lance le dashboard Streamlit").set_defaults(fn=cmd_dashboard)
    api = sub.add_parser("api", help="Lance l'API HTTP locale")
    api.add_argument("--port", type=int, default=8000)
    api.set_defaults(fn=cmd_api)
    ns = p.parse_args()
    ns.fn(ns)


if __name__ == "__main__":
    main()
