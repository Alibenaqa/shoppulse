# Rapport qualité des données

Généré automatiquement par le pipeline le 2026-10-25 18:42. Ne pas modifier à la main.

## Volumes par table

| Table | Avant (RAW) | Après (CORE) |
|---|---:|---:|
| raw.customers → core.customers | 99 441 | 99 441 |
| raw.geolocation → core.geolocation | 1 000 163 | 19 010 |
| raw.order_items → core.order_items | 112 650 | 112 650 |
| raw.order_payments → core.order_payments | 103 886 | 103 886 |
| raw.order_reviews → core.order_reviews | 99 224 | 99 224 |
| raw.orders → core.orders | 99 441 | 99 441 |
| raw.products → core.products | 32 951 | 32 951 |
| raw.sellers → core.sellers | 3 095 | 3 095 |
| raw.category_translation → core.categories | 71 | 73 |

## Contrôles

Nombre de lignes en anomalie. Un contrôle **bloquant** fait échouer le pipeline s'il n'est pas à 0 après nettoyage.

| Contrôle | Description | Avant | Après | Statut |
|---|---|---:|---:|---|
| `doublons_commandes` | Identifiants de commande en double | 0 | 0 | OK (bloquant) |
| `doublons_avis` | Avis en double sur le couple (review_id, order_id) | 0 | 0 | OK (bloquant) |
| `doublons_geolocalisation` | Plusieurs points GPS pour un même code postal (R1) | 981 148 | 0 | OK (bloquant) |
| `geolocalisation_hors_bresil` | Points GPS situés hors du Brésil (R1) | 47 | 0 | OK (bloquant) |
| `categories_sans_traduction` | Produits dont la catégorie n'a pas de traduction (R2) | 13 | 0 | OK (bloquant) |
| `commentaires_vides` | Commentaires d'avis composés uniquement d'espaces (R4) | 9 | 0 | OK (bloquant) |
| `produits_sans_categorie` | Produits sans catégorie (conservés, signalés) | 610 | 610 | signalé |
| `produits_sans_poids` | Produits sans poids ou de poids nul (conservés, signalés) | 6 | 6 | signalé |
| `livrees_sans_date` | Commandes 'delivered' sans date de livraison client | 8 | 8 | signalé |
| `transporteur_avant_achat` | Remise au transporteur datée avant l'achat | 166 | 166 | signalé |
| `commandes_sans_articles` | Commandes sans aucun article | 775 | 775 | signalé |
| `paiements_non_definis` | Paiements de type 'not_defined' | 3 | 3 | signalé |
| `codes_postaux_clients_inconnus` | Clients dont le code postal est absent de la géolocalisation | 278 | 279 | signalé |
