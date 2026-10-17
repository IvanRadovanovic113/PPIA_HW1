# Plan d'anonymisation v2 — PPIA Homework 1

Objectifs et indications d'implémentation pour la suite du projet.
Point de départ : `review-Vermont-anon-v1.json` (841 978 avis, produit par `anonymize_v1.py`).

---

## 0. Vue d'ensemble

| # | Objectif | Statut |
|---|----------|--------|
| 1 | Retirer l'heure, garder le mois | Fait (`anonymize_v2.py`) |
| 2 | k-anonymity sur les quasi-identifiants | À faire (`kanonymity.py`) |
| 3 | Règle des 5 % pour les outliers (top/bottom coding) | À faire |
| 4 | Tests : mesurer quand on perd trop de données | À faire |
| 5 | Tester différentes options et en discuter dans l'étude | À faire |
| 6 | Arrondir les prix + k-anonymity dessus | À faire |
| 7 | Échelle logarithmique pour les prix | À faire |

---

## 1. Retirer l'heure, garder le mois — FAIT

Implémenté dans `anonymize_v2.py` :

- suppression du champ `time` (HH:MM) ;
- généralisation de `date` : `AAAA-MM-JJ` → `AAAA-MM`.

**Pourquoi** : l'heure exacte et le jour sont des quasi-identifiants trop fins.
La précision mois réduit fortement le risque de ré-identification tout en
gardant une analyse temporelle possible (saisonnalité, tendances).

**Piste d'amélioration** : si le mois est encore trop fin, envisager le
trimestre (`AAAA-QT`) ou l'année — à tester comme « option » (objectif 5).

---

## 2. k-anonymity sur les quasi-identifiants

**Définition** : chaque combinaison de quasi-identifiants (QI) doit être
partagée par au moins *k* enregistrements. Un attaquant qui connaît les QI
d'une personne ne peut pas la distinguer de *k−1* autres.

### Quasi-identifiants dans notre dataset

| Champ | Rôle |
|-------|------|
| `date` (mois) | QI — temporel |
| `gmap_id` | QI — le lieu est très identifiant (un lieu peut n'avoir que 1 avis) |
| `category` | QI — liste de catégories, quasi redondante avec `gmap_id` |
| `rating` | QI possible (valeur 1–5) |
| `spent` | QI numérique une fois discrétisé (objectifs 6–7) |
| `state` | Constant (`"Vermont"`), aucun pouvoir identifiant |

### Indications d'implémentation (`kanonymity.py`)

1. **Construire la clé QI** : tuple des champs QI retenus, ex.
   `(date, gmap_id, rating, spent_bucket)`.
2. **Compter** les occurrences de chaque clé (un simple `collections.Counter`
   suffit, pas besoin de pandas sur 840k lignes).
3. **Mesurer k** : histogramme des tailles de groupes → % d'avis vivant dans
   un groupe < k (c'est la métrique clé pour l'objectif 4).
4. **Généralisation itérative** tant que des groupes < k subsistent :
   - `date` : mois → trimestre → année ;
   - `rating` : valeur exacte → {1–2, 3, 4–5} → {pos, nég} → suppression ;
   - `spent` : élargir les paliers (objectif 6) ;
   - `gmap_id` : le plus problématique — remplacer par `category` généralisée,
     ou supprimer.
5. **Deux stratégies à comparer** (objectif 5) :
   - *suppression* : retirer les lignes des groupes < k (simple, mais perte
     de données) ;
   - *généralisation* : coarser les QI jusqu'à atteindre k (préserve les
     lignes, mais perd de la précision).

**Ordre recommandé** : généraliser d'abord les QI les moins utiles à
l'analyse, en dernier les plus utiles.

---

## 3. Règle des 5 % pour les outliers

**Principe** : une valeur partagée par moins de 5 % des enregistrements (ou
située dans les 5 % extrêmes d'une distribution) est trop identifiante →
top-coding / bottom-coding.

### Champs concernés

- `spent` : les montants très rares (ex. 22 000 $ chez un concessionnaire)
  identifient presque individuellement une ligne.
- `resp_delay_hours`, `comment_length`, `pics_num` : idem pour les valeurs
  extrêmes.

### Indications d'implémentation

1. Calculer les quantiles à 5 % et 95 % par champ (globalement, ou **par
   profil de dépense**, car 200 $ est banal au restaurant mais rare à la
   station-service).
2. **Top-coding** : toute valeur > q95 est remplacée par `"> q95"` (ou q95
   lui-même). **Bottom-coding** symétrique pour < q5.
3. En sortie, le champ devient soit une catégorie ordonnée
   (`"95+"`, `"low"`), soit la valeur plafonnée — les deux sont discutables
   (objectif 5 : catégorie = aucune fausse donnée ; plafonnement = garde une
   valeur numérique mais menteuse sur les extrêmes).
4. Attention : pour `spent`, appliquer le top-coding **avant** les paliers de
   l'objectif 6, sinon les outliers cassent l'arrondi.

---

## 4. Tests : détecter quand on perd trop de données

**But** : quantifier le compromis utilité ↔ vie privée à chaque étape et
fournir des chiffres pour l'étude.

### Métriques à implémenter

| Métrique | Signification |
|----------|---------------|
| Taux de lignes supprimées | si stratégie = suppression |
| % de lignes dans un groupe ≥ k | santé de la k-anonymity |
| Erreur moyenne sur `spent` | avant/après arrondi, paliers, log |
| Nombre de mois distincts exploitables | après généralisation date |
| Distribution de `rating` préservée ? | khi² ou simple histogramme |

### Indications d'implémentation

1. Une fonction `report(df_or_counter, k)` qui imprime toutes les métriques
   — appelée après chaque variante pour construire un tableau comparatif.
2. Seuil « alarme » à définir dans l'étude : ex. si > 10 % des lignes
   supprimées ou si l'erreur médiane sur `spent` > 20 %, la variante est
   rejetée.
3. Écrire les résultats dans un CSV (`results.csv`) : une ligne par
   variante testée, colonnes = paramètres + métriques. C'est ce tableau qui
   alimentera la discussion (objectif 5).

---

## 5. Tester différentes options pour l'étude

Grille de variantes à comparer (chaque cellule = une exécution) :

| Axe | Options |
|-----|---------|
| Précision date | mois / trimestre / année |
| k | 3 / 5 / 10 |
| QI retenus | avec ou sans `rating`, avec ou sans `category` |
| `spent` | exact / arrondi / paliers / log-paliers |
| Outliers | avec / sans règle 5 % |
| Stratégie groupes < k | suppression / généralisation |

**Indication d'implémentation** : écrire les variantes comme des fonctions
de configuration (un dict de paramètres par variante), pas du code copié.
Exécuter en boucle, collecter les métriques de l'objectif 4, puis discuter :
courbe utilité ↔ k, coût de chaque axe, recommandation finale.

---

## 6. Arrondir les prix + k-anonymity dessus

**But** : `spent = 1987.31` avec 2 décimales est un identifiant quasi unique.
Un arrondi grossier regroupe les lignes.

### Indications d'implémentation

1. **Arrondi simple** : au palier le plus proche parmi
   `[10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]`, ex.
   `1987.31 → 2000`. Le palier peut croître avec le montant (arrondi
   « significatif », plus lisible que `round(x, -2)` uniforme).
2. **Compter ensuite la k-anonymity sur `spent`** comme pour les autres QI
   (objectif 2) : si un palier reste trop rare, le fusionner avec le voisin.
3. Alternative plus radicale : **bandes ordonnées** plutôt qu'arrondi —
   `0–10`, `10–50`, `50–200`, `200+`… Plus anonyme, moins précis : à tester
   comme variante (objectif 5).
4. Ordre du pipeline : outliers (obj. 3) → arrondi → vérification k.

---

## 7. Échelle logarithmique pour les prix

**Pourquoi** : la dépense est log-normale (le modèle de v1 tire déjà
`median * exp(N(0, spread))`). En échelle linéaire, tout le petit monde est
écrasé vers 0 et les gros montants étirent l'axe. En log, chaque **ordre de
grandeur** a le même poids.

### Indications d'implémentation

1. **Paliers logarithmiques** : arrondir au multiple de puissance le plus
   proche — `spent → 10^round(log10(spent))` donne 1, 10, 100, 1000, 10000 $.
   Plus fin : palier à `±0.5` en log10 → 1, 3, 10, 30, 100, 300…
2. **Variable dérivée** : ajouter `log_spent = round(log10(spent), 1)` en
   QI numérique — 0,1 en log10 = facteur ~1,26, c'est une généralisation
   naturelle.
3. **Visualisation** : tous les histogrammes de `spent` dans l'étude en axe x
   logarithmique (matplotlib : `ax.set_xscale('log')`), sinon les graphiques
   sont illisibles.
4. **Cohérence avec obj. 6** : les paliers log (1, 3, 10, 30…) remplacent
   avantageusement les paliers linéaires pour les montants élevés ; garder
   des paliers fins (1, 5, 10) sous 20 $ où les données sont denses.

---

## Pipeline cible

```
review-Vermont-anon-v1.json
        │  anonymize_v2.py            (obj. 1 : heure retirée, date → mois)
        ▼
review-Vermont-anon-v2.json
        │  1. top/bottom-coding 5 %   (obj. 3 : outliers spent)
        │  2. arrondi / paliers log   (obj. 6–7 : spent discrétisé)
        │  3. généralisation QI       (obj. 2 : date, rating, gmap_id…)
        │  4. k-anonymity check       (obj. 2 : groupes ≥ k)
        ▼
review-Vermont-anon-v3.json  +  results.csv  (obj. 4–5 : métriques, variantes)
```

## Points à discuter dans l'étude

- Perte de données vs valeur de k : où place-t-on le curseur ?
- `gmap_id` est-il conservable, ou faut-il passer aux catégories ?
- Top-coding « catégorie » vs « plafonnement » : fausses valeurs ou perte d'information ?
- Paliers linéaires vs logarithmiques pour `spent` : effet sur l'utilité analytique.
- Limite de la k-anonymity elle-même : vulnérable aux attaques par
  similarité (l-diversity, t-closeness) — mention à minima.
