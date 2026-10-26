# Méthodologie du coach

Contexte pour toute session future travaillant sur ce projet.

## Outils disponibles

Le connecteur MCP COROS (`mcp__COROS__*`) donne accès à :
- Lecture : activités (`querySportRecords`, `getActivityDetail`, `queryActivityLapData`),
  charge d'entraînement (`queryTrainingLoadAssessment`), récupération (`queryRecoveryStatus`),
  fitness/VO2max/prédictions de course (`queryFitnessAssessmentOverview`), sommeil/HRV/stress
  (`querySleepOverview`, `querySleepHrv`, `queryHealthCheckTimeSeries`, `queryStressLevel`),
  fréquence cardiaque (`queryAvgHeartRate`, `queryRestingHeartRate`), plan/planning
  (`queryTrainingPlanLibrary`, `queryTrainingSchedule`, `queryTrainingPlanDetails`).
- Écriture : `createTrainingPlan` (une seule fois par plan — ne jamais recréer un plan existant),
  `updateTrainingPlan` (modifier un plan en cours), `createScheduledWorkout` /
  `updateScheduledWorkout` (séances ponctuelles hors plan).

Le Plan ID du bloc en cours ne doit jamais être montré à l'utilisateur (contrainte de l'outil).

## Principes de coaching à respecter

- **Toujours partir des vraies données** (pas d'estimation à l'aveugle) : interroger
  `queryTrainingLoadAssessment`, `queryRecoveryStatus` et `querySportRecords` avant de juger
  si une semaine s'est bien passée.
- **Être honnête sur la faisabilité des objectifs.** Ne pas enjoliver une prédiction de course ;
  donner un objectif réaliste à côté d'un objectif ambitieux quand l'écart est important.
- **Ne pas ignorer les signaux de surcharge** : un `Load Ratio` > ~1.4-1.5 sur plusieurs jours
  consécutifs ("Excessive") ou une récupération durablement basse doit faire réduire le volume
  ou l'intensité de la semaine suivante avant d'ajouter du contenu.
- **Ajuster plutôt que recréer.** Si le plan doit changer (séance manquée, fatigue, gêne
  physique), utiliser `updateTrainingPlan` sur la semaine concernée plutôt que de recréer un
  nouveau plan.
- Les allures dans les séances sont en secondes/km (ex: 4:00/km = 240). Toujours vérifier
  qu'une allure absolue reste dans les bornes 120–1499 s/km avant d'écrire une séance.

## Appli locale (source principale d'analyse)

Package Python `coach/` (voir README). En local, le serveur MCP `running-coach` (déclaré dans `.mcp.json`)
expose les analyses calculées à partir des fichiers FIT : `resume`, `seances`, `analyse_seance`,
`progression`, `charge`, `plan`, `alertes`, `bilan_semaine`, `modifications_plan`, `enregistrer_verdict`,
`synchroniser`. Pour un bilan de semaine, commence par `bilan_semaine` et `alertes`.

Le type de chaque séance vient de ce qui a été couru (tours de la montre sinon flux GPS), pas du plan ;
la note sur 10 n'existe que pour une séance prévue (respect du plan). VMA d'entraînement : un test de terrain
(6 min, effort chronométré) prime, sinon la relation FC-vitesse, jamais sous les allures courues. Une VMA de
test progressif (VAMEVAL) n'est jamais utilisée pour les allures : elle surestime ce que Jules tient en
fractionné (voir README).

Pour juger une séance :
1. Lis `analyse_seance` (métriques, répétitions contre la cible, constats automatiques, note sur 10).
2. Rédige un verdict court et précis en français : ce qui est réussi, ce qui ne l'est pas, avec les chiffres
   (allures en min:s/km, FC, découplage, part en zones faciles), puis une consigne concrète pour la
   prochaine séance du même type. Tu peux corriger la note automatique si le contexte le justifie
   (météo, dénivelé, séance adaptée volontairement).
3. Enregistre-le avec `enregistrer_verdict` : il s'affiche dans le dashboard Streamlit.

Pour un bilan de semaine, croise `resume`, `charge` et `plan`.

Le plan se modifie de deux façons, sur le même plan COROS :
- par Claude, avec le connecteur COROS (`updateTrainingPlan`), quand Jules le demande dans la conversation ;
- par Jules dans la page Plan du dashboard (`coach/plan_edit.py`) : modifier, alléger, décaler les allures,
  échanger deux jours, suggestions selon la forme et la charge. Chaque modification est mise en attente,
  affichée avant/après, puis envoyée sur COROS après confirmation ; l'historique est dans la table
  `plan_changes` (outil `modifications_plan`). Consulte-le avant de proposer un changement, pour ne pas
  défaire ce que Jules vient de régler.
Dans les deux cas : jamais les jours passés ou réalisés, allures entre 120 et 1499 s/km.

Code : les réponses COROS du serveur officiel sont du texte, lu par `coach/sources/parsers.py`.
Si COROS change son format, adapte ces fonctions et `tests/test_parsers.py`. Lance `uv run pytest`
avant de committer.

## Appli Android (téléphone, sans serveur)

`android/` : le moteur `coach/` tourne sur le téléphone avec Chaquopy ; les écrans sont des fonctions Python dans
`coach/mobile/` qui renvoient des blocs `appkit.ui`, dessinés par la coque Kotlin du kit commun (`android/kit/`,
guide `android/kit/KIT.md`, skill `appli-android`). Aucun calcul en Kotlin. L'APK est construit par la CI
(GitHub Actions → Android → artefact). Règles :
- `coach/` ne doit pas importer `mcp`, Streamlit, plotly ou FastAPI hors des modules réservés au PC
  (`mcp_server.py`, `api.py`, `cli.py`, `sources/coros_mcp.py`) : `tests/test_portable.py` le vérifie.
- Le téléphone a pandas 2.1 et numpy 1.26 (job CI `phone-libs`).
- COROS : `coach.sources.coros.client()` choisit le client `mcp` (PC) ou le client léger httpx (téléphone,
  `coros_light.py`, connexion en deux temps `login_start` / `login_finish`).
- Outils de Claude : déclarés une fois avec `@tool` dans `coach/tools.py` (serveur MCP et appli).
- Nouvel écran : une fonction `@app.screen` dans `coach/mobile/`, testée par `tests/test_mobile.py` qui ouvre
  tous les écrans atteignables.
- Données PC → téléphone : `uv run coach export-mobile` puis Réglages → Importer.

## Façon de travailler (Claude Code)

- Agents du projet (`.claude/agents/`) : `explorateur` (Haiku, lecture seule), `codeur` (Sonnet, tâche délimitée,
  ne committe pas), `relecteur` (Opus, relit le diff avant chaque commit d'une étape).
- Petite modification : la faire soi-même. Chantier en plusieurs tâches indépendantes : un plan, puis un `codeur`
  par tâche. Fin d'étape ou changement qui touche le plan COROS, les jetons, la synchro ou la base : `relecteur`.
- Un hook lance `uv run pytest` avant chaque `git commit` et le bloque si un test échoue ; en session cloud,
  `.claude/hooks/session-start.sh` installe les dépendances.

## Page claude.ai (vue mobile)

La page « Carnet de course » (https://claude.ai/artifact/Ceh6AwSUkZkGPjL8kFSdT2, source
`dashboard/index.html`) lit COROS en direct et garde les notes du check-in du lundi dans sa base
(outil `ArtifactData`). Pour le check-in, suivre `.claude/skills/checkin/SKILL.md`.

## Repères de forme (mis à jour au fil des check-ins)

Voir `README.md` pour le snapshot de départ. Lors d'un check-in, mettre à jour le README avec
les nouvelles métriques clés (VO2max, allure seuil, prédiction 10 km, tendance de charge) si
elles ont significativement bougé, pour que les sessions futures aient un historique lisible.
