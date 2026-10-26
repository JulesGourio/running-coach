# Kit Android (Python + Kotlin)

Le kit fait d'un moteur Python une vraie appli Android, sans serveur ni PC allumé : Chaquopy fait tourner le
Python **sur le téléphone**, et une coque Kotlin/Compose unique dessine les écrans que le Python décrit.
Une nouvelle appli ne demande **aucun Kotlin** : seulement des écrans Python et une poignée de fichiers Gradle.

Version : `appkit.KIT_VERSION` (1.0.0). Né dans `running-coach` ; à recopier tel quel dans les autres dépôts.

## Ce qu'il contient

```
android/kit/
├── KIT.md                       ce fichier
├── python/appkit/               la moitié Python (testée sur le PC comme le reste)
│   ├── app.py                   App (écrans, actions, onglets, synchro) et Result
│   ├── ui.py                    les blocs d'écran (page, metrics, chart, form…)
│   └── bridge.py                ce que Kotlin appelle : start, manifest, screen, action, sync
└── src/main/java/fr/julesgourio/kit/   la moitié Kotlin, compilée dans l'appli
    ├── Kit.kt                   KitConfig (module Python, nom, icône, heure de synchro, verrou)
    ├── engine/                  Engine (Chaquopy), SecretStore (Keystore), Notifier, Files
    ├── work/                    Scheduler + SyncWorker (WorkManager, synchro quotidienne)
    └── ui/                      KitActivity (verrou, onglets, piles), Screen, Blocks, Charts, WebAuth
```

Ce que la coque sait faire, pour toutes les applis :
- verrou par empreinte ou code après 5 minutes en arrière-plan ;
- onglets en bas (jusqu'à 5), une pile de navigation par onglet, retour Android ;
- tirer pour rafraîchir, rechargement automatique après chaque synchro ;
- synchro quotidienne en arrière-plan à l'heure choisie, bouton « Synchroniser » ;
- notifications du téléphone (canaux alertes, urgent, synchro) ;
- secrets chiffrés par l'Android Keystore (`get`/`set`/`delete` depuis Python) ;
- connexion OAuth dans l'appli (WebView qui intercepte l'adresse de retour) ;
- import d'un fichier choisi par l'utilisateur, export d'un fichier où il veut ;
- graphiques (courbes, barres, barres empilées, horizontales), tracés GPS, tableaux, formulaires.

## Créer une nouvelle appli

1. **Moteur portable.** Le package Python ne doit pas importer de bibliothèque absente du téléphone (Streamlit,
   `mcp`, keyring, plotly…) en dehors des modules réservés au PC. Ajouter un test qui le vérifie
   (`tests/test_portable.py` de running-coach). Les secrets passent par un `vault` à backends interchangeables,
   les notifications par un `notify.set_local(handler)`.
2. **Écrans.** Un module, par exemple `monappli/mobile/__init__.py` :

   ```python
   from appkit import App, Result, ui

   app = App("Mon appli", tabs=[("accueil", "Accueil", "home"), ("plus", "Plus", "more")], sync_hour=7, sync_minute=30)

   @app.on_start
   def start(data_dir, secrets, notifier):      # dossier privé de l'appli, coffre Keystore, notifications
       os.environ["MONAPPLI_DATA_DIR"] = str(data_dir)
       vault.use(secrets); notify.set_local(notifier)

   @app.on_sync
   def sync() -> list[str]:                     # chaque matin et bouton « Synchroniser »
       return ["3 opérations récupérées"]

   @app.screen("accueil")
   def accueil(periode: int = 30):               # les arguments viennent des choix, pagers et liens
       return ui.page("Accueil", ui.choice("periode", [(30, "30 j"), (365, "1 an")], periode),
                      ui.metrics(ui.metric("Total", "12 345 €", "+2 %", sub_tone="good")))

   @app.action("enregistrer")
   def enregistrer(note: str = ""):
       ...
       return "Enregistré."                       # ou Result(message=…, open=ui.link("accueil"), back=True…)
   ```
3. **Tests.** Ouvrir tous les écrans depuis les onglets avec `appkit.bridge` (modèle :
   `tests/test_mobile.py` de running-coach), et ajouter `pythonpath = [".", "android/kit/python"]` à pytest.
4. **Projet Android.** Recopier `android/` de running-coach sans `app/build` : `settings.gradle.kts`,
   `build.gradle.kts`, `gradle/` (wrapper et `libs.versions.toml`), `gradle.properties`, `gradlew*`, `kit/`, et
   `app/` en changeant :
   - `app/build.gradle.kts` : `namespace`, `applicationId`, la tâche `copyEngine` (nom du package et modules
     réservés au PC), le mot de passe de la clé ;
   - `app/requirements.txt` : les dépendances Python du téléphone ;
   - `CoachApp.kt` : `KitConfig(pythonModule = "monappli.mobile", …)` ; `MainActivity` reste `KitActivity()` ;
   - `res/values/strings.xml` (nom), `colors.xml`, les deux icônes ;
   - une nouvelle clé de signature : `keytool -genkeypair -keystore app/monappli.keystore -storetype PKCS12
     -alias monappli -keyalg RSA -keysize 2048 -validity 36500`.
5. **CI.** Recopier `.github/workflows/android.yml` (l'APK est un artefact de chaque passage) et le job
   `phone-libs` de `tests.yml` si le moteur utilise pandas ou numpy (versions de Chaquopy : pandas 2.1.3,
   numpy 1.26.2 pour Python 3.13).
6. **Installer.** GitHub → Actions → Android → dernier passage vert → artefact → ouvrir l'APK sur le téléphone.

## Les blocs (`appkit.ui`)

| Bloc | Rôle |
|---|---|
| `page(titre, *blocs, subtitle=)` | un écran |
| `title`, `text` (`**gras**`, styles body/muted/small/big), `muted`, `bullets`, `divider` | texte |
| `alert(niveau, titre, texte)` | encadré bad/warn/info/good (rouge/orange/vert acceptés) |
| `metrics(metric(label, valeur, sous-titre, tone, sub_tone, open), columns=2)`, `big` | chiffres clés |
| `rows(row(titre, sub, value, tone, badge, open, action))` | liste ; `open` = lien, `action` = action au toucher |
| `card(titre, *blocs, tone, open, collapsed)` | groupe, dépliable si `collapsed` vaut True/False |
| `table(colonnes, lignes, tones)` | tableau qui défile de côté |
| `chart(titre, labels, *series, kind, y, reverse, bands, lines, y_min, y_max, highlight)` | graphique |
| `route(points)` | tracé GPS (sans fond de carte) |
| `choice(nom, options, valeur)`, `pager(label, prev, next)` | rechargent l'écran avec d'autres arguments |
| `button(label, action, args, confirm, style, icon)`, `buttons(...)` | action, avec confirmation éventuelle |
| `form(champs, action, submit, args, confirm, live)` + `field(nom, label, kind, valeur, options)` | formulaire ; `live=True` recharge l'écran avec les valeurs au lieu d'appeler l'action |
| `file_button(label, action, mime)` | choisir un fichier : `action(path=…, name=…)` |
| `export_button(label, action, filename)` | `action(dest=…)` écrit le fichier, la coque le copie où l'utilisateur veut |
| `sync_status(derniere)` | bouton Synchroniser et état de la synchro |

Graphiques : `kind` line, bar, stack, hbar ; séries `series(nom, valeurs, couleur, style)` avec style line, dash,
points, bar, area ; `y` num, int, pace (s/km → m:ss), time, pct, hours, km. Une valeur `None` coupe la courbe.
Tons : good, bad, warn, info, muted ou une couleur `#rrggbb`. Icônes : today, run, calendar, trend, chart,
heart, bed, history, fitness, flag, help, settings, more, home, bank, insights, receipt, bell, person, sync,
refresh, upload, download, delete, login, watch (`ui/Icons.kt`).

`Result` d'une action : `message`, `reload` (par défaut), `back`, `open=ui.link(écran, **args)`,
`webauth={"url", "prefix", "finish", "title"}` (connexion dans l'appli ; l'adresse de retour est passée à
l'action `finish` sous `url`), `sync=True` (lance la synchro). Une exception devient un message d'erreur.
Les valeurs des formulaires arrivent en texte ; `bridge` les convertit selon la valeur par défaut ou
l'annotation du paramètre (`int`, `float`, `bool`).

## Règles

- Aucun calcul en Kotlin : tout est dans le Python, testé sur le PC. La coque ne fait que dessiner.
- Un type de bloc inconnu est ignoré par la coque : on peut ajouter un bloc côté Python sans casser une vieille APK,
  mais il faut l'ajouter à `ui/Blocks.kt` pour qu'il s'affiche.
- Changer une clé d'un bloc se fait des deux côtés dans le même commit, avec le test des écrans.
- Le kit est identique dans chaque dépôt : on le modifie dans un dépôt, on monte `KIT_VERSION`, on recopie
  `android/kit/` dans les autres.
