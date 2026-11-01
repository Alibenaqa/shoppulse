# Rétrospective — ShopPulse

Période de travail : du 25 octobre au 2 novembre 2026.

## Feuille de route et réalité

| Étape prévue (note de cadrage) | Réalisé | Écart |
|---|---|---|
| 1. Cadrage, arbitrages, backlog — en premier | choix d'outils faits dès le départ, mais documents, backlog et points d'étape rédigés à la fin (1er novembre) | **écart majeur** : le cadrage écrit n'a pas guidé le travail, il le résume |
| 2. Données fiables | 25 octobre | conforme |
| 3. Analyse et marketing | 25 octobre | conforme |
| 4. Modèles | 25-26 octobre | conforme ; modèle de retard moins bon que prévu sur la période récente |
| 5. Industrialisation | 26 octobre | conforme ; tests et CI ajoutés après le code plutôt qu'au fil de l'eau |
| Livraison : README, slides, vidéo | README le 26 octobre (installation vérifiée sur un clone neuf), puis slides et vidéo | conforme |
| Commits quotidiens | travail concentré sur trois journées (25 et 26 octobre, 1er novembre) | **non respecté** |

Les cinq lots sont livrés ; les bonus (cloud, Spark, ELK, MLflow) ne l'ont
pas été.

## Ce qui a bien marché

- **Des données fiables d'abord** : couches `raw` → `core`, contrôles
  bloquants et pipeline rejouable. Tout le reste (analyses, modèles,
  tableau de bord) s'est appuyé sur une base contrôlée.
- **La rigueur méthodologique** : découpage temporel, variables sans fuite
  d'information, choix des modèles en validation croisée et non sur le
  test, règle de choix du modèle de sentiment fixée avant de voir les
  résultats. Les résultats sont moins flatteurs, mais honnêtes.
- **Les tests et la vérification ont trouvé de vrais bugs** avant le rendu :
  - un tableau de volumes décalé dans le premier rapport qualité ;
  - des résultats qui variaient d'une exécution à l'autre (ordre des
    commandes ex aequo, calculs parallèles), corrigés pour rendre les
    pipelines exactement reproductibles ;
  - une précision de dates différente qui faisait planter l'API ;
  - une dépendance (`pyarrow`) absente de l'image Docker, et un modèle
    illisible qui empêchait toute l'API de démarrer.
- **L'installation vérifiée sur un clone neuf** : le README a été rejoué tel
  quel, de bout en bout.

## Ce qui a moins bien marché

- **Le modèle de retard** : correct en validation, nettement moins bon sur
  l'été 2018, parce qu'Olist a changé sa politique de délais promis. Cette
  dérive a été comprise et documentée, mais pas corrigée.
- **Le biais régional** : le modèle signale beaucoup plus les commandes du
  Nordeste ; les seuils par région réduisent l'écart sans le supprimer.
- **Plusieurs textes de notebooks** ont dû être corrigés pour coller aux
  chiffres réellement obtenus.
- **Le suivi de projet** : backlog et points d'étape tenus a posteriori,
  commits concentrés sur peu de jours.

## Ce que je referais autrement

1. **Ouvrir le backlog et écrire la note de cadrage dès le premier jour**,
   puis tenir les points d'étape au moment où ils ont lieu.
2. **Committer chaque jour** et passer par des pull requests, pour garder une
   trace de relecture de chaque branche.
3. **Écrire les tests en même temps que le code**, et brancher la CI dès le
   premier lot.
4. **Valider les modèles sur la période la plus récente dès le début**, pour
   détecter la dérive plus tôt, et prévoir un suivi automatique (MLflow,
   alerte sur la performance et l'équité).
5. **Générer les chiffres cités dans les textes** directement depuis le
   code, plutôt que de les recopier.
