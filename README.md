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
| `enregistrer_verdict` | enregistre le verdict rédigé par Claude, affiché ensuite dans le dashboard |
| `synchroniser` | lance une synchronisation COROS |

Exemples : « juge ma séance d'hier », « fais le bilan de ma semaine », « suis-je dans les temps pour le
sub-40 ? ». Pour **modifier une séance**, Claude utilise son connecteur COROS (claude.ai) et écrit
directement dans ton calendrier.

## Ce que l'appli calcule

**Par séance**
- **Type et note sur 10** : footing, sortie longue, seuil, VMA, allure spécifique, course, ou séance hors plan.
- **Répétitions contre la cible** du plan. Elles sont retrouvées via les tours de la montre, ou détectées
  dans les données. Pour chacune : écart en s/km, statut, régularité et baisse de régime.
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
- **VMA estimée à partir des fractionnés** : les répétitions sont isolées de la récupération, puis chacune est
  ramenée à la VMA selon sa durée (un 400 m se court vers 105 % de VMA, un 1000 m vers 98 %). On retient la
  moyenne des deux meilleures séances des 6 dernières semaines ; les séances où la FC n'approche jamais le max
  sont ignorées. Recoupée avec l'allure seuil COROS (seuil ≈ 87 % de VMA) et la VO2max COROS (≈ 3,5 × VMA).
- **10 km estimé** : médiane de trois estimations (VMA des fractionnés, prédiction COROS, allure seuil COROS),
  la VMA étant convertie en temps de course selon la part tenable sur la durée (~90 % sur 40 min).
  Il n'y a ni course ni effort continu 5/10 km dans les données : Riegel, VDOT et vitesse critique sur les
  « meilleurs efforts » donnaient des résultats faux et ne sont plus utilisés.
- **Projection au jour de la course** et probabilité d'atteindre les objectifs A et B : niveau actuel amélioré
  d'un gain hebdomadaire (tendance récente si elle est nette, sinon 0,4 %/semaine), plafonné à 0,8 %/semaine.
- **Disponibilité du jour** (vert, orange, rouge) à partir de la VFC et de la FC de repos (comparées à tes
  4 dernières semaines), du sommeil et de la fraîcheur, avec un conseil sur la séance prévue.

Les FC max et au seuil sont estimées depuis tes séances (seuil = meilleure FC moyenne sur 20 min).
Pour plus de précision, renseigne `ATHLETE_HR_MAX`, `ATHLETE_LTHR` et `ATHLETE_THRESHOLD_PACE` dans `.env`.
Après un changement de profil, les analyses sont recalculées automatiquement.

## Commandes

| Commande | Effet |
|---|---|
| `uv run coach login` | connexion au serveur officiel COROS |
| `uv run coach sync [--days N] [--max-fit N] [--source auto\|mcp\|web]` | synchronisation puis analyse |
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
  VMA estimée sur les fractionnés 15,3 km/h, 10 km estimé 43:26, projection au 13 décembre 41:30
  (fourchette 40:07-42:56).
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
