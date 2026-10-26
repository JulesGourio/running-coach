"""Plus (the other pages), Réglages (COROS sign-in, credentials, profile, data transfer) and Aide."""
from __future__ import annotations

from pathlib import Path

from appkit import Result, ui

from coach import config
from coach.mobile import app, ctx, fmt, last_sync


@app.screen("plus")
def plus():
    links = [
        ("charge", "Charge", "Forme, fatigue, fraîcheur, volume et intensité"),
        ("recuperation", "Récupération", "Forme du jour, sommeil, VFC et FC de repos"),
        ("historique", "Historique", "Kilomètres, records, années"),
        ("seances_types", "Séances types", "Fractionnés calculés sur ta VMA, à ajouter au plan"),
        ("jour_j", "Jour J", "Plan de course km par km avec la météo"),
        ("bilan", "Bilan de la semaine", "Réalisé contre prévu et ajustements"),
        ("reglages", "Réglages", "COROS, profil, objectif, import des données"),
        ("aide", "Aide", "D'où viennent les chiffres"),
    ]
    return ui.page("Plus", ui.rows([ui.row(t, sub=sub, open=ui.link(sc)) for sc, t, sub in links]))


@app.screen("reglages")
def reglages():
    from coach import vault
    from coach.sources import coros

    s, db = ctx()
    connected = coros.connected(s)
    prof = {k: config.env(k) or "" for k in config.PROFILE_KEYS}
    n_acts = len(db.activities(sports="all"))
    n_fit = sum(1 for a in db.activities(sports="all") if a.get("fit_path"))
    return ui.page(
        "Réglages",
        ui.card("COROS",
                ui.alert("good" if connected else "warn", "Connecté au serveur officiel COROS" if connected else "Pas encore connecté",
                         None if connected else "Connecte-toi : la page COROS s'ouvre dans l'appli, comme pour Claude."),
                ui.buttons(ui.button("Se reconnecter" if connected else "Se connecter à COROS", "coros_connexion", icon="login",
                                     style="secondary" if connected else "primary"),
                           ui.button("Se déconnecter", "coros_deconnexion", style="text", confirm="Oublier la connexion COROS de ce téléphone ?")
                           if connected else None),
                ui.sync_status(last_sync(db)),
                ui.button("Tout l'historique COROS", "historique_coros", style="secondary", icon="history",
                          confirm="Récupérer les résumés de toutes les séances et nuits depuis l'ouverture du compte ?")),
        ui.card("API web COROS (au-delà de 50 fichiers FIT par jour)",
                ui.muted("Facultatif. Non officielle : elle peut cesser de fonctionner. Identifiants chiffrés par le téléphone."),
                ui.form([ui.field("coros_email", "E-mail COROS", "text", "", placeholder="déjà renseigné" if vault.get("coros_email") else None),
                         ui.field("coros_password", "Mot de passe COROS", "secret", "",
                                  placeholder="déjà renseigné" if vault.get("coros_password") else None)],
                        "secrets_enregistrer", "Enregistrer"), collapsed=True),
        ui.card("Objectif et profil",
                ui.muted("Vide : valeur estimée depuis tes séances (FC, allure seuil) ou par défaut."),
                ui.form([ui.field(k, label, "date" if k == "GOAL_DATE" else "text", prof[k]) for k, label in config.PROFILE_KEYS.items()],
                        "profil_enregistrer", "Enregistrer le profil"), collapsed=True),
        ui.card("Données",
                ui.muted(f"{n_acts} séances, {n_fit} fichiers FIT sur ce téléphone."),
                ui.file_button("Importer les données du PC (.zip ou .sqlite)", "donnees_importer",
                               confirm="Remplacer les données de ce téléphone par ce fichier ? L'ancienne base est gardée en copie."),
                ui.file_button("Importer un fichier .fit", "fit_importer"),
                ui.export_button("Exporter mes données (.zip)", "donnees_exporter", "coach-mobile.zip", "application/zip"),
                ui.muted("Sur le PC : `uv run coach export-mobile` crée l'archive à copier ici ; `uv run coach import-mobile <fichier>` "
                         "reprend celle du téléphone.")),
        ui.card("Notifications", ui.muted("Alertes du jour, séance analysée, bilan du lundi, COROS à reconnecter."),
                ui.button("Envoyer une notification de test", "notification_test", style="secondary")),
        ui.muted(f"Données : {s.data_dir}"),
    )


@app.action("coros_connexion")
def coros_connexion():
    from coach.sources import coros_light
    s, _ = ctx()
    url = coros_light.login_start(s)
    return Result(webauth={"url": url, "prefix": coros_light.redirect_uri(s), "finish": "coros_connexion_fin",
                           "title": "Connexion COROS"}, reload=False)


@app.action("coros_connexion_fin")
def coros_connexion_fin(url: str):
    from coach.sources import coros_light
    s, _ = ctx()
    coros_light.login_finish(s, url)
    return Result(message="Connecté à COROS. Première synchronisation lancée.", sync=True)


@app.action("coros_deconnexion")
def coros_deconnexion():
    from coach.sources import coros_light
    s, _ = ctx()
    coros_light.store(s).clear()
    return "Connexion COROS oubliée."


@app.action("secrets_enregistrer")
def secrets_enregistrer(coros_email: str = "", coros_password: str = ""):
    from coach import vault
    saved = []
    for name, value in (("coros_email", coros_email), ("coros_password", coros_password)):
        if value.strip():
            vault.set(name, value.strip())
            saved.append(name)
    return "Identifiants enregistrés." if saved else "Rien de changé (champs vides)."


@app.action("profil_enregistrer")
def profil_enregistrer(**valeurs):
    config.save_profile({k: v for k, v in valeurs.items() if k in config.PROFILE_KEYS})
    s, db = ctx()
    from coach.sync import analyze
    analyze(s, db, log=lambda _: None)  # a new profile changes the zones: analyses are recomputed
    return "Profil enregistré, analyses recalculées."


@app.action("donnees_importer")
def donnees_importer(path: str, name: str = ""):
    from coach.transfer import import_bundle
    s, _ = ctx()
    r = import_bundle(s, Path(path))
    msg = f"{r['seances']} séances importées, {r['fit']} fichiers FIT."
    if r["fit_absents"]:
        msg += f" {r['fit_absents']} fichiers manquants seront retéléchargés."
    return msg


@app.action("fit_importer")
def fit_importer(path: str, name: str = ""):
    from coach.sources.fit_folder import import_folder
    from coach.sync import analyze
    s, db = ctx()
    labels = import_folder(Path(path).parent, db, s.fit_dir)
    analyze(s, db, log=lambda _: None)
    return f"{len(labels)} fichier(s) importé(s)." if labels else "Aucune séance reconnue dans ce fichier."


@app.action("donnees_exporter")
def donnees_exporter(dest: str):
    from coach.transfer import export_bundle
    s, _ = ctx()
    r = export_bundle(s, Path(dest))
    return Result(message=f"Archive prête : {r['seances']} séances, {r['fit']} fichiers FIT.", reload=False)


@app.action("notification_test")
def notification_test():
    from coach import notify
    ok = notify.send("Carnet de course", "Les notifications fonctionnent.")
    return "Notification envoyée." if ok else "Notifications refusées : autorise-les dans les réglages Android."


HELP = [
    ("Démarrer", [
        "Réglages → « Se connecter à COROS » : la page de COROS s'ouvre, tu autorises, c'est fait (une fois).",
        "Pour reprendre tout l'historique du PC : `uv run coach export-mobile` sur le PC, copie le .zip sur le téléphone, "
        "puis Réglages → « Importer les données du PC ».",
        "Ensuite la synchro tourne seule chaque matin vers 7 h 15, ou avec le bouton « Synchroniser ».",
    ]),
    ("D'où viennent les données", [
        "Serveur officiel COROS : séances, sommeil, VFC, FC de repos, charge, prédictions, plan.",
        "Fichiers FIT (le détail seconde par seconde) : COROS en autorise 50 par jour ; au-delà, l'API web si tu as saisi tes identifiants.",
        "Tous les calculs tournent sur le téléphone, avec le même code que sur le PC. Rien ne part ailleurs que chez COROS (et Open-Meteo pour le Jour J).",
    ]),
    ("Aujourd'hui", [
        "Alertes du jour, forme du jour (VFC et FC de repos comparées à tes 4 dernières semaines, sommeil, fraîcheur) : vert ≥ 70, orange 50-69, rouge < 50.",
        "Séance du jour avec un conseil, objectif (10 km estimé, projection, chances A/B, VMA), charge et dernières séances.",
    ]),
    ("Séances", [
        "Le type vient de ce qui a été couru (tours de la montre, sinon flux GPS), pas du plan. La note sur 10 mesure le respect du plan.",
        "Découplage cardiaque : perte d'efficacité entre la 1re et la 2de moitié ; au-delà de 5 %, l'endurance ne suit pas.",
    ]),
    ("Charge", [
        "Forme (42 j), fatigue (7 j), fraîcheur = forme − fatigue. Ratio aigu/chronique : optimal 0,8-1,3, excessif au-delà de 1,5.",
        "Repère d'intensité : environ 80 % du temps en facile.",
    ]),
    ("Progression", [
        "VMA d'entraînement : un test de terrain (6 min ou effort chronométré) prime ; sinon la relation FC-vitesse ; jamais sous les allures courues.",
        "Une VMA de test progressif (VAMEVAL) est affichée pour info : elle surestime ce que tu tiens en fractionné.",
        "10 km estimé : médiane de la VMA, de la prédiction COROS et du seuil COROS.",
    ]),
    ("Plan", [
        "Chaque modification est mise en attente, affichée avant/après, puis envoyée sur COROS après confirmation.",
        "Jamais les jours passés ou réalisés ; allures entre 2:00 et 24:59/km. L'historique des envois est gardé.",
        "Claude peut aussi modifier le plan depuis la conversation : c'est le même plan COROS.",
    ]),
    ("Claude", [
        "Sur le PC, Claude Code lit les mêmes analyses (serveur MCP) et rédige les verdicts. Copie l'archive du PC pour les voir ici.",
    ]),
]


@app.screen("aide")
def aide():
    return ui.page("Aide", *[ui.card(t, ui.bullets(items), collapsed=i > 0) for i, (t, items) in enumerate(HELP)])
