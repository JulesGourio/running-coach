"""Claude's tools on the training data, as plain functions returning JSON-safe values.

One list (`TOOLS`) serves the MCP server (`mcp_server`, PC) and the phone app (`mobile`); nothing here imports
`mcp`, Streamlit or the Android bridge. A new tool is declared once, with `@tool`.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

from coach import service
from coach.config import get_settings
from coach.db import DB
from coach.jsonable import jsonable

INSTRUCTIONS = (
    "Analyses d'entraînement de Jules calculées localement à partir des fichiers FIT COROS. "
    "Temps et allures en secondes (allure en s/km). Pour juger une séance, lis analyse_seance puis rédige "
    "un verdict honnête et précis, et enregistre-le avec enregistrer_verdict. Pour modifier le plan, "
    "utilise le connecteur COROS de Claude, pas ce serveur."
)

TOOLS: list[Callable[..., Any]] = []


def tool(fn: Callable[..., Any]) -> Callable[..., Any]:
    TOOLS.append(fn)
    return fn


def _ctx():
    s = get_settings()
    return s, DB(s.db_path)


@tool
def resume() -> dict:
    """Vue d'ensemble : forme du jour, charge (CTL/ATL/TSB, ACWR, monotonie), prédictions 10 km, projection
    vers l'objectif, dernières séances notées et séances à venir."""
    s, db = _ctx()
    return jsonable(service.overview(db, s))


@tool
def seances(jours: int = 14) -> dict:
    """Séances des N derniers jours avec type, note sur 10, constats chiffrés et verdict déjà rédigé s'il existe."""
    _, db = _ctx()
    return {"seances": jsonable(service.sessions(db, jours))}


@tool
def analyse_seance(label_id: str) -> dict:
    """Toutes les métriques d'une séance (charge, zones, découplage, efficacité, meilleurs efforts, répétitions
    comparées au plan) et le verdict automatique."""
    _, db = _ctx()
    d = service.session_detail(db, label_id)
    return jsonable(d) if d else {"erreur": f"séance {label_id} inconnue"}


@tool
def progression() -> dict:
    """Indicateurs de progrès : allure à FC de référence, efficacité, meilleurs efforts sur 90 jours, VMA estimée
    (fractionnés, seuil COROS, VO2max), prédictions 10 km (fractionnés, COROS, seuil) et leur médiane, projection
    au jour J et probabilités d'objectif."""
    s, db = _ctx()
    p = service.progress(db, s)
    p.pop("ef_rows", None)
    return jsonable(p)


@tool
def charge(jours: int = 42) -> dict:
    """Modèle de charge jour par jour (charge, forme CTL, fatigue ATL, fraîcheur TSB, ACWR) et résumé par semaine
    (km, heures, charge, répartition facile / tempo / intense)."""
    _, db = _ctx()
    lm = service.load_model(db)
    since = (date.today() - timedelta(days=jours)).isoformat()
    model = lm["model"]
    return jsonable({"jours": model[model.index >= since], "semaines": lm["weekly"].tail(8),
                     "monotonie": lm["monotony"], "contrainte": lm["strain"]})


@tool
def plan(jours_passes: int = 7, jours_a_venir: int = 14) -> dict:
    """Plan COROS synchronisé : statut de chaque jour (faite, manquée, à venir, repos) et séances réalisées."""
    s, db = _ctx()
    return {"jours": jsonable(service.plan_view(db, s, jours_passes, jours_a_venir))}


@tool
def bilan_semaine(lundi: str | None = None) -> dict:
    """Bilan d'une semaine (lundi au format AAAA-MM-JJ ; par défaut la dernière semaine complète) : réalisé contre
    prévu jour par jour, séances clés, charge, sommeil, FC de repos et VFC comparées aux 4 semaines d'avant,
    évolution du 10 km estimé, alertes et ajustements proposés."""
    from datetime import date as _d

    from coach import report
    s, db = _ctx()
    return report.build(db, s, _d.fromisoformat(lundi)) if lundi else report.ensure_last_week(db, s)


@tool
def alertes() -> dict:
    """Alertes du jour : sommeil court avant une séance dure, FC de repos ou VFC anormales, charge qui dérape, dette de
    sommeil, hausse brutale du kilométrage, séances de qualité manquées. Chacune avec un conseil."""
    from coach.alerts import alerts
    s, db = _ctx()
    return {"alertes": alerts(db, s)}


@tool
def modifications_plan(nombre: int = 20) -> dict:
    """Historique des modifications du plan envoyées sur COROS depuis l'appli (jour, avant, après, raison, statut)."""
    from coach.plan_edit import describe
    _, db = _ctx()
    return {"modifications": [{"envoyee_le": h["created_at"], "jour": h["date"], "avant": describe(h["before"]),
                               "apres": describe(h["after"]), "raison": h["reason"], "statut": h["status"]}
                              for h in db.plan_changes(nombre)]}


@tool
def enregistrer_verdict(label_id: str, texte: str, note: float | None = None) -> str:
    """Enregistre le verdict rédigé pour une séance ; il s'affiche dans le dashboard."""
    _, db = _ctx()
    if not db.activity(label_id):
        return f"Séance {label_id} inconnue."
    db.save_verdict(label_id, texte.strip(), note)
    return "Verdict enregistré."
