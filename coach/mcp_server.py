"""Local MCP server: lets Claude (Claude Code in VS Code) read the analyses and save written verdicts."""
from __future__ import annotations

from datetime import date, timedelta

from mcp.server.mcpserver import MCPServer

from coach import service
from coach.config import get_settings
from coach.db import DB
from coach.jsonable import jsonable

server = MCPServer(
    "running-coach",
    instructions=(
        "Analyses d'entraînement de Jules calculées localement à partir des fichiers FIT COROS. "
        "Temps et allures en secondes (allure en s/km). Pour juger une séance, lis analyse_seance puis rédige "
        "un verdict honnête et précis, et enregistre-le avec enregistrer_verdict. Pour modifier le plan, "
        "utilise le connecteur COROS de Claude, pas ce serveur."
    ),
)


def _ctx():
    s = get_settings()
    return s, DB(s.db_path)


@server.tool()
def resume() -> dict:
    """Vue d'ensemble : forme du jour, charge (CTL/ATL/TSB, ACWR, monotonie), prédictions 10 km, projection
    vers l'objectif, dernières séances notées et séances à venir."""
    s, db = _ctx()
    return jsonable(service.overview(db, s))


@server.tool()
def seances(jours: int = 14) -> dict:
    """Séances des N derniers jours avec type, note sur 10, constats chiffrés et verdict déjà rédigé s'il existe."""
    _, db = _ctx()
    return {"seances": jsonable(service.sessions(db, jours))}


@server.tool()
def analyse_seance(label_id: str) -> dict:
    """Toutes les métriques d'une séance (charge, zones, découplage, efficacité, meilleurs efforts, répétitions
    comparées au plan) et le verdict automatique."""
    _, db = _ctx()
    d = service.session_detail(db, label_id)
    return jsonable(d) if d else {"erreur": f"séance {label_id} inconnue"}


@server.tool()
def progression() -> dict:
    """Indicateurs de progrès : allure à FC de référence, efficacité, meilleurs efforts sur 90 jours, VMA estimée
    (fractionnés, seuil COROS, VO2max), prédictions 10 km (fractionnés, COROS, seuil) et leur médiane, projection
    au jour J et probabilités d'objectif."""
    s, db = _ctx()
    p = service.progress(db, s)
    p.pop("ef_rows", None)
    return jsonable(p)


@server.tool()
def charge(jours: int = 42) -> dict:
    """Modèle de charge jour par jour (charge, forme CTL, fatigue ATL, fraîcheur TSB, ACWR) et résumé par semaine
    (km, heures, charge, répartition facile / tempo / intense)."""
    _, db = _ctx()
    lm = service.load_model(db)
    since = (date.today() - timedelta(days=jours)).isoformat()
    model = lm["model"]
    return jsonable({"jours": model[model.index >= since], "semaines": lm["weekly"].tail(8),
                     "monotonie": lm["monotony"], "contrainte": lm["strain"]})


@server.tool()
def plan(jours_passes: int = 7, jours_a_venir: int = 14) -> dict:
    """Plan COROS synchronisé : statut de chaque jour (faite, manquée, à venir, repos) et séances réalisées."""
    s, db = _ctx()
    return {"jours": jsonable(service.plan_view(db, s, jours_passes, jours_a_venir))}


@server.tool()
def enregistrer_verdict(label_id: str, texte: str, note: float | None = None) -> str:
    """Enregistre le verdict rédigé pour une séance ; il s'affiche dans le dashboard."""
    _, db = _ctx()
    if not db.activity(label_id):
        return f"Séance {label_id} inconnue."
    db.save_verdict(label_id, texte.strip(), note)
    return "Verdict enregistré."


@server.tool()
async def synchroniser(jours: int = 14) -> str:
    """Récupère les dernières données COROS (connexion faite au préalable avec `uv run coach login`)
    et analyse les nouvelles séances."""
    from coach.sources.coros_mcp import describe
    from coach.sync import analyze, sync_mcp
    s, db = _ctx()
    logs: list[str] = []
    try:
        await sync_mcp(s, db, days=jours, interactive=False, log=logs.append)
    except Exception as e:  # noqa: BLE001 - report any sync failure back to Claude as text
        return f"Synchronisation impossible : {describe(e)}"
    analyze(s, db, log=logs.append)
    return "\n".join(logs)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
