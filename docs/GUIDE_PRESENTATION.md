# Comment présenter ces données

Le dashboard n'est pas une collection de graphiques : c'est **un raisonnement en 7 étapes**. Chaque
section répond à une question et prépare la suivante. Ce guide explique pourquoi chaque choix a été
fait, pour que tu puisses le défendre en entretien et l'adapter.

---

## Le piège principal : GBIF mesure les observateurs autant que la nature

GBIF agrège surtout des observations **opportunistes** (iNaturalist, eBird…). Le nombre
d'observations dépend de :

- la croissance des applis (souvent +20 à +40 % par an) ;
- l'accès : une zone brûlée est souvent fermée pendant des semaines ;
- la curiosité : après un feu médiatisé, des naturalistes viennent *exprès* voir ce qui repousse ;
- la saison, le COVID (2020 !), les campagnes de science participative.

**Conséquence : ne jamais montrer « nombre d'observations avant/après » seul comme un résultat
biologique.** Tout le design du dashboard sert à neutraliser ce biais :

1. **Une zone témoin** (non brûlée, même région, même période) subit les mêmes biais d'effort.
2. **Le ratio BACI** divise le changement de la zone brûlée par celui du témoin.
3. **Des parts** (fréquences relatives) plutôt que des comptages bruts.
4. **La raréfaction** : comparer la richesse sur des échantillons de même taille.

**Un feu récent (ex. Gironde 2026) ajoute deux pièges :**

- *la saison* : 2 mois « après » (août-septembre) ne se comparent pas à 2 ans « avant » (toutes
  saisons). Le pipeline compare donc automatiquement à la même saison des années précédentes ;
- *le délai de publication* : les observations récentes arrivent dans GBIF avec des semaines, voire
  des années de retard (eBird publie une fois par an, certains programmes français bien plus tard).
  En Gironde, août 2022 compte 6 080 observations (eBird, Pl@ntNet, INPN…) contre 1 036 en août 2025
  (iNaturalist et Observation.org seulement). Le pipeline ne compare donc que les **jeux de données
  déjà présents après le feu** : mêmes sources avant et après. Le dashboard affiche « Too early » tant qu'une
  case BACI a moins de 100 observations. Montrer cette prudence est un point fort, pas une faiblesse.

Si tu ne retiens qu'une phrase pour un entretien : *« J'ai séparé l'effet du feu de l'effet
observateur grâce à un design BACI avec zone témoin. »*

---

## L'arc narratif, section par section

### 1. Le feu — « De quoi parle-t-on ? »
- **4 KPI** : surface brûlée, détections, observations, espèces. Ils posent l'échelle, pas de conclusion.
- **Carte** : peu de couleurs — brûlé en **rouge** (vif pour le feu le plus récent, foncé pour les
  plus anciens : la Gironde montre ainsi 2022 et 2026 sur la même carte), témoin (bleu), exclu (gris). Le lecteur doit
  comprendre la comparaison *spatialement* avant de voir un chiffre.
- Pourquoi des hexagones H3 ? Surfaces égales partout, voisinage simple (les anneaux de
  la zone tampon), et fonctions natives dans Databricks.

### 2. L'effort — « Peut-on comparer ? »
- Section **avant** les résultats, volontairement : c'est ce qui rend le reste crédible.
- **Indexé (avant = 100) par défaut** : chaque zone est ramenée à sa propre moyenne pré-feu, donc les
  deux courbes sont comparables même si le témoin a 10× plus d'observations.
- Le **creux de la courbe rouge pendant et juste après le feu** est attendu (accès fermé) : le dire explicitement.
- Les détections satellites sont dans un **graphique séparé** avec le même axe du temps —
  **jamais de double axe Y** (deux échelles sur un même graphique font dire n'importe quoi à la courbe).

### 3. Le verdict — « La zone brûlée a-t-elle perdu des espèces ? »
- **Un seul grand chiffre** : l'effet BACI sur la richesse raréfiée. C'est la réponse à la question
  du projet ; il doit être le plus visible de la page.
- Les **slope charts** avant → après montrent d'où vient ce chiffre : le lecteur voit les deux pentes
  et comprend le ratio sans formule.
- Les mini-effets (observations, richesse brute) montrent *pourquoi* on raréfie : la richesse
  brute suit l'effort, la raréfiée non.
- Formulation : « −11 % **par rapport à la trajectoire du témoin** », pas « −11 % d'espèces ».

### 4. Les espèces — « Lesquelles ? »
- **Barres divergentes** centrées sur « same » : à droite relativement plus fréquente en zone brûlée,
  à gauche moins. Échelle log2 affichée en ×2, ×4, ×1/2 : plus lisible qu'un logarithme.
- Seulement le **top 10 de chaque côté** + un filtre par groupe + le tableau complet dans « Show as table ».
- Les barres sont neutres (gris) : le rouge et le bleu sont réservés aux zones, **une couleur garde
  le même sens partout sur la page**.
- **« Nouvelles dans la région »** : à présenter comme des *pistes* (plantes pionnières après le feu ?
  espèce invasive ? ou simplement un nouvel observateur spécialisé ?).

### 5. La composition — « L'écosystème a-t-il changé de visage ? »
- **Dumbbells** (rond vide = avant, rond plein = après) pour chaque groupe, brûlé et témoin côte à côte.
- Règle de lecture à écrire sous le titre : *un déplacement dans la zone brûlée seulement = effet
  possible du feu ; dans les deux zones = changement de pratique d'observation.*

### 6. Les déplacements de latitude — « Les observations ont-elles bougé ? »
- Point + moustaches à ±2 erreurs standard ; point plein = décalage significatif.
- **À l'échelle d'une région, c'est fragile** : le « déplacement » reflète surtout l'endroit où les
  gens sont allés. Le dire dans le texte. L'analyse devient vraiment intéressante à l'échelle
  mondiale (voir « Pour aller plus loin »).

### 7. Méthode et limites
- Un portfolio qui **nomme ses limites** inspire plus confiance qu'un portfolio qui affiche des
  certitudes. C'est un signal de maturité pour un recruteur data.

---

## Règles de présentation appliquées (réutilisables partout)

| Règle | Dans ce dashboard |
|---|---|
| Une couleur = un sens, sur toute la page | Rouge = brûlé (vif = feu récent, foncé = ancien), bleu = témoin, gris = exclu / neutre |
| Jamais de double axe Y | Détections de feu dans un graphique à part |
| Le titre de section est une question | « Did the burned area lose species? » |
| Un seul chiffre héros par vue | L'effet BACI de la section 3 |
| Étiqueter peu, mais directement | Fin de courbe (« Burned », « Control »), pas un chiffre par point |
| Toujours une légende si ≥ 2 séries | Légende au-dessus de chaque graphique |
| Info-bulle au survol + vue tableau | Tous les graphiques ; tableau pour les espèces |
| Mode sombre choisi, pas inversé | Tons ajustés pour le fond sombre, bouton « Theme » |
| Le vocabulaire reste honnête | « observations », « plus fréquente », jamais « population » ou « abondance » |

---

## Comment en parler (README, LinkedIn, entretien)

**Pitch en 30 secondes :**
> J'ai construit une plateforme de données sur Databricks et dbt qui croise 4 ans de détections
> satellites de la NASA avec les observations d'espèces de GBIF autour de quatre grands incendies.
> Le point difficile était le biais d'observation ; je l'ai traité avec un design BACI et une
> richesse raréfiée, le tout testé par dbt à chaque couche, orchestré par un job Databricks mensuel
> et publié automatiquement sur un dashboard interactif.

**Ce qu'un recruteur data engineer regardera :** l'architecture médaillon, les tests dbt, la
reproductibilité (seed unique, `vars`, scripts idempotents), la CI.
**Ce qu'un recruteur data analyst / scientist regardera :** le traitement du biais, le choix des
graphiques, l'honnêteté des conclusions.

---

## Pour aller plus loin (idées d'évolution)

1. **Déplacement mondial des espèces** : pour les espèces très observées, latitude moyenne par année
   sur 15 ans à l'échelle du globe (via l'API Download de GBIF) → une section « climate shift ».
2. **Détection automatique des grands feux** : clusteriser les détections FIRMS (cellules H3 voisines,
   jours consécutifs) pour trouver les événements au lieu de les choisir à la main.
3. **Citations** : afficher sur le dashboard les DOI des téléchargements GBIF (`gbif_citations/`),
   comme l'exige la licence des jeux de données.
4. **Incrémental** : modèles dbt `incremental` pour ne retraiter que les nouveaux mois.
5. **Durée de récupération** : suivre l'effet BACI mois par mois après le feu pour estimer quand la
   zone brûlée rejoint le témoin.
