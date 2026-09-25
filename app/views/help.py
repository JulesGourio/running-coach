import streamlit as st

st.title("Aide")
st.caption("Ce que fait chaque onglet, d'où viennent les chiffres, et comment s'en servir.")

tabs = st.tabs(["Démarrer", "Aujourd'hui", "Séances", "Charge", "Progression", "Historique", "Récupération", "Plan",
                "Séances types", "Jour J", "Alertes et bilan", "Claude et commandes", "Glossaire"])

with tabs[0]:
    st.markdown("""
### Démarrer
1. **Connexion à COROS** (une fois) : `uv run coach login` dans le terminal, puis autoriser dans le navigateur.
2. **Premier import** : `uv run coach history --days 3650` récupère toutes tes séances et nuits depuis l'ouverture du
   compte, puis `uv run coach sync --max-fit 50` télécharge les fichiers détaillés.
3. **Ensuite** : le bouton **Synchroniser** en haut de chaque page (3 dernières semaines : séances, sommeil,
   récupération, charge, plan).

**D'où viennent les données**
- Serveur officiel COROS (comme Claude) : séances, sommeil, VFC, FC de repos, charge, prédictions, plan.
- Fichiers FIT (le détail seconde par seconde de chaque séance) : COROS en autorise 50 par jour ; au-delà l'appli
  passe par l'API web de COROS (identifiants dans `.env`).
- Météo du jour J : Open-Meteo.

Tout reste en local, dans le dossier `data/` (non versionné).
""")

with tabs[1]:
    st.markdown("""
### Aujourd'hui
- **Alertes** en haut de page, avec un conseil : voir l'onglet *Alertes et bilan*.
- **Bilan de la semaine** (ouvert le lundi) : réalisé contre prévu, séances clés, sommeil, récupération, ajustements.
- **10 km estimé, projection au jour J, chances A/B, VMA retenue** : voir *Progression*.
- **Forme du jour** (0-100) : VFC et FC de repos comparées à tes 4 dernières semaines, sommeil, fraîcheur.
  Vert ≥ 70, orange 50-69, rouge < 50.
- **Séance du jour** du plan, avec un conseil selon la forme.
- **Charge** : forme, fatigue, fraîcheur, ratio de charge COROS.
- **Dernières séances** et **profil** (FC max, repos, seuil, allure seuil, VO2max, zones).
""")

with tabs[2]:
    st.markdown("""
### Séances
Filtres **sport** (course, autres sports), **période** (3 mois à tout) et **type**.

**Type de séance** : déduit de ce que tu as couru, pas du plan : récupération, footing, footing + accélérations,
sortie longue (avec ou sans allure), VMA courte, VMA longue, allure spécifique, seuil, tempo, fartlek, côtes,
course / effort à fond. La structure est dans le titre (« VMA courte · 12 × 400 m »).

**Répétitions** : prises dans les **tours de la montre** quand ils les décrivent (séance structurée ou bouton tour :
mêmes valeurs que l'app COROS), sinon détectées dans le GPS et recadrées sur le cœur de l'effort.

**Note sur 10** : seulement pour une séance prévue au plan, elle mesure le **respect du plan** (écart aux allures
cibles, régularité, baisse de régime). Pas de note hors plan.

**Carte** colorée par l'allure (rouge = rapide), **profil d'altitude**, allure et FC avec les zones en bandes de
couleur, tours, meilleurs efforts, et **toutes tes séances du même type** depuis le début pour voir ta progression.
Les autres sports (randonnée, vélo…) ont leur propre fiche : distance, D+, vitesse, FC, calories, carte.
""")

with tabs[3]:
    st.markdown("""
### Charge
- **Charge d'une séance** : intensité × durée, 100 = une heure courue à ton allure seuil. Pour les autres sports et
  les séances sans détail : estimée d'après la FC et la durée (100 par heure à ta FC seuil).
- **Forme** : moyenne de la charge sur ~6 semaines (ce que ton corps a assimilé). **Fatigue** : sur 7 jours.
  **Fraîcheur** = forme − fatigue ; entre +5 et +15 : frais pour une course ; sous −20 : fatigue élevée.
- **Ratio de charge** (COROS, tous sports) : 7 derniers jours / 4 dernières semaines. Zone utile 0,8-1,3 ;
  au-dessus de 1,5 plusieurs jours, le risque de blessure monte.
- **Répartition facile / tempo / intense** : repère ~80 % du temps en facile.
""")

with tabs[4]:
    st.markdown("""
### Progression
**VMA retenue**, dans cet ordre :
1. un **test** saisi (6 minutes, effort chronométré à fond, ou valeur que tu fixes) : il prime 10 semaines ;
2. sinon la **relation FC-vitesse** de ta meilleure séance de fractionné (échauffement + fin de chaque répétition, même
   jour, mêmes conditions), prolongée jusqu'à 97 % de ta FC max ;
3. jamais en dessous des **allures courues** en fractionné (chaque répétition ramenée à la VMA selon sa durée).

Affichés en recoupement : allure seuil COROS (seuil ≈ 87 % de VMA) et VO2max COROS (≈ 3,5 × VMA).

**10 km estimé** : médiane de la VMA retenue (convertie avec ~90 % de VMA tenus sur 40 min), de la prédiction
COROS et de l'allure seuil. **Toutes les distances** : même principe du 5 km au marathon, avec ton record en repère.

**Projection au jour J** : niveau actuel + un gain par semaine (ta tendance si elle est nette, sinon 0,4 %),
plafonné à 0,8 %. La fourchette inclut le désaccord entre méthodes. **Chances A/B** : probabilité que la projection
passe sous chaque objectif ; suivies semaine après semaine.
""")

with tabs[5]:
    st.markdown("""
### Historique
Toute ton activité depuis l'ouverture du compte : période au choix (comparée à la précédente), course seule ou tous
les sports, km et heures par semaine ou par mois et par type, allure de chaque sortie, km par année, plus grosse
semaine et plus gros mois, **carte de tous tes parcours** et **carte de chaleur**.

**Records personnels** : meilleur temps sur 400 m, 1 km … marathon, n'importe où dans une sortie (comme Strava ou
COROS), sans les sauts GPS, les passages trop rapides pour ta cadence (voiture, vélo enregistrés en course) ni les
descentes. Le trail est exclu.
""")

with tabs[6]:
    st.markdown("""
### Récupération
- **Nuit** : une nuit à la fois (précédente, suivante, ou n'importe quelle date) : durée totale siestes comprises,
  horaires, phases comparées aux repères (profond 13-23 %, paradoxal 20-25 %, éveil < 5 %), réveils, siestes.
  **Conseillé ce soir** : 8 h de base, +30 min après une séance dure, une charge élevée ou une dette de sommeil,
  avec l'heure de coucher d'après ton heure de lever habituelle.
- **Statistiques** : moyennes par jour, nuits sous 7 h, siestes, régularité des horaires, phases nuit par nuit,
  moyennes par jour de semaine, par mois et par année.
- **VFC et FC de repos** : sous ta plage de VFC plusieurs jours, ou FC de repos +5 bpm = fatigue à respecter.
""")

with tabs[7]:
    st.markdown("""
### Plan
- **Plan principal** (celui en cours dans COROS) : semaines d'avant le plan et du plan, volume prévu et réalisé,
  et pour chaque jour la séance faite **à côté** de la séance prévue.
- **Modifier** une séance : volume, allures, remplacer par un modèle, échanger deux jours. Ou ajuster plusieurs séances
  d'un coup (une semaine ou tout le plan).
- **Suggestions** : alléger quand la forme ou la charge l'exigent, reprogrammer une séance manquée, programmer un test
  VMA, recaler les allures VMA sur ta VMA retenue.
- Chaque modification est **mise en attente** (avant/après), puis **envoyée sur COROS** après confirmation. Les jours
  passés ou réalisés ne changent jamais.
- **Nouveau plan** : générateur (5 km, 10 km, semi, marathon) ; il reste en brouillon et se crée dans COROS quand il
  démarre dans les 14 jours (règle COROS).
""")

with tabs[8]:
    st.markdown("""
### Séances types
Toutes les séances de fractionné par catégorie : fractionné court, fractionné long, seuil, allure spécifique,
pyramides et mixtes, côtes. Allures calculées sur ta VMA (modifiable en haut), ton seuil et ton allure objectif ;
tout se personnalise (répétitions, distance ou durée, % de VMA, récupération trottée ou marchée, séries).
**Ajouter au plan** met la séance en attente sur le jour choisi ; l'envoi se fait depuis la page Plan.
""")

with tabs[9]:
    st.markdown("""
### Jour J
Allure **kilomètre par kilomètre** à effort constant, avec les temps de passage.
- **Parcours** : GPX officiel, une de tes sorties faite sur le parcours, ou plat. Chaque km est ralenti en montée et
  accéléré en descente selon la pente.
- **Météo** : prévision Open-Meteo à moins de 16 jours, sinon la météo observée à cette date les 3 dernières années
  (ou saisie à la main). Chaleur : ~0,3 % de temps par °C au-dessus de 12 °C ; vent de face ~2 % par m/s.
- **Stratégie** : temps réaliste selon la météo, ou tenir le temps visé coûte que coûte.
- **Sur la montre** : le plan devient la séance du jour de course, un segment par km avec son allure.
""")

with tabs[10]:
    st.markdown("""
### Alertes
Vérifiées à chaque ouverture : sommeil court (2 des 3 dernières nuits sous 6 h 30) avant une séance dure, FC de repos en
hausse, VFC sous la normale, ratio de charge trop haut, dette de sommeil, kilométrage +35 % d'un coup, séances de
qualité manquées. Chacune avec un conseil.

### Bilan hebdo
Généré automatiquement le lundi pour la semaine écoulée et archivé : réalisé contre prévu jour par jour, séances clés,
charge, sommeil, FC de repos et VFC comparées aux 4 semaines d'avant, évolution du 10 km estimé, ajustements proposés.
""")

with tabs[11]:
    st.markdown("""
### Avec Claude (Claude Code dans VS Code)
Claude lit les mêmes analyses via le serveur local `running-coach` : `resume`, `seances`, `analyse_seance`,
`progression`, `charge`, `plan`, `alertes`, `bilan_semaine`, `modifications_plan`, `synchroniser`,
`enregistrer_verdict`. Exemples : « juge ma séance d'hier », « fais le bilan de ma semaine », « suis-je dans les temps
pour le sub-40 ? ». Il peut aussi modifier le plan avec le connecteur COROS.

### Commandes (terminal)
| Commande | Effet |
|---|---|
| `uv run coach login` | connexion à COROS |
| `uv run coach sync [--days N] [--max-fit N]` | synchronisation et analyse |
| `uv run coach history [--days N]` | tout l'historique (séances et nuits) |
| `uv run coach analyze [--force]` | recalcul des analyses |
| `uv run coach status` | forme du jour dans le terminal |
| `uv run coach dashboard` | cette appli |
""")

with tabs[12]:
    st.markdown("""
### Glossaire
- **VMA** : vitesse maximale aérobie, la vitesse tenue à VO2max (~6 min à fond).
- **Allure seuil** : l'allure tenable environ une heure ; au-delà, l'acide lactique s'accumule.
- **FC seuil (LTHR)** : la FC à cette allure. **FC max** : la plus haute atteinte.
- **Zones** : Z1 récupération, Z2 endurance, Z3 tempo, Z4 seuil, Z5 VO2max (bornes sur la page Aujourd'hui).
- **VFC** : variabilité de la FC la nuit ; plus haute = mieux récupéré.
- **Dérive cardiaque** : hausse de la FC à allure égale entre les deux moitiés d'une sortie ; sous 5 % = endurance solide.
- **Fractionné court / long** : répétitions de moins / plus de ~2 minutes à allure VMA.
- **Affûtage** : dernières semaines avant la course, volume réduit, intensité gardée.
""")
