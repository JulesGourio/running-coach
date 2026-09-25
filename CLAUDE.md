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

## Repères de forme (mis à jour au fil des check-ins)

Voir `README.md` pour le snapshot de départ. Lors d'un check-in, mettre à jour le README avec
les nouvelles métriques clés (VO2max, allure seuil, prédiction 10 km, tendance de charge) si
elles ont significativement bougé, pour que les sessions futures aient un historique lisible.
