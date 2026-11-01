# Note de cadrage — ShopPulse, mission flash data & IA

Mission de 10 jours, traitée comme une mission client : cadrage,
production, livraison, soutenance vidéo. Commanditaire : le Directeur Data
de ShopPulse, marketplace e-commerce d'environ 3 000 vendeurs et 100 000
clients.

## 1. Enjeux métier

La direction exprime trois irritants, que les données confirment :

| Irritant | Constat chiffré | Conséquence |
|---|---|---|
| Données éparpillées, aucune vision consolidée | 9 sources séparées (commandes, clients, vendeurs, produits, paiements, avis, géolocalisation…) | chaque question demande un travail manuel, sans garantie de qualité |
| Marketing sans segmentation | **3 %** des clients repassent commande | les campagnes ciblent tout le monde, le réachat stagne |
| Retards découverts après coup | note moyenne **4,3** à l'heure contre **2,3** en retard ; **79 %** d'avis négatifs au-delà de 7 jours de retard | l'entreprise subit les avis négatifs au lieu de les prévenir |

## 2. Objectifs

**Livrables attendus par le Directeur Data** : une base consolidée et
fiable, des réponses métier lisibles par un non-technicien et un modèle de
prédiction servi par une API conteneurisée.

**Objectifs économiques** visés par ces livrables :

- **réduire les avis négatifs liés aux retards** en repérant les commandes à
  risque assez tôt pour agir (prévenir le client, geste commercial) ;
- **augmenter le réachat** grâce à des campagnes ciblées et chiffrées (gain
  net attendu, hypothèses à valider par test A/B) ;
- **piloter l'activité** avec des indicateurs partagés (chiffre d'affaires,
  commandes, panier moyen, taux de retard, note moyenne) ;
- **réduire le coût d'analyse** : une donnée chargée et contrôlée une seule
  fois, réutilisée par tous.

## 3. Utilisateurs et réponses attendues

| Utilisateur | Question | Réponse livrée |
|---|---|---|
| Direction | Comment se porte l'activité ? | tableau de bord à 5 indicateurs, filtré par période et région |
| Marketing | Qui sont nos clients et comment les cibler ? | segmentation RFM + clustering, 3 personas, 3 campagnes chiffrées |
| Logistique | Quelle commande risque d'arriver en retard ? | modèle de classification servi par l'endpoint `/predict/delay` |
| Service client | Que disent les clients dans leurs avis ? | modèle de sentiment (baseline comparée à un réseau de neurones), endpoint `/predict/sentiment` |
| Équipe data | Comment maintenir le tout ? | pipelines rejouables, tests, image Docker, intégration continue |

## 4. Périmètre

- **Inclus** : les 5 lots (cadrage, données fiables, analyse et marketing,
  modèles, industrialisation) sur le jeu public Olist (≈ 100 000 commandes,
  9 CSV), présenté comme les données de ShopPulse.
- **Exclus** (bonus possibles une fois le socle livré) : Spark sur le
  clickstream REES46, supervision ELK, déploiement cloud, suivi des
  expériences avec MLflow.
- **Contraintes** : projet individuel, 10 jours, données complètes jamais
  versionnées, avis en portugais, aucune donnée dérivée produite à la main.

## 5. Feuille de route

| Étape | Contenu | Livrable |
|---|---|---|
| 1. Cadrage | enjeux, arbitrages, architecture, backlog | `docs/`, backlog GitHub |
| 2. Données fiables | modèle relationnel, ETL rejouable, contrôles qualité, 8 requêtes SQL | base PostgreSQL, rapports qualité |
| 3. Analyse et marketing | EDA, tests statistiques, segmentation, tableau de bord | notebooks, tableau de bord |
| 4. Modèles | variables, modèle de retard, sentiment, audit d'équité, note éthique | notebooks, rapports, modèles |
| 5. Industrialisation | API, package, tests, Docker, CI | API conteneurisée, CI au vert |
| Livraison | README, rétrospective, vidéo | dépôt, vidéo de 10 minutes |

Chaque étape est développée sur sa propre branche et fusionnée dans `main`
après validation.

## 6. Risques et parades

| Risque | Parade |
|---|---|
| Données incohérentes ou incomplètes | contrôles qualité bloquants : le pipeline échoue plutôt que de charger une donnée fausse |
| Fuite d'information dans le modèle de retard | variables calculées uniquement avec ce qui est connu à l'achat, découpage temporel |
| Modèle qui se dégrade dans le temps (dérive) | validation sur une période future, réentraînement régulier, rapports régénérés |
| Biais envers certaines régions | audit d'équité par région, usages autorisés et interdits |
| Données personnelles (RGPD) | minimisation, pseudonymisation, aucun envoi à un service externe |
| Délai très court | périmètre réduit, bonus seulement après le socle, priorité au dépôt exécutable |

## 7. Critères de succès

- Le dépôt se clone et s'exécute en moins de 30 minutes par un tiers.
- Les quatre questions métier reçoivent une réponse chiffrée et lisible.
- Chaque modèle est comparé à une baseline, avec des métriques adaptées.
- Le code est structuré, testé, et la CI est au vert sur `main`.

## 8. Évolutions probables

- **Temps réel** : brancher l'API sur la base pour calculer les variables à
  la volée, et alimenter le modèle de retard avec le suivi des
  transporteurs.
- **MLOps** : réentraînement mensuel planifié, suivi des expériences
  (MLflow), alerte en cas de dérive ou d'écart d'équité.
- **Marketing** : mesurer le gain réel des campagnes par tests A/B, puis
  automatiser la relance de la deuxième commande.
- **Avis** : analyse par thème (livraison, produit, vendeur) et modèle
  pré-entraîné en portugais.
- **Échelle** : déploiement cloud de l'API, traitement Spark du
  clickstream.
