# Note éthique — ShopPulse

Périmètre : modèles de retard et de sentiment, segmentation clients, sur le
jeu public Olist (≈ 100 000 commandes, Brésil, 2016-2018).

## 1. Biais possibles des modèles par région

- **Modèle de retard** (`docs/fairness_report.md`, notebook 05) : il
  signale selon la région plus que selon le risque réel. Été 2018 : 56 % des
  commandes du Nordeste signalées contre 9 % dans le Sudeste, pour des taux
  de retard proches (4,8 % et 3,9 %) ; seulement 13 % des retards du Sudeste
  et du Sul détectés. Causes : un passé où le Nordeste avait deux fois plus
  de retards, une dérive mi-2018, peu de données hors du Sudeste (68 % des
  commandes). **Retirer l'état du client ne corrige rien** (la distance et le
  trajet servent de proxys) ; des **seuils par région** recalibrés à chaque
  entraînement divisent l'écart par deux et améliorent le rappel global
  (21 % → 25 %). Le Norte et le Nordeste étant en moyenne les régions les
  plus pauvres, ce modèle ne doit jamais servir à les pénaliser.
- **Modèle de sentiment** : pas d'écart notable par région (erreurs de 3,5 %
  à 6,3 %, intervalles de confiance qui se recouvrent) ; rappel un peu plus
  faible dans le Nordeste (90 % contre 94 %), à surveiller. Il ne connaît
  que le portugais courant : argot et fautes peuvent le tromper.

## 2. Conformité RGPD des données clients

- **Nature des données** : identifiants hachés, ni nom ni e-mail, code
  postal réduit à son préfixe, noms d'entreprises des avis remplacés par
  des maisons de *Game of Thrones*. Croisés (client, code postal, dates),
  ces éléments permettent une réidentification : données **pseudonymisées,
  donc personnelles** au sens du RGPD (et de la LGPD brésilienne).
- **Déjà appliqué** : minimisation (seules les colonnes utiles ; modèles au
  niveau de l'état, jamais de l'adresse ; agrégats seulement dans le tableau
  de bord) ; données complètes jamais versionnées (échantillons < 1 Mo) ;
  secrets dans un `.env` hors de Git ; aucun avis envoyé à un service de
  traduction externe (entraînement sur place).
- **Avant une mise en production réelle** : registre des traitements ; base
  légale de l'intérêt légitime ; information des clients et **droit
  d'opposition au profilage marketing** (art. 21) ; prospection par e-mail
  limitée aux clients existants, avec désinscription ; conservation limitée
  (3 ans après le dernier achat, recommandation CNIL) ; **analyse d'impact
  (AIPD, art. 35)**, car on note des personnes à grande échelle ; masquage
  des téléphones et e-mails écrits dans les avis.

## 3. Limites d'usage des prédictions

Les modèles **aident à décider, ils ne décident pas** : aucune décision
importante pour un client ne doit reposer uniquement sur eux (art. 22).

| Modèle | Usage autorisé | Usage interdit |
|---|---|---|
| Retard | surveiller, prévenir le client, geste commercial | allonger le délai promis, augmenter les frais, refuser une commande |
| Sentiment | prioriser les réponses, suivre les thèmes | supprimer ou masquer des avis négatifs, évaluer un conseiller |
| Segmentation | campagnes avec désinscription, tests A/B | prix selon la région, cibler un client opposé à la prospection |

- **Fiabilité** : retard modeste (1,6 fois mieux que le hasard sur l'été
  2018) et sensible aux changements de politique de promesse ; sentiment à
  94 % de rappel mais appris sur des notes parfois incohérentes avec le
  texte ; gains des campagnes à valider par test A/B.
- **Suivi** : réentraînement mensuel ; rapports de performance et d'équité
  régénérés à chaque fois ; un ratio de signalement hors de la règle des
  4/5 bloque la mise en service jusqu'à un examen humain.
