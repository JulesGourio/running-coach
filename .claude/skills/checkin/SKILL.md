---
name: checkin
description: Check-in d'entraînement de Jules. Lit les données COROS de la semaine, compare au plan, écrit une note du coach et un point de forme dans le dashboard « Carnet de course ». À utiliser pour le check-in du lundi et quand Jules demande un bilan.
---

# Check-in du coach

Dashboard : https://claude.ai/artifact/Ceh6AwSUkZkGPjL8kFSdT2 (base de données lue et écrite avec l'outil `ArtifactData`).
Données : connecteur COROS (`mcp__COROS__*`). Charge ces outils avec ToolSearch s'ils sont différés.

## 1. Lire le contexte

- Dashboard : `settings/athlete` (profil, objectif), les 3 derniers `reports` (tri `createdAt` décroissant), les `changes` récents (modifications faites depuis la page).
- COROS :
  - `queryFitnessAssessmentOverview` (VO2max, allure seuil, prédictions)
  - `queryRecoveryStatus`
  - `queryTrainingLoadAssessment` avec `days: 14`
  - `querySportRecords` sur les 8 derniers jours, codes course `[100,101,102,103]`
  - `querySleepHrv`, `querySleepOverview` et `queryRestingHeartRate` sur 7 jours
  - `queryTrainingPlanLibrary` pour le plan en cours (ligne `execution`, `editable`), puis `queryTrainingPlanDetails` sur la semaine écoulée et sur les 14 prochains jours.

## 2. Analyser

- Semaine écoulée : séances prévues contre séances réalisées (distance, allure, FC). Séances manquées ou modifiées.
- Signaux de surcharge : ratio de charge > 1,3 plusieurs jours (> 1,5 = excessif), VFC sous la normale, FC de repos en hausse d'au moins 5 bpm, nuits de moins de 6 h 30.
- Progression : prédiction 10 km, VO2max et allure seuil comparés aux `snapshots` précédents et aux objectifs A et B.
- Sois honnête sur la faisabilité de l'objectif. Ne décris pas une progression que les données ne montrent pas.

## 3. Écrire dans le dashboard

Avec `ArtifactData` (une seule opération `batch`) :

- `snapshots/<yyyyMMdd>` (seulement s'il n'existe pas) :
  `{date: "yyyy-MM-dd", vo2max, level, threshold, p5, p10, half, marathon, source: "checkin"}`. Temps et allures en secondes (4:22/km = 262, 43:26 = 2606).
- `reports/<yyyyMMdd>-weekly` :
  `{kind: "weekly", createdAt: <ISO UTC>, title, summary, highlights: [], watch: [], recommendations: [], proposals: [{date: "yyyy-MM-dd", text}]}`.
  Français simple, phrases courtes, 3 éléments au plus par liste. `summary` en 2 paragraphes au plus.

## 4. Ne pas modifier le plan sans accord

Le check-in automatique **propose** les ajustements (`proposals`) sans les appliquer. Jules les valide depuis le dashboard (bouton « Voir avec le coach »).
Modifie le plan COROS (`updateTrainingPlan`) seulement si Jules le demande explicitement dans la conversation. Lis d'abord `queryTrainingPlanDetails`, remplace des journées entières, ne touche pas aux jours passés ou réalisés, et ajoute une entrée dans `changes`.

## 5. Terminer

Réponds avec un résumé de 3 à 5 lignes : l'état de forme, le point principal à surveiller, et les ajustements proposés.
