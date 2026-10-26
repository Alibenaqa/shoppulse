# Modèle de retard de livraison

Généré automatiquement par le pipeline d'entraînement le 2026-10-25 19:31. Ne pas modifier à la main.

## Données

- Apprentissage (janv. 2017 → mai 2018) : 77 600 commandes, 7,6 % de retards
- Test (juin → août 2018) : 18 603 commandes, 3,6 % de retards

## Validation croisée temporelle (5 plis)

Moyenne ± écart-type sur les plis. Modèle retenu : le meilleur PR-AUC moyen.

| Modèle | PR-AUC | ROC-AUC | Rappel top 10 % | Précision top 10 % |
|---|---:|---:|---:|---:|
| gradient_boosting | 0.177 ± 0.110 | 0.700 ± 0.037 | 0.271 ± 0.048 | 0.217 ± 0.142 |
| regression_logistique | 0.159 ± 0.108 | 0.658 ± 0.119 | 0.250 ± 0.080 | 0.196 ± 0.135 |
| regle_taux_par_etat | 0.133 ± 0.083 | 0.639 ± 0.017 | 0.176 ± 0.038 | 0.145 ± 0.111 |
| baseline_taux_moyen | 0.083 ± 0.056 | 0.500 ± 0.000 | 0.096 ± 0.005 | 0.080 ± 0.055 |

## Test (période jamais vue)

Modèle retenu : **gradient_boosting**, seuil de décision 0.664 (F1 maximal en validation).

| Modèle | PR-AUC | ROC-AUC | Rappel top 10 % | Précision top 10 % | Précision | Rappel | F1 | Exactitude équilibrée | Part signalée |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| regression_logistique | 0.075 | 0.709 | 0.216 | 0.078 |  |  |  |  |  |
| gradient_boosting | 0.060 | 0.651 | 0.174 | 0.063 | 0.057 | 0.214 | 0.090 | 0.541 | 0.136 |
| regle_taux_par_etat | 0.037 | 0.455 | 0.095 | 0.034 |  |  |  |  |  |
| baseline_taux_moyen | 0.036 | 0.500 | 0.103 | 0.037 |  |  |  |  |  |

## Importance des variables (permutation sur le test)

Baisse de PR-AUC quand on mélange la variable. Une valeur négative signifie que la relation apprise ne tient plus sur la période de test.

| Variable | Importance | Écart-type |
|---|---:|---:|
| `promise_slack_days` | 0.0189 | 0.0014 |
| `estimated_days` | 0.0089 | 0.0006 |
| `seller_dispatch_days` | 0.0032 | 0.0006 |
| `customer_state` | 0.0031 | 0.0020 |
| `platform_delivery_days_14d` | 0.0025 | 0.0006 |
| `seller_past_orders` | 0.0011 | 0.0003 |
| `n_items` | 0.0010 | 0.0004 |
| `order_value` | 0.0010 | 0.0003 |
| `seller_past_late_rate` | 0.0001 | 0.0004 |
| `total_weight_g` | -0.0001 | 0.0003 |
| `platform_orders_7d` | -0.0003 | 0.0010 |
| `same_state` | -0.0006 | 0.0004 |
| `route_expected_days` | -0.0026 | 0.0027 |
| `freight_value` | -0.0028 | 0.0013 |
| `distance_km` | -0.0072 | 0.0014 |
