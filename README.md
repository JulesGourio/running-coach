# Running Coach

Coach automatique basé sur les données COROS, piloté via Claude.

## Source de données

Connecteur officiel **COROS MCP** (`mcp.coros.com`), connecté au compte Claude de l'utilisateur.
Donne accès en lecture aux activités, à la fréquence cardiaque, au sommeil, au HRV, à la charge
d'entraînement, à la récupération, et en écriture à la création de séances/plans d'entraînement
directement sur le calendrier COROS de l'utilisateur.

Un connecteur Strava officiel existe aussi dans le registre Claude si besoin d'une source
complémentaire, mais n'est pas utilisé pour l'instant.

## Objectif actuel

- **Course cible** : 10 km, dimanche 13 décembre 2026
- **Objectif A (ambitieux)** : sub-40:00 (4:00/km)
- **Objectif B (réaliste)** : ~41:00–41:30

## Snapshot de forme au démarrage (24-25 septembre 2026)

| Métrique | Valeur |
|---|---|
| VO2max (COROS) | 60 |
| Allure seuil | 4:22/km |
| Prédiction 10 km (COROS) | 43:26 |
| Récupération | 61% |

Contexte : plusieurs jours de charge "Excessive" (ratio ~1.5) début septembre, d'où un
démarrage de bloc en décrassage plutôt qu'en pleine charge.

## Plan d'entraînement

Un plan de 11 semaines (28 septembre → 13 décembre) a été créé et poussé sur le calendrier
COROS de l'utilisateur (5 jours de course/semaine, repos fixes lundi/vendredi) :

1. **Semaines 1-3 — Base** : décrassage puis réintroduction progressive du seuil et de la VO2max.
2. **Semaines 4-7 — Build** : volume de seuil et VO2max, sorties longues avec segments à allure objectif.
3. **Semaines 8-10 — Spécifique/Peak** : intervalles à allure objectif, sorties longues avec segments
   plus longs à allure objectif.
4. **Semaine 11 — Affûtage & course** : réduction de volume, rappels courts, course le 13 décembre.

Volume hebdomadaire : ~45 km (semaine 1) → pic ~63 km (semaine 5) → ~25 km (semaine course).

Le plan est modifiable directement dans l'app COROS ; il peut aussi être ajusté via Claude
(`updateTrainingPlan`) au fil des semaines selon la forme réelle.

## Dashboard « Carnet de course »

https://claude.ai/artifact/Ceh6AwSUkZkGPjL8kFSdT2 (privé, source : `dashboard/index.html`)

- **Données en direct** : la page appelle le connecteur COROS avec le compte de l'utilisateur.
  Elle affiche la récupération, la charge, la VFC, la FC de repos, le sommeil, les prochaines
  séances du plan, les séances récentes, le volume hebdomadaire et la prédiction 10 km.
- **Base de données de la page** :
  - `settings/athlete` : profil et objectif (date, objectifs A et B en secondes)
  - `reports/*` : notes du coach (check-ins et bilans)
  - `snapshots/<yyyyMMdd>` : historique VO2max, allure seuil et prédictions, écrit à chaque
    visite et à chaque check-in
  - `changes/*` : journal des modifications du plan
- **Coach dans la page** : le bouton « Demander au coach » ouvre une discussion avec Claude.
  Il peut lire le plan, analyser une séance, enregistrer un bilan et proposer une modification.
  Une modification n'est écrite dans COROS qu'après un clic sur « Appliquer ».

Pour republier après une modification de `dashboard/index.html`, publier le fichier avec l'outil
Artifact en passant l'URL ci-dessus.

## Suivi

- **Check-in automatique** chaque lundi matin : une session cloud suit
  `.claude/skills/checkin/SKILL.md`, écrit une note et un point de forme dans le dashboard et
  propose des ajustements sans les appliquer.
- **À la demande** : bouton « Bilan de la semaine » dans le dashboard, ou demander un check-in à
  Claude dans ce repo.

Voir `CLAUDE.md` pour la méthodologie détaillée.
