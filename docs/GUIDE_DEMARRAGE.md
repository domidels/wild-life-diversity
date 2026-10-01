# Guide de démarrage — de zéro à un dashboard en ligne

Ce guide suppose que tu n'as jamais utilisé Databricks ni dbt. Compte une demi-journée pour tout
faire la première fois. Chaque étape se termine par une vérification.

---

## 0. Les concepts en 2 minutes

| Outil | Rôle dans le projet | Analogie |
|---|---|---|
| **Databricks** | L'entrepôt de données dans le cloud : il stocke les fichiers et exécute le SQL. | Le moteur + le disque |
| **Unity Catalog** | L'organisation des données dans Databricks : `catalogue.schéma.table`. | Les dossiers |
| **Volume** | Un dossier de fichiers bruts (CSV) dans Unity Catalog. | Le quai de déchargement |
| **SQL warehouse** | La machine qui exécute les requêtes SQL. | Le processeur |
| **dbt** | Des fichiers `.sql` versionnés qui construisent les tables dans le bon ordre, avec des tests. | La recette |
| **Job** | Une suite de tâches planifiée (ingestion puis dbt) qui tourne dans Databricks, sans ton ordinateur. | Le minuteur |
| **Asset Bundle** | Le fichier [`databricks.yml`](../databricks.yml) qui décrit ce job dans le code, déployé par GitHub. | Le plan de montage |

L'architecture en **médaillon** que dbt construit :

- **bronze** : les CSV bruts lus tels quels (tout en texte) ;
- **silver** : les données nettoyées, typées, enrichies (grille H3, zones brûlées) ;
- **gold** : les tables finales, petites, prêtes pour le dashboard.

---

## 1. Installer l'environnement local

```bash
cd wild-life-diversity
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

✅ `dbt --version` affiche `dbt-databricks`.

## 2. Voir le dashboard tout de suite

```bash
python -m http.server -d web 8000
```

Ouvre http://localhost:8000. `web/data/` contient le dernier export des vraies données.

## 3. Créer un compte Databricks Free Edition

1. Inscris-toi sur https://www.databricks.com/learn/free-edition (gratuit, sans carte bancaire).
2. Dans le menu de gauche, **SQL Editor**, colle le contenu de
   [`databricks/setup.sql`](../databricks/setup.sql) et exécute-le. Cela crée le schéma
   `wildfire_raw` et le volume `landing`.
3. Récupère les identifiants de connexion :
   - **SQL Warehouses** → ton warehouse (« Serverless Starter Warehouse ») → **Connection details** :
     copie *Server hostname* et *HTTP path* ;
   - clique sur ton avatar → **Settings** → **Developer** → **Access tokens** → *Generate new token*.
4. Remplis `.env` : `DATABRICKS_HOST`, `DATABRICKS_HTTP_PATH`, `DATABRICKS_TOKEN`.

✅ Dans **Catalog** → `workspace` → `wildfire_raw`, tu vois le volume `landing`.

> ⚠️ Le fichier `.env` contient un secret : il est dans `.gitignore`, ne le commite jamais.

## 4. Télécharger les données

**Clé NASA FIRMS** : demande-la sur https://firms.modaps.eosdis.nasa.gov/api/map_key/ (email, immédiat),
puis mets-la dans `.env` (`FIRMS_MAP_KEY=`).

**Compte GBIF** : crée-le sur https://www.gbif.org/user/profile (gratuit), puis remplis `GBIF_USER`,
`GBIF_PASSWORD` et `GBIF_EMAIL` dans `.env`. Le script utilise l'API Download : une seule requête
par région, préparée par GBIF en quelques minutes, avec un DOI citable (noté dans `gbif_citations/`).

```bash
python ingestion/gbif.py --regions north_evia     # commence par une seule région
python ingestion/firms.py --regions north_evia
```

Les fichiers arrivent dans `data/raw/gbif/` et `data/raw/firms/`, un CSV par mois. Si le script
s'arrête, relance-le : les mois déjà téléchargés sont sautés.

✅ `ls data/raw/gbif | wc -l` ≈ 50 fichiers pour une région.

Quand ça marche pour une région, lance sans `--regions` : seules les régions actives
(`is_active` dans `regions.csv`) sont téléchargées.

## 5. Envoyer les fichiers dans Databricks

Deux options :

- **Simple (interface)** : Catalog → `wildfire_raw` → `landing` → *Upload to this volume*. Crée les
  dossiers `gbif` et `firms` et dépose les CSV dedans.
- **Scriptée** : `python databricks/upload_to_volume.py` crée le volume et n'envoie que les
  fichiers nouveaux (`--force` pour tout renvoyer).

✅ Dans le SQL Editor :
```sql
select count(*) from read_files('/Volumes/workspace/wildfire_raw/landing/gbif/', format => 'csv', header => true);
```

## 6. Construire les tables avec dbt

```bash
cd dbt
cp profiles.example.yml profiles.yml
set -a; source ../.env; set +a       # charge les variables de .env dans le terminal
dbt debug --profiles-dir .            # ✅ "All checks passed!"
dbt deps --profiles-dir .             # installe dbt_utils
dbt seed --profiles-dir .             # charge regions.csv et fire_episodes.csv
dbt build --profiles-dir .            # construit toutes les tables ET lance tous les tests
```

`dbt build` exécute les modèles dans l'ordre des dépendances (`ref()`), puis leurs tests.
Un test rouge = une hypothèse sur les données qui est fausse : lis le message, c'est souvent la
partie la plus intéressante du projet à raconter en entretien.

Pour visualiser le lignage (très bien pour un portfolio) :
```bash
dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir .
```

✅ Dans Catalog, les schémas `wildfire_bronze`, `wildfire_silver`, `wildfire_gold` existent.

### Lire le projet dbt dans l'ordre

1. [`seeds/regions.csv`](../dbt/seeds/regions.csv) et [`seeds/fire_episodes.csv`](../dbt/seeds/fire_episodes.csv) — les régions (cadres géographiques) et leurs feux. C'est la seule chose à modifier pour étudier un autre feu.
2. [`models/bronze/`](../dbt/models/bronze) — `read_files()` lit les CSV du volume.
3. [`models/staging/`](../dbt/models/staging) — typage, filtres qualité, index H3, fenêtres avant/après de chaque épisode.
4. [`models/intermediate/`](../dbt/models/intermediate) — par épisode : historique de feu par cellule, zones, étiquetage des observations.
5. [`models/marts/`](../dbt/models/marts) — une table par graphique du dashboard, une ligne par épisode.
6. [`dbt_project.yml`](../dbt/dbt_project.yml) — les paramètres (`vars`) : taille des hexagones, seuils, 24 mois « après ».

## 7. Exporter vers le site et publier

```bash
cd ..
python export/export_marts.py         # remplace web/data/*.json par les vraies données
python -m http.server -d web 8000     # vérifie : la date en bas de page est celle du jour
```

Publication sur GitHub (dépôt `domidels/wild-life-diversity`) :

```bash
git add . && git commit -m "Pipeline Databricks + dbt et dashboard"
git push -u origin main
```

Puis sur GitHub : **Settings → Pages → Source : GitHub Actions**. Le workflow
`deploy-pages.yml` publie `web/` à chaque push.

---

## 8. Faire tourner le pipeline dans le cloud (sans ton ordinateur)

Une fois en place, plus rien ne tourne en local :

| Quand | Où | Quoi |
|---|---|---|
| à chaque push sur `main` | GitHub Actions | déploie le job Databricks décrit dans [`databricks.yml`](../databricks.yml) |
| le 1er du mois, 3 h UTC | Databricks (serverless) | télécharge GBIF + FIRMS **directement dans le volume**, puis `dbt build` |
| le 2 du mois, 6 h UTC | GitHub Actions | exporte les tables gold en JSON et republie le dashboard sur GitHub Pages |

**Mise en place (une seule fois) :**

1. **Secrets dans Databricks** (scope `wildfire`) — le job y lit la clé NASA (`firms_map_key`)
   et le compte GBIF (`gbif_user`, `gbif_password`, `gbif_email`). Pour en changer un :
   `databricks secrets put-secret wildfire <nom>`.
2. **Secrets GitHub** — sur le repo : *Settings → Secrets and variables → Actions → New repository secret* :
   `DATABRICKS_HOST` (sans `https://`), `DATABRICKS_HTTP_PATH`, `DATABRICKS_TOKEN` — les mêmes valeurs que `.env`.
3. **GitHub Pages** — *Settings → Pages → Source : GitHub Actions*.
4. Pousse le code. Pour lancer une première exécution tout de suite : onglet *Actions* →
   *Deploy Databricks pipeline* → *Run workflow* → coche « run_now ».

**Choisir les régions** : colonne `is_active` de [`regions.csv`](../dbt/seeds/regions.csv). Seules
les régions actives sont téléchargées (une nouvelle région = plusieurs heures la première fois).

**À surveiller** : le token Databricks expire (90 jours) — pense à le renouveler dans `.env` et
dans les secrets GitHub. Chaque mois, le job re-télécharge les 3 derniers mois, car GBIF et FIRMS
continuent de les compléter.

---

## Dépannage

| Symptôme | Cause probable |
|---|---|
| `h3_longlatash3` inconnu | Le warehouse n'est pas un SQL warehouse (serverless/pro). Utilise le SQL warehouse, pas un cluster classique. |
| `read_files` : chemin introuvable | Les CSV ne sont pas dans `landing/gbif/` et `landing/firms/`, ou `landing_path` dans `dbt_project.yml` diffère. |
| Effet BACI vide (« Not enough observations ») | Une des 4 cases BACI (brûlé/témoin × avant/après) est vide : réduis `min_detections_burned` ou agrandis la bbox de la région. |
| GBIF : « refused the credentials » | `GBIF_USER` / `GBIF_PASSWORD` faux dans `.env` ou dans les secrets Databricks `wildfire/gbif_*`. |
| FIRMS : `Invalid MAP_KEY` | Clé absente de `.env`, ou quota dépassé (5 000 requêtes / 10 min) : attends 10 minutes. |
