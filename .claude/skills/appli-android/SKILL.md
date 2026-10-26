---
name: appli-android
description: Crée ou met à jour l'appli Android d'un projet Python de Jules avec le kit commun (moteur Python sur le téléphone via Chaquopy, coque Kotlin unique qui dessine des écrans décrits en Python). À utiliser quand Jules veut « son appli sur le téléphone », un nouvel écran mobile, ou recopier le kit dans un autre dépôt.
---

# Appli Android avec le kit

Référence complète : `android/kit/KIT.md` (dépôt `JulesGourio/running-coach`, où le kit est né). Appli modèle :
`running-coach` (`coach/mobile/`, `android/app/`, `tests/test_mobile.py`).

## Principe à garder

- Le téléphone fait tourner le même moteur Python que le PC ; pas de serveur, pas de PC allumé.
- Les écrans sont des fonctions Python qui renvoient des blocs `appkit.ui` ; **aucun Kotlin propre à l'appli**
  hors de `KitConfig` (nom, module, icône, heure de synchro).
- Le fonctionnement du PC ne change pas : les modules réservés au PC (Streamlit, MCP, CLI…) restent, ils ne
  sont simplement pas copiés dans l'APK.

## Nouvelle appli, dans l'ordre

1. Lire le `CLAUDE.md` du dépôt, ses pages (Streamlit ou autre) et ses dépendances : lister ce que le téléphone
   ne peut pas installer (bibliothèques compilées sans version Android : `mcp`/pydantic-core, rpds-py, cffi…).
   Chaquopy fournit numpy 1.26, pandas 2.1, cryptography, lxml… pour Python 3.13.
2. Rendre le moteur portable : imports PC-only isolés, secrets via un `vault` à backends, notifications via
   `notify.set_local`, chemins via une variable d'environnement du dossier de données. Test de portabilité qui
   bloque les imports PC-only dans un sous-processus.
3. Si le moteur utilise une bibliothèque impossible sur Android, écrire un client léger (ex. COROS :
   `coach/sources/coros_light.py`, OAuth + MCP en httpx) avec la même interface, choisi automatiquement.
4. Écrire les écrans (`<package>/mobile/`), une fonction par page, mêmes calculs que le PC, puis le test qui ouvre
   tous les écrans depuis les onglets et les actions principales.
5. Recopier `android/` de running-coach (kit compris) et adapter `app/` (voir KIT.md, étape 4) ; nouvelle clé de
   signature ; recopier `.github/workflows/android.yml` et le job `phone-libs`.
6. Pousser, ouvrir la PR (brouillon), suivre la CI Android jusqu'au vert : c'est la seule compilation possible
   depuis une session cloud (pas de SDK Android ni d'accès à `dl.google.com`/`chaquo.com`).
7. README `android/README.md` : installer l'APK, premier lancement, PC et téléphone.

## Recopier ou mettre à jour le kit dans un autre dépôt

- Le kit doit rester identique partout : `android/kit/` en entier, `KIT_VERSION` dans `appkit/__init__.py`.
- Depuis une session qui a les deux dépôts : copier le dossier, puis lancer les tests des écrans et la CI Android
  du dépôt qui le reçoit.
- Un bloc nouveau se déclare des deux côtés (`appkit/ui.py` et `ui/Blocks.kt`) dans le même commit, et le test
  des écrans vérifie ses clés (`BLOCK_KEYS` de `tests/test_mobile.py`).

## Pièges connus

- `curl_cffi` (et tout ce qui dépend de `cffi`) ne s'installe pas avec Chaquopy : prévoir un repli.
- `actions/setup-python` doit avoir la même version de Python que `chaquopy { version }`.
- `abiFilters` : arm64-v8a suffit pour le Pixel 8a et accélère la construction.
- Les rappels OAuth sur `http://127.0.0.1:…` ne se chargent jamais : la WebView les intercepte (`Result.webauth`).
