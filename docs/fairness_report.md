# Audit d'équité du modèle de retard par région

Généré automatiquement par le pipeline d'entraînement le 2026-10-26 00:12. Ne pas modifier à la main. Analyse et recommandations : `notebooks/05_audit_equite.ipynb` et `docs/ethique.md`.

Indicateurs : taux de retard réel, taux de signalement, rappel (part des retards signalés), taux de fausses alertes (part des commandes à l'heure signalées), précision, ROC-AUC. Entre crochets : intervalle de confiance à 95 % (bootstrap, 500 tirages). Référence : Sudeste. ⚠️ = ratio de signalement hors [0.8 ; 1.25] (règle des 4/5) ou écart de rappel / fausses alertes > 10 points.

## Validation (06/2017 → 05/2018), seuil unique

| Région | Commandes | Retards | Taux de retard | Signalées | Rappel | Fausses alertes | Précision | ROC-AUC | Ratio de signalement | Alerte |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Centro-Oeste | 3842 | 312 | 8.1 % | 25.0 % [24–26] | 24.7 % [20–30] | 25.0 % [24–26] | 8.0 % | 0.59 [0.56–0.61] | 1.51 | ⚠️ |
| Nordeste | 6086 | 970 | 15.9 % | 52.8 % [52–54] | 67.8 % [65–71] | 49.9 % [49–51] | 20.5 % | 0.61 [0.59–0.63] | 3.18 | ⚠️ |
| Norte | 1144 | 134 | 11.7 % | 22.3 % [20–25] | 42.5 % [34–51] | 19.6 % [17–23] | 22.4 % | 0.70 [0.66–0.74] | 1.35 | ⚠️ |
| Sudeste | 44303 | 3233 | 7.3 % | 16.6 % [16–17] | 42.5 % [41–44] | 14.5 % [14–15] | 18.7 % | 0.72 [0.71–0.73] | 1.00 |  |
| Sul | 9290 | 702 | 7.6 % | 25.4 % [25–26] | 39.7 % [36–43] | 24.2 % [23–25] | 11.8 % | 0.64 [0.62–0.66] | 1.53 | ⚠️ |
| Toutes | 64665 | 5351 | 8.3 % | 21.8 % [22–22] | 45.7 % [44–47] | 19.7 % [19–20] | 17.3 % | 0.70 [0.70–0.71] |  |  |

## Test (06/2018 → 08/2018), seuil unique

| Région | Commandes | Retards | Taux de retard | Signalées | Rappel | Fausses alertes | Précision | ROC-AUC | Ratio de signalement | Alerte |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Centro-Oeste | 1066 | 36 | 3.4 % | 9.6 % [8–11] | 25.0 % [11–41] | 9.0 % [7–11] | 8.8 % | 0.74 [0.67–0.82] | 1.02 | ⚠️ |
| Nordeste | 1640 | 78 | 4.8 % | 56.4 % [54–59] | 73.1 % [62–84] | 55.6 % [53–58] | 6.2 % | 0.64 [0.57–0.71] | 6.00 | ⚠️ |
| Norte | 301 | 6 | 2.0 % | 36.5 % [32–42] | 66.7 % [20–100] | 35.9 % [31–41] | 3.6 % | 0.71 [0.49–0.87] | 3.89 | ⚠️ |
| Sudeste | 13143 | 508 | 3.9 % | 9.4 % [9–10] | 13.4 % [10–17] | 9.2 % [9–10] | 5.5 % | 0.66 [0.64–0.68] | 1.00 |  |
| Sul | 2453 | 44 | 1.8 % | 6.2 % [5–7] | 13.6 % [5–24] | 6.0 % [5–7] | 4.0 % | 0.65 [0.57–0.72] | 0.65 | ⚠️ |
| Toutes | 18603 | 672 | 3.6 % | 13.6 % [13–14] | 21.4 % [18–25] | 13.3 % [13–14] | 5.7 % | 0.65 [0.63–0.67] |  |  |

## Test (06/2018 → 08/2018), seuils par région

| Région | Commandes | Retards | Taux de retard | Signalées | Rappel | Fausses alertes | Précision | ROC-AUC | Ratio de signalement | Alerte |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Centro-Oeste | 1066 | 36 | 3.4 % | 20.9 % [19–23] | 44.4 % [29–61] | 20.1 % [18–23] | 7.2 % | 0.74 [0.67–0.82] | 1.79 | ⚠️ |
| Nordeste | 1640 | 78 | 4.8 % | 36.2 % [34–39] | 57.7 % [47–70] | 35.1 % [33–38] | 7.6 % | 0.64 [0.57–0.71] | 3.10 | ⚠️ |
| Norte | 301 | 6 | 2.0 % | 40.9 % [36–47] | 66.7 % [20–100] | 40.3 % [35–46] | 3.3 % | 0.71 [0.49–0.87] | 3.50 | ⚠️ |
| Sudeste | 13143 | 508 | 3.9 % | 11.7 % [11–12] | 18.7 % [15–22] | 11.4 % [11–12] | 6.2 % | 0.66 [0.64–0.68] | 1.00 |  |
| Sul | 2453 | 44 | 1.8 % | 8.9 % [8–10] | 15.9 % [7–27] | 8.8 % [8–10] | 3.2 % | 0.65 [0.57–0.72] | 0.76 | ⚠️ |
| Toutes | 18603 | 672 | 3.6 % | 14.5 % [14–15] | 24.9 % [22–28] | 14.1 % [14–15] | 6.2 % | 0.65 [0.63–0.67] |  |  |
