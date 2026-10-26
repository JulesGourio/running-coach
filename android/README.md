# Carnet de course sur Android

L'appli fait tourner le moteur Python du dépôt (`coach/`) directement sur le téléphone, grâce à Chaquopy.
Il n'y a ni serveur ni PC à garder allumé. Le PC continue de fonctionner comme avant (dashboard, Claude Code).

Toutes les pages du dashboard y sont : Aujourd'hui, Séances (et le détail de chaque séance), Plan (semaine,
modifications en attente puis envoi sur COROS, suggestions, brouillons et générateur), Progression, Charge,
Récupération, Historique, Séances types, Jour J, Bilan de la semaine, Réglages et Aide.

## Installer

1. GitHub → **Actions** → **Android** → dernier passage vert → artefact `carnet-de-course-apk` (un zip qui
   contient l'APK).
2. Sur le Pixel, ouvre l'APK et autorise l'installation depuis cette source la première fois.
3. Les versions suivantes s'installent par-dessus la précédente, sans perdre les données : elles sont toutes
   signées avec la même clé, `app/coach.keystore`.

## Premier lancement

1. **COROS** : Réglages → « Se connecter à COROS ». La page de COROS s'ouvre dans l'appli ; tu autorises,
   l'appli récupère le code toute seule et lance la première synchro.
2. **Historique du PC** (facultatif) : sur le PC, `uv run coach export-mobile` crée `coach-mobile.zip` (base,
   fichiers FIT, profil). Copie-le sur le téléphone, puis Réglages → « Importer les données du PC ».
   Sinon, Historique → « Tout l'historique COROS » récupère les résumés, et les fichiers FIT arrivent au fil
   des synchros (50 par jour).
3. **Objectif et profil** : Réglages → « Objectif et profil » (date et temps visés, FC max…).
4. Facultatif : identifiants de l'API web COROS (au-delà de 50 fichiers FIT par jour), chiffrés par le
   téléphone.

La synchro tourne ensuite chaque matin vers 7 h 15. Les alertes du jour, chaque séance analysée et le bilan du
lundi arrivent en notifications. L'appli se verrouille par empreinte ou par code après 5 minutes en arrière-plan.

## PC et téléphone

- Chaque appareil a sa base et sa connexion COROS (le plan COROS, lui, est commun : une modification faite
  sur le téléphone se voit sur le PC à la synchro suivante, et inversement).
- Réglages → « Exporter mes données » produit le même zip ; `uv run coach import-mobile <zip>` le reprend
  sur le PC (l'ancienne base est gardée en copie).
- Les verdicts de Claude sont écrits sur le PC (serveur MCP) : réexporte l'archive pour les voir sur le
  téléphone, ou écris le tien dans la séance.

## Construire en local

Il faut le SDK Android (Android Studio), Java 17 et Python 3.13 sur le PC. Ensuite :

```bash
cd android
./gradlew assembleDebug          # Windows : gradlew.bat assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Le moteur est recopié depuis `../coach` à chaque construction ; il n'est jamais dupliqué dans git. Les modules
réservés au PC restent en dehors : `mcp_server.py`, `api.py`, `cli.py` et `sources/coros_mcp.py`.

Pour tester sur le PC la connexion COROS du téléphone : `uv run coach login-light`, puis
`COACH_COROS_CLIENT=light uv run coach sync`.

## Organisation

- `kit/` : le kit commun (coque Kotlin et `appkit` Python), voir `kit/KIT.md`.
- `app/` : ce qui est propre à l'appli (nom, icônes, clé, `KitConfig`, dépendances Python).
- Les écrans sont en Python, dans `coach/mobile/`, et testés par `tests/test_mobile.py`.
