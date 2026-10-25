# Analyses SQL

Généré automatiquement par le pipeline le 2026-10-25 18:46 à partir des fichiers de `sql/queries/`. Ne pas modifier à la main.

## Chiffre d'affaires mensuel et croissance

- **Question** : Comment évolue l'activité mois après mois ?
- **Destinataire** : Direction
- **Techniques** : agrégat (SUM, COUNT DISTINCT), CTE, fonction de fenêtre LAG
- **Lecture** : l'activité a été multipliée par 8 entre janvier 2017 et 2018, avec un pic au Black Friday (novembre 2017, +53 %), puis un plateau autour de 1 M par mois en 2018. Panier moyen stable (~160).
- **Fichier** : `sql/queries/01_ca_mensuel.sql`

| month | orders | revenue | avg_basket | growth_pct |
|---|---|---|---|---|
| 2017-01-01 | 787 | 136943 | 174.01 |  |
| 2017-02-01 | 1718 | 283562 | 165.05 | 107.1 |
| 2017-03-01 | 2617 | 425618 | 162.64 | 50.1 |
| 2017-04-01 | 2377 | 405849 | 170.74 | -4.6 |
| 2017-05-01 | 3640 | 582711 | 160.09 | 43.6 |
| 2017-06-01 | 3205 | 499652 | 155.90 | -14.3 |
| 2017-07-01 | 3946 | 578754 | 146.67 | 15.8 |
| 2017-08-01 | 4272 | 661904 | 154.94 | 14.4 |
| 2017-09-01 | 4227 | 717103 | 169.65 | 8.3 |
| 2017-10-01 | 4547 | 764756 | 168.19 | 6.6 |
| 2017-11-01 | 7421 | 1172192 | 157.96 | 53.3 |
| 2017-12-01 | 5618 | 861527 | 153.35 | -26.5 |
| 2018-01-01 | 7187 | 1101920 | 153.32 | 27.9 |
| 2018-02-01 | 6624 | 979486 | 147.87 | -11.1 |
| 2018-03-01 | 7168 | 1152657 | 160.81 | 17.7 |
| 2018-04-01 | 6919 | 1156249 | 167.11 | 0.3 |
| 2018-05-01 | 6833 | 1145686 | 167.67 | -0.9 |
| 2018-06-01 | 6145 | 1020382 | 166.05 | -10.9 |
| 2018-07-01 | 6233 | 1039784 | 166.82 | 1.9 |
| 2018-08-01 | 6421 | 996974 | 155.27 | -4.1 |

## Top 10 des catégories par chiffre d'affaires

- **Question** : Quelles catégories portent le chiffre d'affaires ?
- **Destinataire** : Direction, Marketing
- **Techniques** : jointure multiple (4 tables), agrégat, fonction de fenêtre SUM() OVER () pour la part du CA total
- **Lecture** : aucune catégorie ne dépasse 10 % du CA ; les 10 premières en font environ 62 %. Santé-beauté et montres-cadeaux mènent.
- **Fichier** : `sql/queries/02_top_categories.sql`

| category | orders | revenue | revenue_share_pct | avg_price |
|---|---|---|---|---|
| health_beauty | 8800 | 1255695 | 9.3 | 130.34 |
| watches_gifts | 5604 | 1198185 | 8.9 | 200.70 |
| bed_bath_table | 9399 | 1035964 | 7.7 | 93.36 |
| sports_leisure | 7673 | 979741 | 7.3 | 114.06 |
| computers_accessories | 6654 | 904322 | 6.7 | 116.22 |
| furniture_decor | 6425 | 727465 | 5.4 | 87.67 |
| housewares | 5847 | 626826 | 4.6 | 90.65 |
| cool_stuff | 3616 | 620770 | 4.6 | 164.27 |
| auto | 3872 | 586586 | 4.3 | 139.53 |
| garden_tools | 3505 | 481010 | 3.6 | 111.14 |

## Taux de retard de livraison par état

- **Question** : Où les commandes arrivent-elles le plus souvent en retard ?
- **Destinataire** : Logistique
- **Techniques** : jointure, agrégat conditionnel (FILTER), HAVING
- **Lecture** : les états du Nord-Est (MA, CE, BA) et RJ dépassent 12 % de retards, contre 4,5 % à SP où se trouvent la plupart des vendeurs.
- **Fichier** : `sql/queries/03_retards_par_etat.sql`

| state | delivered_orders | late_orders | late_rate_pct | avg_delivery_days |
|---|---|---|---|---|
| MA | 717 | 125 | 17.4 | 21.5 |
| CE | 1279 | 176 | 13.8 | 21.2 |
| BA | 3256 | 396 | 12.2 | 19.3 |
| RJ | 12350 | 1495 | 12.1 | 15.2 |
| PA | 946 | 106 | 11.2 | 23.7 |
| ES | 1995 | 214 | 10.7 | 15.7 |
| PB | 517 | 54 | 10.4 | 20.4 |
| MS | 701 | 68 | 9.7 | 15.5 |
| PE | 1593 | 153 | 9.6 | 18.4 |
| SC | 3546 | 291 | 8.2 | 14.9 |
| GO | 1957 | 128 | 6.5 | 15.5 |
| RS | 5344 | 325 | 6.1 | 15.2 |
| MT | 886 | 53 | 6.0 | 18.0 |
| DF | 2080 | 118 | 5.7 | 12.9 |
| MG | 11354 | 519 | 4.6 | 11.9 |
| SP | 40494 | 1820 | 4.5 | 8.7 |
| PR | 4923 | 199 | 4.0 | 11.9 |

## Retard selon la distance client-vendeur

- **Question** : La distance entre le client et le vendeur explique-t-elle les retards ? (piste de variable pour le modèle de retard)
- **Destinataire** : Logistique, équipe data
- **Techniques** : jointure multiple (6 tables dont 2 fois geolocation), formule de haversine, CASE pour les tranches, agrégat
- **Lecture** : le taux de retard triple avec la distance (4,4 % sous 100 km, 12 % au-delà de 2 000 km) : variable à garder pour le modèle.
- **Fichier** : `sql/queries/04_retard_selon_distance.sql`

| distance_band | orders | avg_distance_km | late_rate_pct |
|---|---|---|---|
| 1. < 100 km | 17904 | 40 | 4.4 |
| 2. 100-500 km | 36995 | 323 | 6.1 |
| 3. 500-1000 km | 25745 | 712 | 7.1 |
| 4. 1000-2000 km | 9739 | 1403 | 9.5 |
| 5. >= 2000 km | 5608 | 2316 | 12.0 |

## Impact du retard sur la note des avis

- **Question** : Les retards de livraison dégradent-ils les avis clients ?
- **Destinataire** : Service client, Logistique
- **Techniques** : jointure, CASE, agrégats (AVG, part des notes 1-2)
- **Lecture** : à l'heure, la note moyenne est de 4,3 et 9 % d'avis négatifs ; au-delà de 7 jours de retard, 1,7 et 79 % d'avis négatifs.
- **Fichier** : `sql/queries/05_impact_retard_avis.sql`

| delay_band | reviews | avg_score | negative_pct |
|---|---|---|---|
| 1. à l'heure ou en avance | 89944 | 4.29 | 9.3 |
| 2. 1 à 3 jours de retard | 1856 | 3.29 | 32.2 |
| 3. 4 à 7 jours de retard | 1756 | 2.10 | 67.7 |
| 4. plus de 7 jours de retard | 2797 | 1.70 | 79.2 |

## Top 3 des vendeurs par état

- **Question** : Quels vendeurs dominent chaque marché régional ?
- **Destinataire** : Direction (relation vendeurs)
- **Techniques** : jointure, agrégat, fonctions de fenêtre RANK() et SUM() OVER (PARTITION BY) pour la part du CA de l'état
- **Lecture** : à SP le marché est très fragmenté (le n°1 pèse 2,6 % du CA de l'état), alors qu'à RJ les 3 premiers en font près de 40 %.
- **Fichier** : `sql/queries/06_top_vendeurs_par_etat.sql`

| state | rank_in_state | seller | orders | revenue | state_share_pct |
|---|---|---|---|---|---|
| SP | 1 | 4869f7a5 | 1131 | 229238 | 2.6 |
| SP | 2 | 4a3ca931 | 1804 | 200326 | 2.3 |
| SP | 3 | fa1c13f2 | 584 | 192842 | 2.2 |
| PR | 1 | ccc4bbb5 | 187 | 74005 | 5.9 |
| PR | 2 | 522620dc | 174 | 57168 | 4.5 |
| PR | 3 | 77530e97 | 319 | 46471 | 3.7 |
| MG | 1 | a1043baf | 715 | 101483 | 10.1 |
| MG | 2 | 25c5c91f | 158 | 54679 | 5.5 |
| MG | 3 | 7299e27e | 337 | 34225 | 3.4 |
| SC | 1 | 04308b1e | 94 | 60131 | 9.6 |
| SC | 2 | eeb6de78 | 83 | 43740 | 7.0 |
| SC | 3 | 712e6ed8 | 79 | 39815 | 6.4 |
| RJ | 1 | 46dc3b2c | 518 | 127161 | 15.2 |
| RJ | 2 | 620c87c1 | 732 | 113659 | 13.6 |
| RJ | 3 | edb1ef5e | 166 | 79285 | 9.5 |

## Taux de réachat et délai avant la deuxième commande

- **Question** : Combien de clients reviennent, et au bout de combien de temps ?
- **Destinataire** : Marketing
- **Techniques** : jointure, fonctions de fenêtre ROW_NUMBER() et LEAD(), agrégats conditionnels (FILTER), PERCENTILE_CONT
- **Lecture** : seulement 3 % des clients repassent commande ; la moitié de ceux-là le font en moins de 28 jours. Gros levier marketing.
- **Fichier** : `sql/queries/07_reachat.sql`

| customers | repeat_customers | repeat_rate_pct | median_days_to_second | same_day_second_order |
|---|---|---|---|---|
| 94990 | 2888 | 3.04 | 28.0 | 869 |

## Scores RFM des clients (base de la segmentation)

- **Question** : Comment se répartissent les clients selon la récence, la fréquence et le montant de leurs achats ?
- **Destinataire** : Marketing
- **Techniques** : jointure multiple, agrégats, fonction de fenêtre NTILE(5)
- **Lecture** : 97 % des clients n'ont commandé qu'une fois (F = 1) ; les multi-acheteurs dépensent 2 à 4 fois plus et sont la cible fidélité.
- **Fichier** : `sql/queries/08_scores_rfm.sql`

| r_score | f_score | customers | avg_recency_days | avg_monetary | avg_m_score |
|---|---|---|---|---|---|
| 5 | 3 | 64 | 94 | 599.46 | 4.80 |
| 5 | 2 | 579 | 96 | 290.97 | 4.29 |
| 5 | 1 | 18354 | 95 | 163.73 | 2.98 |
| 4 | 3 | 63 | 184 | 493.96 | 4.79 |
| 4 | 2 | 529 | 184 | 301.24 | 4.22 |
| 4 | 1 | 18406 | 186 | 165.32 | 3.00 |
| 3 | 3 | 39 | 265 | 492.74 | 4.74 |
| 3 | 2 | 586 | 268 | 294.28 | 4.32 |
| 3 | 1 | 18373 | 270 | 152.91 | 2.94 |
| 2 | 3 | 40 | 378 | 544.96 | 4.73 |
| 2 | 2 | 532 | 367 | 282.23 | 4.17 |
| 2 | 1 | 18426 | 366 | 163.44 | 2.95 |
| 1 | 3 | 30 | 535 | 266.39 | 4.17 |
| 1 | 2 | 426 | 514 | 285.50 | 4.10 |
| 1 | 1 | 18542 | 524 | 160.70 | 2.93 |
