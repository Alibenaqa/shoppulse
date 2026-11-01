# Arbitrage technique — orchestration : Prefect ou Airflow ?

## Le besoin

Le pipeline de données doit enchaîner plusieurs étapes (vérification des
sources, chargement RAW, transformation CORE, contrôles qualité, rapports,
analyses SQL, segmentation), être **rejouable**, **s'arrêter** si un
contrôle bloquant échoue, **relancer** une étape en cas d'erreur
passagère et tracer chaque exécution. Un second pipeline entraîne les
modèles. Le volume est modeste (≈ 100 000 commandes, un traitement par
jour au plus) et la mission dure 10 jours, pour une seule personne.

## Les options

- **Apache Airflow** : le standard historique de l'orchestration. Les flux
  (DAG) sont écrits en Python, mais l'outil fonctionne comme une plateforme
  : un planificateur, une base de métadonnées, un serveur web et un
  exécuteur, à déployer et à maintenir.
- **Prefect** : orchestrateur plus récent. Les flux sont des fonctions
  Python décorées (`@flow`, `@task`) qui s'exécutent directement avec
  `python pipelines/olist_flow.py` ; un serveur temporaire démarre tout seul
  pour l'historique et l'interface, un serveur permanent reste optionnel.

## Comparaison selon les quatre critères

| Critère | Airflow | Prefect |
|---|---|---|
| **Coût** | gratuit (Apache 2.0), mais plusieurs services à faire tourner en permanence (au moins planificateur, base de métadonnées et serveur web) : coût d'infrastructure et de maintenance | gratuit (Apache 2.0) ; rien à faire tourner en permanence pour notre usage, offre cloud optionnelle |
| **Délai** | installation et configuration d'une plateforme avant d'écrire la première tâche ; modèle de DAG à apprendre | une installation `pip`, puis du Python ordinaire : le premier flux a tourné le jour même |
| **Performance** | très solide à grande échelle (exécuteurs Celery ou Kubernetes) ; démarrage lent pour des flux courts | largement suffisante pour quelques flux quotidiens ; flux complet ETL ≈ 1 min, serveur temporaire prêt en ≈ 4 s |
| **Pérennité** | projet de la fondation Apache, très répandu, compétence la plus demandée sur le marché | entreprise éditrice, communauté active mais plus petite ; dépendance à l'évolution de l'API (passage de la version 2 à la 3) |

## Grille de décision

Notes de 1 (défavorable) à 5 (favorable), pondérées selon les priorités de
la mission : le délai et le coût priment sur une montée en charge qui
n'existe pas.

| Critère | Poids | Airflow | Prefect |
|---|---:|---:|---:|
| Coût | 25 % | 2 | 5 |
| Délai | 35 % | 2 | 5 |
| Performance | 15 % | 5 | 4 |
| Pérennité | 25 % | 5 | 3 |
| **Score pondéré** | | **3,20** | **4,35** |

## Décision

**Prefect**, parce que le délai et le coût dominent : un flux Prefect est du
Python standard, testable comme le reste du code, lançable en une commande
et sans infrastructure. Les fonctionnalités dont nous avions besoin sont
toutes présentes et utilisées : étapes nommées, nouvelles tentatives
automatiques (`retries`), arrêt du flux si un contrôle bloquant échoue,
historique des exécutions.

**Ce que nous acceptons** : un outil moins standard qu'Airflow sur le
marché, et un risque d'évolution de son API.

**Ce qui nous ferait changer d'avis** : des dizaines de flux, une équipe
data dédiée ou une plateforme Airflow déjà en place dans l'entreprise. La
migration resterait limitée : chaque tâche Prefect ne fait qu'appeler une
classe du package `shoppulse`, qu'un DAG Airflow appellerait de la même
façon.

## Même méthode, autre choix : Streamlit plutôt que Metabase

| Critère | Metabase | Streamlit | Choix |
|---|---|---|---|
| Coût | gratuit, mais un serveur Java et sa propre base à héberger | gratuit, une application Python | Streamlit |
| Délai | tableaux sans code, mais configuration et modèle de données à recréer dans l'outil | même langage et mêmes classes que le reste du projet (indicateurs testés en Python) | Streamlit |
| Performance | très bonne pour l'exploration libre par des utilisateurs métier | suffisante pour une page de 5 indicateurs avec cache | égalité |
| Pérennité | outil BI reconnu, gestion des droits | code versionné et testé dans le dépôt ; outil demandé dans le cadre de la formation | Streamlit |

Metabase deviendrait le meilleur choix si de nombreux utilisateurs métier
devaient créer eux-mêmes leurs propres tableaux.
