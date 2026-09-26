# Running Coach

Coach de course à pied local : il récupère tes données COROS (fichiers FIT seconde par seconde, VFC,
sommeil, plan), calcule ce que COROS n'affiche pas, juge chaque séance par rapport au plan, et se branche
à Claude Code pour que Claude lise ces analyses et rédige les verdicts.

## Installation (VS Code)

Prérequis : [uv](https://docs.astral.sh/uv/) et Python 3.11 ou plus.

```bash
git clone https://github.com/JulesGourio/running-coach && cd running-coach
uv sync
cp .env.example .env          # optionnel : profil athlète, objectif, identifiants de repli
uv run coach login            # ouvre le navigateur pour autoriser l'accès à COROS
uv run coach sync --days 120 --max-fit 60   # premier import : 4 mois d'historique
uv run coach dashboard        # http://localhost:8501
```

Ensuite, `uv run coach sync` (30 derniers jours par défaut) ou le bouton **Synchroniser COROS** du
dashboard suffisent.

### Connexion à COROS, dans l'ordre

1. **Serveur officiel COROS** : connexion sécurisée comme Claude ou Cursor, sans mot de passe dans
   le code. Le jeton est stocké dans `data/.coros_oauth.json`, qui n'est pas versionné. L'hôte MCP
   dépend de la région du compte (`COROS_REGION`, `eu` par défaut ; `us` ou `asia`/`cn` sinon) ;
   ne renseigne `COROS_MCP_URL` que pour le forcer explicitement.
2. **API non officielle** (repli automatique si l'étape 1 échoue) : renseigne `COROS_EMAIL` et
   `COROS_PASSWORD` dans `.env`. Elle récupère les séances et les fichiers FIT, mais pas la VFC ni le
   sommeil. Elle n'est pas supportée par COROS et peut cesser de fonctionner.
3. **Import manuel** : `uv run coach import-fit ~/Téléchargements/fit`. Accepte n'importe quel dossier
   de fichiers `.fit`.

COROS limite le nombre de fichiers FIT téléchargeables par jour. `--max-fit` plafonne chaque
synchronisation, et les fichiers déjà téléchargés ne sont jamais redemandés.

## Relier Claude Code

Le fichier `.mcp.json` déclare le serveur MCP local `running-coach`. En ouvrant le dossier dans
VS Code avec Claude Code, accepte ce serveur. Claude peut alors :

| Outil | Rôle |
|---|---|
| `resume` | forme du jour, charge, prédictions, projection, dernières séances, séances à venir |
| `seances` / `analyse_seance` | toutes les métriques d'une séance et le verdict automatique |
| `progression` / `charge` / `plan` | tendances, modèle de charge, plan contre réalisé |
| `modifications_plan` | historique des modifications du plan faites depuis le dashboard |
| `enregistrer_verdict` | enregistre le verdict rédigé par Claude, affiché ensuite dans le dashboard |
| `synchroniser` | lance une synchronisation COROS |

Exemples : « juge ma séance d'hier », « fais le bilan de ma semaine », « suis-je dans les temps pour le
sub-40 ? ». Pour **modifier une séance**, Claude utilise son connecteur COROS (claude.ai) et écrit
directement dans ton calendrier.

## Ce que l'appli calcule

**Par séance**
- **Type d'après ce qui a été couru**, avec la structure dans le titre (« VMA courte · 12 × 400 m ») :
  récupération, footing, footing + accélérations, sortie longue, sortie longue avec allure, VMA courte,
  VMA longue, allure spécifique, seuil, tempo, fartlek, côtes, course / effort à fond (+ trail, tapis, piste).
- **Répétitions** : prises dans les tours de la montre quand ils les décrivent (séance structurée ou bouton tour,
  mêmes valeurs que l'app COROS), sinon détectées dans le flux GPS et recadrées sur le cœur de l'effort.
  Pour une séance prévue : écart à la cible en s/km, statut, régularité, baisse de régime, et une note de
  **respect du plan** sur 10 (pas de note pour une séance hors plan).
- **Discipline en endurance** : part du temps en zones faciles (objectif ≥ 90 %), allure comparée à la fourchette prévue.
- **Découplage cardiaque** (Pa:HR) : perte d'efficacité entre la 1re et la 2de moitié. Au-delà de 5 %,
  l'endurance ne suit pas sur la durée.
- **Charge et effort** :
  - charge rTSS (100 = 1 h à l'allure seuil) ;
  - TRIMP et hrTSS (charge calculée sur la FC) ;
  - allure ajustée au dénivelé et lissée (NGP) ;
  - efficacité (vitesse / FC) ;
  - temps par zone de FC et d'allure ;
  - cadence et foulée ;
  - meilleurs efforts de la séance.

**Dans le temps**
- **Forme, fatigue et fraîcheur** (CTL, ATL, TSB) calculées sur ta propre charge.
- **Ratio charge aiguë / chronique**, monotonie et contrainte (Foster).
- **Répartition facile / tempo / intense** par semaine (repère : environ 80 % facile).
- **Allure à FC fixe** sur les footings : l'indicateur le plus fiable de progrès aérobie.
- **VMA retenue**, dans cet ordre :
  1. un **test** récent (moins de 10 semaines) saisi dans la page Progression : 6 minutes, effort chronométré à
     fond (1500 m, 3000 m…) ou valeur connue ;
  2. sinon la **relation FC-vitesse** de la meilleure séance de fractionné des 6 dernières semaines : échauffement
     et fin de chaque répétition (allure corrigée du dénivelé) s'alignent presque en ligne droite ; prolongée
     jusqu'à 97 % de la FC max, elle donne la vitesse à VO2max même si les répétitions n'étaient pas à fond
     (lignes nettes seulement, R² ≥ 0,85, séance ayant atteint 90 % de la FC max) ;
  3. jamais en dessous des **allures courues** en fractionné (chaque répétition ramenée à la VMA selon sa durée :
     400 m ≈ 105 %, 1000 m ≈ 98 % ; moyenne des deux meilleures séances).
  Affichées en recoupement : allure seuil COROS (seuil ≈ 87 % de VMA) et VO2max COROS (≈ 3,5 × VMA, non retenue).
- **10 km estimé** : médiane de trois estimations (VMA retenue, prédiction COROS, allure seuil COROS ; le test seul
  s'il existe), la VMA étant convertie en temps de course selon la part tenable sur la durée (~90 % sur 40 min).
  Il n'y a ni course ni effort continu 5/10 km dans les données : Riegel, VDOT et vitesse critique sur les
  « meilleurs efforts » donnaient des résultats faux et ne sont plus utilisés.
- **Projection au jour de la course** et probabilité d'atteindre les objectifs A et B : niveau actuel amélioré
  d'un gain hebdomadaire (tendance récente si elle est nette, sinon 0,4 %/semaine), plafonné à 0,8 %/semaine.
- **Disponibilité du jour** (vert, orange, rouge) à partir de la VFC et de la FC de repos (comparées à tes
  4 dernières semaines), du sommeil et de la fraîcheur, avec un conseil sur la séance prévue.

Les FC max et au seuil sont estimées depuis tes séances (seuil = meilleure FC moyenne sur 20 min).
Pour plus de précision, renseigne `ATHLETE_HR_MAX`, `ATHLETE_LTHR` et `ATHLETE_THRESHOLD_PACE` dans `.env`.
Après un changement de profil, les analyses sont recalculées automatiquement.

## Historique et sommeil

- `uv run coach history --days 3650` (ou le bouton de la page **Historique**) récupère toutes les séances
  (résumés : distance, temps, allure, FC) et toutes les nuits depuis l'ouverture du compte COROS. Les fichiers
  FIT détaillés arrivent ensuite au fil des synchronisations : COROS en autorise 50 par jour.
- Page **Historique** : période réglable (30 jours à tout), comparée à la période précédente ; km par semaine ou
  par mois et par type de séance ; allure de chaque sortie ; km par année ; records (plus longue sortie, plus
  grosse semaine et plus gros mois) ; meilleure sortie sur 5 km, 10 km, semi et marathon.
- Page **Séances** : filtre par période et par type ; pour chaque séance, toutes les séances du même type depuis
  le début (allure des répétitions séance après séance).
- Page **Récupération** : dernière nuit en détail (phases comparées aux repères, siestes, réveils), sommeil
  conseillé pour la nuit suivante (8 h de base, +30 min après une séance dure, une charge élevée ou une dette
  de plus de 3 h sur 7 nuits) avec l'heure de coucher, dette sur 7 nuits, régularité des horaires, moyennes par
  jour de semaine, mois et année, liste des siestes, VFC et FC de repos.

## Navigation et nouveautés

Onglets en haut de page (plus de barre latérale) : Aujourd'hui, Séances, Charge, Progression, Historique,
Récupération, Plan, Séances types, Jour J, **Aide** (récapitulatif de chaque fonctionnalité et glossaire).

- **Tous les sports** : randonnée, vélo, rameur… sont importés avec leurs FIT (carte, D+, FC), comptés dans la
  charge (estimée d'après la FC et la durée) et visibles dans Séances et Historique.
- **FIT au-delà du quota** : passé les 50 fichiers par jour du serveur officiel, la synchro passe par l'API web
  COROS (`COROS_EMAIL`/`COROS_PASSWORD` dans `.env`).
- **Cartes** : parcours coloré par l'allure et profil d'altitude pour chaque sortie ; carte de tous les parcours et
  carte de chaleur dans Historique.
- **Records personnels** : meilleur temps n'importe où dans une sortie (400 m au marathon), sans sauts GPS,
  passages trop rapides pour la cadence ni descentes ; trail exclu (`coach/history.py:personal_records`).
- **Alertes** (`coach/alerts.py`) en haut de la page Aujourd'hui : sommeil court avant une séance dure, FC de repos
  en hausse, VFC basse, ratio de charge, dette de sommeil, hausse brutale du kilométrage, qualité manquée.
- **Bilan hebdo** (`coach/report.py`) généré le lundi et archivé.
- **Prédictions toutes distances** (5 km au marathon) et suivi des chances A/B semaine après semaine.
- **Sommeil** en trois onglets :
  - une nuit à la fois (frise sur 24 h, phases comparées aux zones normales) ;
  - statistiques (durée avec moyenne sur 7 jours, part de profond et de paradoxal, fenêtre coucher → lever) ;
  - VFC et FC de repos.
  Pour les nuits de l'historique long, COROS ne donne que les heures de coucher et de lever : la durée en est déduite.
- **Trail et randonnée** (`coach/metrics/session.py`) :
  - le temps en mouvement compte la marche en montée : un arrêt, c'est une vitesse d'effort, pente comprise, sous 0,8 m/s ;
  - allure d'effort, sur une courbe de coût de la pente de type Strava plutôt que Minetti, qui surestime le gain en descente ;
  - D-, km-effort, vitesse ascensionnelle, découpage km par km (`splits`), allure par classe de pente (`grade_bins`).
- **Historique** : l'allure moyenne ne porte que sur la route, la piste et le tapis.
- **Jour J** (`coach/raceplan.py`) : allure km par km selon le profil (GPX, une sortie ou plat) et la météo
  Open-Meteo (chaleur, vent), temps de passage, envoi sur la montre comme séance du jour de course.

Outils MCP ajoutés : `alertes`, `bilan_semaine`, `modifications_plan`.

## Plusieurs plans

L'onglet **Plan** montre le plan principal (celui en cours dans COROS) et des plans en brouillon. « + Nouveau
plan » génère un plan complet pour une course (5 km, 10 km, semi, marathon) : phases base / développement /
spécifique / course, volumes semaine par semaine (semaine plus légère toutes les 4, affûtage sur 2), séances de
qualité espacées, allures calculées sur la VMA, le seuil et l'allure objectif (`coach/plan_builder.py`).
Chaque jour d'un brouillon se remplace par une séance de la bibliothèque. COROS n'accepte un nouveau plan que
s'il démarre dans les 14 jours : le bouton « Créer dans COROS » s'active à ce moment-là.

Pour le plan principal : les semaines d'avant le plan sont affichées aussi (8 par défaut), avec le volume
réalisé et prévu semaine par semaine, et chaque jour montre la séance réalisée à côté de celle prévue.

## Séances types

La page **Séances types** regroupe les séances de fractionné par catégorie (fractionné court, fractionné long,
seuil, allure spécifique 10 km, pyramides et mixtes, côtes), avec allures calculées sur la VMA retenue, l'allure
seuil et l'allure objectif. Chaque séance se personnalise (répétitions, distance ou durée, % de VMA ou écart
d'allure, récupération trottée ou marchée, séries) et affiche le temps par répétition, le volume d'effort, la
distance et la durée totales. Un clic l'ajoute à un jour du plan (mise en attente, envoi depuis la page Plan).
Catalogue : `coach/workouts.py`.

## Plan modifiable

La page **Plan** du dashboard affiche le plan COROS semaine par semaine (volume prévu, réalisé, séances de
qualité, statut de chaque jour) et permet de le modifier :
- **Modifier une séance** : ajuster le volume (50-150 %) et les allures de qualité (± s/km), la remplacer par
  un modèle (footing, footing + accélérations, VMA, seuil, allure 10 km, sortie longue, sortie longue avec
  allure, repos) aux allures calculées sur tes zones et ta VMA, ou l'échanger avec un autre jour.
- **Ajuster plusieurs séances** : cette semaine ou toutes les semaines restantes, éventuellement seulement
  les séances de qualité (par exemple -3 s/km quand la VMA progresse).
- **Suggestions** : alléger ou remplacer la séance de qualité quand la forme du jour est orange ou rouge,
  alléger la semaine quand le ratio de charge COROS reste au-dessus de 1,5, reprogrammer une séance de
  qualité manquée sur le prochain jour facile.

Les modifications sont mises en attente et affichées avant/après, puis envoyées sur COROS (`updateTrainingPlan`,
seulement les jours changés) après confirmation, et relues aussitôt. Les jours passés ou déjà réalisés ne sont
jamais modifiés. L'historique est gardé en local et consultable par Claude (`modifications_plan`).

## Commandes

| Commande | Effet |
|---|---|
| `uv run coach login` | connexion au serveur officiel COROS |
| `uv run coach sync [--days N] [--max-fit N] [--source auto\|mcp\|web]` | synchronisation puis analyse |
| `uv run coach history [--days N]` | historique long : séances résumées et nuits (sans FIT) |
| `uv run coach import-fit DOSSIER` | import de fichiers FIT |
| `uv run coach analyze [--force]` | recalcul des analyses |
| `uv run coach status` | forme du jour et dernières séances dans le terminal |
| `uv run coach dashboard` | dashboard Streamlit |
| `uv run coach api [--port 8000]` | API HTTP locale (documentation sur `/docs`) |
| `uv run pytest` | tests |

Pour essayer sans COROS : `COACH_DATA_DIR=data-demo uv run python scripts/demo_data.py`, puis
`COACH_DATA_DIR=data-demo uv run coach dashboard` (8 semaines de séances simulées).

## Structure

```
coach/
  sources/     connexion officielle COROS, API non officielle, import FIT, lecture des réponses COROS
  fit.py       décodage des fichiers FIT
  metrics/     zones, métriques de séance, répétitions, charge, progression, disponibilité
  verdict.py   type de séance, note et constats
  sync.py      synchronisation et analyse
  service.py   vues partagées par le dashboard, l'API et le serveur MCP
  mcp_server.py, api.py, cli.py
app/           dashboard Streamlit
dashboard/     ancienne page claude.ai (vue mobile, lit COROS en direct)
tests/
```

Toutes les données restent en local dans `data/` (base SQLite, fichiers FIT, jeton COROS). Ce dossier
est exclu de git.

## Objectif et plan en cours

- 10 km le dimanche 13 décembre 2026. Objectif A : sub-40:00. Objectif B : 41:00 à 41:30.
- Forme au 25 septembre 2026 : VO2max 60, allure seuil 4:22/km, prédiction COROS 43:26,
  VMA retenue 16,0 km/h (relation FC-vitesse du 6 × 1 km du 24/09, fourchette 15,5-16,7 ; allures de
  fractionné 15,8 ; seuil COROS 15,8 ; VO2max COROS 17,1), 10 km estimé 42:05, projection au 13 décembre
  40:14 (fourchette 37:56-42:33). Test VMA de 6 minutes proposé pour trancher.
- Plan de 11 semaines dans le calendrier COROS (28 septembre → 13 décembre), réécrit le 25 septembre à la
  demande de Jules (le premier jugé trop facile ; il a déjà tenu cette charge pour un marathon) :
  5 séances par semaine dont 3 de qualité (VMA le mardi, seuil ou allure 10 km le jeudi, sortie longue avec
  allure le dimanche), footings en Z2 le mercredi et le samedi (avec accélérations), repos lundi et vendredi.
  Volume d'environ 58 km en semaine 1 à ~70 km en semaines 6-7, assimilation en semaines 4 et 8,
  affûtage en 10-11.
  1. Base (semaines 1 à 3)
  2. Développement (semaines 4 à 7)
  3. Spécifique (semaines 8 à 10)
  4. Course (semaine 11)
- Garde-fou : ratio de charge COROS > 1,5 plusieurs jours de suite ou VFC durablement basse → alléger la
  semaine suivante.

## Suivi automatique

Chaque lundi matin, une routine claude.ai suit `.claude/skills/checkin/SKILL.md`. Elle écrit une note
dans la page claude.ai et propose des ajustements sans les appliquer. Il faut lui avoir ajouté le
connecteur COROS : dans claude.ai, rubrique Routines, ouvre la routine puis **Edit** → **Connectors**.
