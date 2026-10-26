# Modèle de sentiment des avis

Généré automatiquement par le pipeline d'entraînement le 2026-10-26 00:44. Ne pas modifier à la main. Analyse complète : `notebooks/06_modele_sentiment.ipynb`.

## Données

- train : 25 991 avis, 30,5 % négatifs
- validation : 5 569 avis, 26,9 % négatifs
- test : 5 570 avis, 23,9 % négatifs
- notes de 3 (exclues, analysées à part) : 3 529 avis

## Résultats

Modèle retenu (meilleur PR-AUC de validation, le réseau devant gagner au moins 0.01) : **tfidf_regression_logistique**. Régularisation de la baseline choisie en validation : C = 8.0. Seuils de décision (F1 maximal en validation) : tfidf_regression_logistique = 0.531, reseau_gru = 0.820.

### Validation

| Modèle | pr_auc | roc_auc | precision_negative | recall_negative | f1_negative | macro_f1 | balanced_accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| tfidf_regression_logistique | 0.943 | 0.981 | 0.869 | 0.938 | 0.902 | 0.932 | 0.943 |
| reseau_gru | 0.950 | 0.983 | 0.886 | 0.936 | 0.911 | 0.938 | 0.946 |

### Test

| Modèle | pr_auc | roc_auc | precision_negative | recall_negative | f1_negative | macro_f1 | balanced_accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| tfidf_regression_logistique | 0.953 | 0.985 | 0.863 | 0.938 | 0.899 | 0.932 | 0.945 |
| reseau_gru | 0.955 | 0.984 | 0.889 | 0.930 | 0.909 | 0.940 | 0.947 |

## Mots les plus déterminants (baseline)

| Vers « négatif » | Poids | Vers « positif » | Poids |
|---|---:|---|---:|
| não | 16.12 | parabéns | -8.34 |
| nao | 9.50 | só não | -8.17 |
| não recomendo | 8.87 | lindo | -7.95 |
| péssimo | 7.47 | amei | -7.48 |
| péssima | 6.82 | rápido | -6.96 |
| nem | 6.76 | obrigada | -6.60 |
| não recebi | 6.43 | rápida | -6.39 |
| ruim | 6.36 | perfeito | -6.10 |
| adorei recebi | 5.91 | adorei | -5.98 |
| quebrado | 5.88 | recomendo | -5.72 |
| aguardando | 5.71 | antes | -5.52 |
| inferior | 5.51 | bonito | -5.42 |
| demora | 5.44 | tudo | -5.36 |
| faltando | 5.24 | bem | -4.95 |
| comprei | 5.11 | conforme | -4.81 |
