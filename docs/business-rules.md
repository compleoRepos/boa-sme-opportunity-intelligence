# Moteur déterministe d’intelligence d’opportunités

**Produit :** BOA SME Opportunity Intelligence  
**Statut :** spécification métier du MVP  
**Version du document :** 1.0.0  
**Date de référence :** 2026-09-18  
**Périmètre :** détection d’événements transactionnels, génération d’opportunités commerciales explicables et signal relationnel de tension financière.

> Ce document formalise le comportement attendu du moteur à partir des exigences du MVP. Il ne décrit pas une décision de crédit. Il ne définit ni une probabilité de défaut, ni une notation de risque, ni une autorisation de financement.

## 1. Finalité et limites

Le moteur répond à la question suivante : **quels clients PME le chargé d’affaires peut-il contacter aujourd’hui, pour quel besoin potentiel, avec quelles preuves et quel niveau de confiance ?**

Le moteur transforme des métriques calculées à partir des transactions et des soldes en signaux, puis combine ces signaux avec le profil client, les produits détenus et le comportement historique. Le résultat est une recommandation commerciale, jamais une décision automatisée concernant l’octroi, le prix ou le montant d’un crédit.

La chaîne déterministe est la suivante :

`Transactions et soldes → métriques → comparaison historique et saisonnière → signaux → règles d’opportunité → confiance → priorité → action RM → résultat commercial`

Le moteur ne doit pas utiliser de LLM ou de contenu génératif pour décider qu’une opportunité existe. Une capacité d’IA pourra être ajoutée ultérieurement pour résumer ou préparer un briefing, sans modifier la décision déterministe du MVP.

## 2. Principes de décision

1. **Même entrée, même version, même sortie.** Une exécution reproductible utilise le même instant de coupure, les mêmes données, la même configuration et la même version d’algorithme.
2. **Les règles sont configurables, non dispersées dans l’interface.** Les seuils, fenêtres, poids et activations sont portés par une configuration versionnée du moteur.
3. **Une tendance exige plusieurs observations.** Un événement isolé ne suffit pas à produire une opportunité, sauf lorsque la règle est explicitement conçue pour un événement ponctuel et que cette exception est auditée. Aucune des quatre règles du MVP n’utilise cette exception.
4. **La comparaison historique prime sur la comparaison naïve.** Une variation par rapport à la période précédente est confrontée à une base historique et, lorsque cela est possible, au comportement saisonnier du client.
5. **La qualité des données est une condition de décision.** Une donnée absente, trop récente, dupliquée ou incomplète peut empêcher la création d’une opportunité ou la réduire à un signal à examiner.
6. **L’explication est une sortie obligatoire.** Toute opportunité expose les éléments `WHY`, `WHAT`, `WHEN`, `CONFIDENCE` et `EVIDENCE`, ainsi que les valeurs observées, les seuils et les comparaisons utilisées.
7. **Le signal de tension reste relationnel.** Le libellé `FINANCIAL_STRESS_SIGNAL` est le seul libellé autorisé pour ce cas. Les termes « score de risque », « score de crédit », « probabilité de défaut » et « décision de crédit » sont interdits dans les sorties du moteur et de l’interface.

## 3. Temps de référence et périodes d’observation

### 3.1 Date de coupure

Chaque exécution reçoit une `asOfDate`, correspondant à la dernière date de données considérée comme complète. Les transactions postérieures à cette date sont exclues. La date et le fuseau horaire sont enregistrés dans l’audit.

Une journée n’est considérée comme complète que lorsque la source a confirmé sa clôture. Si la dernière journée n’est pas complète, le moteur utilise la dernière journée complète et conserve l’écart dans la qualité des données.

### 3.2 Fenêtres obligatoires

Le service d’analytics calcule les métriques sur les fenêtres suivantes :

| Code | Fenêtre | Usage principal |
|---|---:|---|
| `7D` | 7 jours glissants | récence, confirmation courte, activité internationale récente |
| `30D` | 30 jours glissants | activité courante et horizon de contact immédiat |
| `90D` | 90 jours glissants | décision principale du MVP et comparaison trimestrielle |
| `180D` | 180 jours glissants | persistance, trésorerie et changement de régime |
| `365D` | 365 jours glissants | baseline annuelle et saisonnalité |

Les fenêtres sont calculées en jours calendaires. Les jours sans transaction restent dans le dénominateur des métriques de solde et de fréquence ; ils ne sont pas supprimés silencieusement.

### 3.3 Période précédente et base historique

Pour une fenêtre `W`, le moteur calcule :

- `current(W)`: fenêtre se terminant à `asOfDate` ;
- `previous(W)`: fenêtre de même durée immédiatement antérieure ;
- `historicalBaseline(W)`: médiane des fenêtres comparables disponibles dans les douze derniers mois, hors fenêtre courante ;
- `samePeriodLastYear(W)`: fenêtre alignée sur la même période de l’année précédente, lorsque douze mois d’historique sont disponibles.

La croissance simple est :

`growthRate = (current - previous) / max(abs(previous), denominatorFloor)`

`denominatorFloor` est défini par métrique dans la configuration afin d’éviter un ratio artificiellement élevé quand la base est nulle ou très faible. Si la base est inférieure à ce plancher, la variation est marquée `BASELINE_LOW` et ne peut pas, seule, déclencher une opportunité.

La distance à la base historique est :

`baselineDelta = (current - historicalBaseline) / max(abs(historicalBaseline), denominatorFloor)`

Les taux sont conservés avec leur signe et leur valeur non arrondie pour le calcul. L’interface peut afficher une valeur arrondie, mais l’audit stocke la valeur calculée et la méthode d’arrondi.

### 3.4 Règle de disponibilité minimale

Une règle utilisant `90D` exige au minimum 75 jours calendaires de données complètes sur cette fenêtre, ou une couverture explicite supérieure ou égale à 83 %. Une règle utilisant `365D` exige au minimum 270 jours de données complètes et marque la comparaison annuelle comme partielle si douze mois ne sont pas disponibles.

Un client disposant de moins de 90 jours d’historique peut produire des signaux descriptifs, mais aucune opportunité MVP n’est créée sans satisfaire la disponibilité minimale de la règle. Le motif `INSUFFICIENT_HISTORY` est exposé au RM et enregistré dans l’audit.

## 4. Dictionnaire des métriques

Les montants sont calculés par client, compte et devise, puis consolidés dans la devise de référence du portefeuille selon le taux de conversion fourni par la couche d’intégration. Un montant converti doit conserver la devise d’origine, le taux et l’horodatage du taux. En l’absence de taux valide, la métrique multi-devise est marquée `CURRENCY_INCOMPLETE` et ne déclenche pas de règle qui exige une consolidation.

| Métrique | Définition déterministe | Fenêtres par défaut |
|---|---|---|
| `inflowAmount` | somme des crédits externes entrant sur les comptes actifs ; transferts internes entre comptes du même client exclus | `30D`, `90D`, `180D`, `365D` |
| `outflowAmount` | somme des débits externes, paiements fournisseurs et sorties assimilées ; transferts internes exclus | `30D`, `90D`, `180D`, `365D` |
| `supplierPaymentAmount` | somme des paiements catégorisés fournisseur après normalisation de la contrepartie et de la catégorie | `30D`, `90D`, `180D`, `365D` |
| `transactionCount` | nombre de transactions valides et non dupliquées | toutes |
| `internationalFlowAmount` | somme absolue des flux identifiés comme internationaux, avec séparation entrée/sortie disponible | `30D`, `90D`, `180D`, `365D` |
| `internationalTransactionCount` | nombre de transactions internationales valides | toutes |
| `averageBalance` | moyenne arithmétique du solde de fin de journée sur les jours couverts | `30D`, `90D`, `180D`, `365D` |
| `minimumBalance` | minimum du solde de fin de journée sur la fenêtre | toutes |
| `maximumBalance` | maximum du solde de fin de journée sur la fenêtre | toutes |
| `cashSurplusAmount` | moyenne des soldes positifs au-dessus du seuil de réserve opérationnelle configuré | `30D`, `90D`, `180D`, `365D` |
| `surplusDayRatio` | nombre de jours avec surplus / nombre de jours couverts | toutes |
| `creditLineUtilization` | encours utilisé / limite de crédit disponible, borné entre 0 et 1 ; agrégation pondérée par limite | toutes |
| `creditUtilizationChange` | variation de l’utilisation entre la fenêtre courante et la période précédente | `30D`, `90D` |
| `activityFrequency` | nombre de jours distincts avec une transaction valide / nombre de jours de la fenêtre | toutes |
| `productUsage` | indicateur d’usage d’un produit, selon transactions, encours ou opérations propres au catalogue | `90D`, `180D` |
| `financingRecency` | nombre de jours depuis la dernière utilisation ou souscription d’un financement d’investissement | `365D` |
| `dataCoverage` | jours couverts et exploitables / jours attendus | toutes |

Les catégories et l’identification des fournisseurs doivent être produites par le service de transactions ou l’adapter bancaire. Le moteur ne déduit pas une catégorie à partir d’un texte non normalisé au moment de la décision.

### 4.1 Métriques de croissance et de fréquence

Une métrique de croissance est calculée sur `90D` pour les quatre règles, sauf configuration documentée. Le moteur utilise simultanément `growthRate`, `baselineDelta` et le niveau absolu. Une croissance de 30 % sur une base proche de zéro est donc insuffisante si elle ne franchit pas le `denominatorFloor` et ne présente pas un niveau absolu significatif.

La fréquence internationale est « croissante » lorsque les deux conditions suivantes sont vraies :

- `internationalTransactionCount(30D) > internationalTransactionCount(previous30D)` ;
- la croissance du compte de transactions est supérieure au seuil `internationalFrequencyGrowthThreshold`, ou au moins deux des trois dernières fenêtres de 30 jours montrent une progression.

### 4.2 Utilisation des produits

`ABSENT` signifie qu’aucun produit actif correspondant n’est présent dans `customer_products`. `UNDERUTILIZED` signifie que le produit est présent, mais que son usage observé sur 90 jours est inférieur au seuil du catalogue ou à la fréquence minimale configurée. La règle ne doit jamais déduire l’absence d’un produit lorsque le référentiel produit n’est pas synchronisé.

## 5. Saisonnalité et comparaison robuste

### 5.1 Objectif

Le moteur doit éviter de confondre une saison normale avec une opportunité. Une hausse de décembre par rapport à novembre, par exemple, ne constitue pas à elle seule une croissance anormale.

### 5.2 Logique MVP

Pour chaque métrique éligible, le moteur applique dans l’ordre :

1. comparaison de la période courante à la période précédente de même durée ;
2. comparaison à la médiane des périodes comparables des douze derniers mois ;
3. comparaison à la même période de l’année précédente quand elle est disponible ;
4. calcul d’un indicateur `seasonalityAdjusted`.

L’indicateur est positif seulement si la hausse ou la baisse dépasse à la fois le seuil de la règle et la variation saisonnière attendue. La saisonnalité propre au client est privilégiée sur une moyenne sectorielle. Une moyenne sectorielle ne peut servir que de fallback documenté et ne doit pas être présentée comme une observation individuelle.

### 5.3 Baseline robuste

La baseline par défaut est la médiane des fenêtres comparables. La dispersion est mesurée par l’écart absolu médian (`MAD`) lorsque le nombre d’observations est suffisant. Un signal reçoit la mention `SEASONAL_OR_NORMAL_VARIATION` lorsque l’écart courant reste dans la bande historique configurée :

`[median - k × MAD, median + k × MAD]`

Le paramètre `k` est versionné. Avec moins de six observations comparables, la méthode de dispersion est `INSUFFICIENT_BASELINE` et la confidence maximale est plafonnée à `MEDIUM`.

### 5.4 Cas de saisonnalité connue

Les profils peuvent déclarer des mois ou périodes saisonniers, par exemple décembre pour le commerce. Cette déclaration ne supprime pas l’analyse : elle impose une comparaison à la baseline saisonnière et exige une persistance supérieure à celle d’un mois normal. Une hausse saisonnière attendue peut générer un signal descriptif, mais ne déclenche aucune des quatre opportunités sans dépassement de la baseline ajustée.

## 6. Détection des signaux

Le Signal Detection Service produit des signaux atomiques avant toute décision d’opportunité. Un signal ne doit pas contenir une recommandation commerciale.

### 6.1 Types du MVP

| Signal | Condition par défaut | Preuves minimales |
|---|---|---|
| `INFLOW_GROWTH` | croissance des encaissements supérieure à `0,25` et dépassement de la baseline ajustée | valeur courante, précédente, taux, baseline |
| `OUTFLOW_GROWTH` | croissance des décaissements supérieure au seuil configuré | mêmes éléments |
| `SUPPLIER_PAYMENT_GROWTH` | croissance des paiements fournisseurs supérieure à `0,20` et au plancher absolu | valeur, taux, nombre de fournisseurs si disponible |
| `INTERNATIONAL_FLOW_GROWTH` | croissance des flux internationaux supérieure à `0,30` et non expliquée par la saisonnalité | montants, pays ou sens si disponibles |
| `BALANCE_SURPLUS` | moyenne de solde et ratio de jours en surplus supérieurs à leurs seuils | moyenne, seuil, ratio, durée |
| `BALANCE_DECLINE` | baisse de la moyenne de solde supérieure à `0,20` et confirmée par la baseline | valeurs et comparaisons |
| `CREDIT_UTILIZATION_INCREASE` | progression de l’utilisation de ligne supérieure au seuil configuré | ratios courant/précédent, limite disponible |
| `TRANSACTION_VOLUME_GROWTH` | croissance du nombre de transactions supérieure à `0,15` | comptages et taux |

Les seuils indiqués comme défaut sont des paramètres de la configuration initiale, et non des constantes de code.

### 6.2 Format logique d’un signal

Chaque signal contient au minimum : `signalId`, `customerId`, `type`, `severity`, `status`, `value`, `threshold`, `period`, `asOfDate`, `evidence`, `baseline`, `dataQuality`, `engineVersion` et `ruleSetVersion`.

La sévérité est déterminée par la marge au seuil : `LOW` lorsque la marge est comprise entre 0 et 10 % du seuil, `MEDIUM` entre 10 et 50 %, et `HIGH` au-delà de 50 %, sauf seuil spécifique de la configuration. La sévérité ne constitue pas une priorité commerciale.

### 6.3 Confirmation et déduplication

Un signal passe à l’état `CONFIRMED` si la condition est vraie dans la fenêtre courante et dans au moins une des deux fenêtres comparables précédentes, ou si elle dépasse la marge forte `strongEvidenceMargin` définie pour le signal. Un signal observé une seule fois reste `OBSERVED` et ne peut pas satisfaire une règle qui exige la persistance.

Les signaux identiques pour un même client, type, fenêtre et `asOfDate` sont dédupliqués par une clé idempotente. Une nouvelle version de configuration peut créer une nouvelle décision, mais ne modifie pas le signal audité précédemment.

## 7. Les quatre règles d’opportunité du MVP

Les règles sont évaluées sur un snapshot cohérent de données. Une règle ne lit pas directement la base transactionnelle ; elle consomme les métriques et signaux versionnés du service d’analytics et du Signal Detection Service.

### Règle A — `INVESTMENT_FINANCING`

**Horizon :** `1-3_MONTHS`  
**Finalité :** identifier une croissance d’activité susceptible de justifier un échange sur le financement d’investissement ou le besoin de fonds de roulement.

La règle est vraie si toutes les conditions suivantes sont satisfaites sur `90D`, après ajustement saisonnier :

| Condition obligatoire | Critère initial |
|---|---:|
| croissance des encaissements | `inflowGrowthRate > 0,25` |
| croissance des paiements fournisseurs | `supplierPaymentGrowthRate > 0,20` |
| croissance du volume transactionnel | `transactionVolumeGrowthRate > 0,15` |
| absence de financement d’investissement récent | aucun financement pertinent utilisé ou souscrit dans `financingLookbackDays` |

Le client doit également satisfaire la couverture de données minimale et ne pas être en état `DATA_INVALID`. Les trois signaux de croissance doivent être `CONFIRMED`, ou au moins deux doivent être `CONFIRMED` et le troisième dépasser `strongEvidenceMargin`; ce choix est versionné comme `confirmationPolicy`.

**Sortie commerciale indicative :** produits issus du catalogue et éligibles au client, notamment `Investment Financing` et `Working Capital Facility`. Les noms ne sont jamais codés dans la règle.

**Preuves attendues :** taux d’encaissement, taux de paiements fournisseurs, taux de volume, comparaison historique, dernière utilisation de financement et date de coupure.

### Règle B — `TRADE_FINANCE`

**Horizon :** `0-3_MONTHS`  
**Finalité :** repérer un besoin potentiel lié à la répétition ou à l’intensification des flux internationaux.

La règle est vraie si toutes les conditions suivantes sont satisfaites :

| Condition obligatoire | Critère initial |
|---|---:|
| croissance des flux internationaux | `internationalFlowGrowthRate > 0,30` |
| fréquence internationale en hausse | progression de la fréquence sur 30 jours et confirmation selon la politique de fréquence |
| couverture Trade Finance | produit `ABSENT` ou `UNDERUTILIZED` selon le catalogue |

Un transfert international isolé ne satisfait pas la condition de fréquence. La règle exige au moins deux périodes positives parmi les trois dernières fenêtres de 30 jours, sauf dépassement de la marge forte configurée accompagné d’au moins deux transactions distinctes et de contreparties cohérentes.

**Sortie commerciale indicative :** produit ou service `Trade Finance` du catalogue, avec justification `ABSENT` ou `UNDERUTILIZED`. L’absence de synchronisation du référentiel produits bloque la décision et produit `PRODUCT_DATA_INCOMPLETE`.

### Règle C — `CASH_INVESTMENT`

**Horizon :** `0-1_MONTH`  
**Finalité :** identifier une trésorerie excédentaire persistante pouvant justifier un échange sur le cash management, un dépôt à terme ou une solution de liquidité.

La règle est vraie si les trois conditions suivantes sont satisfaites :

| Condition obligatoire | Critère initial configurable |
|---|---:|
| moyenne de solde élevée | `averageBalance(90D)` supérieure au seuil absolu du segment ou au percentile configuré du portefeuille |
| excédent persistant | `surplusDayRatio(90D) >= 0,70` et condition vraie dans au moins 2 des 3 dernières fenêtres de 30 jours |
| faible utilisation de crédit | `creditLineUtilization(90D) <= lowCreditUtilizationThreshold` |

Le seuil de solde doit être défini en devise de référence et par segment lorsque possible. Le moteur ne doit pas qualifier de « trésorerie excédentaire » une somme élevée mais temporaire : une pointe isolée, un encaissement de cession ou un remboursement non récurrent est marqué comme événement ponctuel et exclu de la persistance.

**Sortie commerciale indicative :** produits actifs et éligibles du catalogue tels que `Cash Management`, `Term Deposit` ou `Liquidity Investment`.

### Règle D — `FINANCIAL_STRESS_SIGNAL`

**Horizon :** `0-1_MONTH` pour la prise de contact relationnelle  
**Finalité :** signaler au chargé d’affaires une dégradation observable des flux ou de la liquidité afin qu’il puisse comprendre la situation avec le client.

La règle est vraie si :

`(inflowDeclineRate < -0,25 OR balanceDeclineRate < -0,20) AND creditUtilizationChange > utilizationIncreaseThreshold`

La baisse des encaissements ou du solde doit être confirmée par la baseline historique et non seulement par le mois précédent. L’incident éventuel peut renforcer la preuve mais n’est pas nécessaire au déclenchement. Un incident technique ou un changement de compte connu doit être exclu avant évaluation.

**Sortie obligatoire :** `FINANCIAL_STRESS_SIGNAL`. L’interface affiche « signal relationnel à examiner ». Elle ne calcule ni montant de crédit, ni score de risque, ni probabilité de défaut, et ne suggère pas une décision d’acceptation ou de refus.

**Preuves attendues :** baisse des encaissements ou du solde, évolution de l’utilisation de ligne, historique de la tendance, couverture de données et éventuels événements explicatifs.

## 8. Conditions communes de génération

Une opportunité est créée seulement si :

- la règle est active à la date de coupure ;
- son jeu de métriques est complet selon les exigences de la règle ;
- les données ne sont ni invalides ni manifestement dupliquées ;
- le client et ses comptes sont actifs ;
- les signaux requis sont reliés au même `customerId` et au même snapshot ;
- aucune exclusion de faux positif n’est active ;
- la décision et toutes ses entrées peuvent être persistées dans l’audit.

Si une condition est presque satisfaite mais qu’une preuve manque, le moteur peut produire un signal `NEEDS_REVIEW`, mais ne doit pas présenter une opportunité comme confirmée. Une opportunité déjà active est mise à jour de manière idempotente ; elle n’est pas recréée chaque jour sans changement de preuve.

## 9. Faux positifs et exclusions explicites

Les cas suivants sont traités comme des tests métier obligatoires et comme des garde-fous d’exécution.

| Cas | Traitement déterministe |
|---|---|
| hausse saisonnière connue | comparer à la baseline saisonnière ; aucune opportunité si le dépassement ajusté est absent |
| transaction exceptionnelle de montant élevé | marquer `ONE_OFF_TRANSACTION` et recalculer une métrique robuste hors événement ; une seule observation ne confirme aucune règle |
| virement international unique | signal descriptif possible, mais `TRADE_FINANCE` interdit sans fréquence confirmée |
| transfert interne entre comptes du client | exclure des encaissements et décaissements externes |
| remboursement, cession, dividende ou encaissement non récurrent connu | catégoriser comme événement ponctuel et exclure de la tendance, sauf configuration contraire auditée |
| changement de compte ou migration de données | suspendre la décision jusqu’à réconciliation de l’historique |
| données incomplètes ou retard de chargement | état `DATA_INCOMPLETE`, pas d’opportunité nouvelle |
| taux de change absent ou incohérent | pas de métrique consolidée multi-devise ; pas de règle dépendante |
| paiement fournisseur mal catégorisé | réduire la qualité de données et empêcher la règle A si le seuil de couverture fournisseur n’est pas atteint |
| baisse due à une clôture administrative connue | exclure la période affectée et produire un motif d’exclusion |
| seuil franchi d’un seul point dans une série volatile | exiger la confirmation historique ou classer `OBSERVED` |
| produit existant mais référentiel non synchronisé | ne pas conclure à une absence de produit |

Le moteur stocke le motif de non-déclenchement. L’absence d’opportunité est donc explicable, notamment dans les tests de faux positifs.

## 10. Stratégie statistique déterministe du MVP

Le MVP utilise une stratégie hybride **règles + statistiques descriptives robustes**. Les statistiques ne remplacent pas les règles : elles servent à construire la baseline, confirmer la persistance, mesurer la marge au seuil et réduire les faux positifs.

### 10.1 Étapes

1. normaliser les transactions et exclure les doublons ;
2. agréger les métriques par fenêtre ;
3. construire la baseline médiane et la dispersion historique ;
4. ajuster la comparaison pour la saisonnalité ;
5. détecter les signaux atomiques ;
6. appliquer les quatre règles avec leurs conditions obligatoires ;
7. calculer la confidence explicable ;
8. calculer la priorité ;
9. produire l’explication et l’audit.

### 10.2 Robustesse et seuils

La médiane et le `MAD` sont privilégiés à la moyenne et à l’écart-type pour limiter l’effet d’une transaction atypique. Les seuils absolus et relatifs sont utilisés ensemble. Une règle ne doit pas produire une opportunité à partir d’un taux de croissance élevé sur une base insignifiante.

Le moteur ne fait pas d’inférence causale. Il identifie une coïncidence stable de signaux compatible avec un besoin commercial potentiel. La décision finale de prise de contact et la qualification de besoin appartiennent au chargé d’affaires.

### 10.3 Historique court

Lorsque l’historique est inférieur au minimum requis, le moteur conserve les métriques et peut créer un signal de qualité réduite, mais bloque l’opportunité correspondante. Il ne remplace pas silencieusement la baseline client par une baseline globale.

## 11. Score de confiance explicable

### 11.1 Définition

La confidence est un score de qualité de l’évidence en réponse à une règle déjà satisfaite. Elle n’est ni une probabilité statistique, ni une probabilité de conversion, ni une mesure de solvabilité.

`confidence = somme des points des composants / 100`

Chaque composant est compris entre 0 et 1 et son poids est configuré. Les points sont calculés à partir des valeurs observées, de la marge au seuil, de la persistance et de la qualité des données. Une valeur affichée comme `0,82` doit toujours être accompagnée de ses composants.

### 11.2 Niveaux

| Niveau | Intervalle | Interprétation |
|---|---:|---|
| `HIGH` | `>= 0,75` | preuves fortes, cohérentes et récentes |
| `MEDIUM` | `0,50 à < 0,75` | règle satisfaite, mais preuve partielle, peu persistante ou moins séparée de la baseline |
| `LOW` | `< 0,50` | règle satisfaite au minimum, confiance limitée ; revue RM recommandée |

Une règle satisfaite peut créer une opportunité `LOW`, mais sa priorité est plafonnée à `P3` sauf validation explicite d’un administrateur de configuration. Une confidence ne peut pas dépasser le plafond imposé par la qualité de données ou par un historique insuffisant.

### 11.3 Composants par règle

Les poids initiaux sont les suivants ; ils sont versionnés et modifiables uniquement dans la configuration approuvée.

| Composant | Investissement | Trade Finance | Cash Investment | Stress |
|---|---:|---:|---:|---:|
| satisfaction et marge des signaux principaux | 35 | 35 | 40 | 40 |
| persistance historique | 15 | 15 | 25 | 15 |
| séparation par rapport à la baseline ajustée | 15 | 15 | 15 | 15 |
| écart produit / sous-utilisation | 10 | 20 | 10 | 0 |
| récence | 10 | 10 | 5 | 10 |
| qualité et couverture de données | 10 | 5 | 5 | 10 |
| corroboration secondaire | 5 | 0 | 0 | 10 |
| **Total** | **100** | **100** | **100** | **100** |

Pour chaque composant, l’explication fournit `weight`, `rawValue`, `normalizedValue`, `points` et `reason`. Par exemple, le composant « marge du seuil » indique le taux observé, le seuil, la marge et le nombre de conditions validées. Les points ne doivent pas être calculés dans le frontend.

### 11.4 Plafonds de confiance

La confidence est plafonnée à `0,65` si l’historique ne permet pas une baseline annuelle, à `0,60` si la règle n’a pas de confirmation multi-période, et à `0,49` lorsque la couverture de données est sous le minimum de la règle. Dans ce dernier cas, l’opportunité ne devrait normalement pas être créée ; le plafond protège contre une sortie incohérente si une configuration permissive l’autorise.

## 12. Priorisation

La priorité ordonne les recommandations destinées au RM. Elle ne modifie pas la règle d’existence de l’opportunité et ne transforme pas le signal de tension en risque de crédit.

### 12.1 Facteurs

Le score est calculé sur 100 :

`priorityScore = 0,30 × confidenceScore + 0,20 × signalStrength + 0,15 × urgency + 0,15 × recency + 0,10 × relationshipContext + 0,10 × productGap`

Chaque facteur est normalisé sur 100 et accompagné d’une justification. `potentialValue` peut être utilisé comme facteur complémentaire seulement s’il s’agit d’un proxy documenté, par exemple une capacité d’activité ou une exposition opérationnelle. Le MVP n’invente pas de chiffre de revenu, de marge, de montant financé ou de valeur commerciale.

- **Confidence :** confidence multipliée par 100.
- **Signal strength :** intensité et marge des signaux requis.
- **Urgency :** horizon de la règle et rapidité de dégradation ; la règle Stress est urgente au sens relationnel.
- **Recency :** proximité de la dernière observation complète.
- **Relationship context :** ancienneté, RM assigné et contexte disponible dans le CRM ; absence de donnée donne un score neutre, non zéro punitif.
- **Product gap :** absence ou sous-utilisation d’un produit éligible.

### 12.2 Niveaux

| Niveau | Score | Action suggérée |
|---|---:|---|
| `P1` | `>= 80` | traiter en priorité dans la journée |
| `P2` | `60 à < 80` | planifier un contact à court terme |
| `P3` | `40 à < 60` | revue et qualification par le RM |
| `P4` | `< 40` | conserver pour suivi, sans urgence |

Une opportunité `LOW` est plafonnée à `P3`. Une opportunité exclue, rejetée ou expirée ne peut pas apparaître dans les listes actives.

## 13. Sortie d’opportunité et explication

Chaque opportunité possède au minimum : `opportunityId`, `customerId`, `opportunityType`, `opportunityStatus`, `horizon`, `confidence`, `confidenceLevel`, `priorityScore`, `priorityLevel`, `why`, `what`, `when`, `recommendedProducts`, `evidence`, `generatedAt`, `asOfDate`, `engineVersion`, `ruleSetVersion` et `decisionAuditId`.

- **WHY :** signaux et variations qui ont satisfait la règle.
- **WHAT :** besoin commercial potentiel et produits éligibles du catalogue.
- **WHEN :** horizon d’action, date de fraîcheur et éventuelle échéance de revue.
- **CONFIDENCE :** score, niveau et décomposition des points.
- **EVIDENCE :** métriques brutes, valeurs précédentes, baseline, seuils, couverture et références de signaux.

L’endpoint attendu est `GET /api/v1/opportunities/{id}/explanation`. Il retourne les signaux, métriques, seuils, comparaisons historiques, ajustement saisonnier, composants de confidence, produits recommandés, horizon et motifs d’exclusion non retenus. La réponse ne doit pas nécessiter de recalcul non audité qui pourrait produire une explication différente de la décision persistée.

## 14. Configuration versionnée

### 14.1 Métadonnées obligatoires

Une configuration active contient :

`configId`, `engineVersion`, `ruleSetVersion`, `status`, `effectiveFrom`, `effectiveTo`, `createdBy`, `approvedBy`, `createdAt`, `checksum`, `changeReason` et `rollbackTarget`.

Les statuts autorisés sont `DRAFT`, `APPROVED`, `ACTIVE`, `RETIRED` et `ROLLED_BACK`. Une configuration active est immuable. Une correction crée une nouvelle version et ne réécrit pas les décisions historiques.

### 14.2 Paramètres initiaux

| Paramètre | Valeur initiale | Portée |
|---|---:|---|
| `primaryDecisionWindow` | `90D` | moteur |
| `minimumHistoryDays90D` | `75` | analytics |
| `minimumDataCoverage` | `0,83` | moteur |
| `inflowGrowthThreshold` | `0,25` | règle A |
| `supplierGrowthThreshold` | `0,20` | règle A |
| `transactionVolumeGrowthThreshold` | `0,15` | règle A |
| `internationalFlowGrowthThreshold` | `0,30` | règle B |
| `internationalFrequencyGrowthThreshold` | `0,10` | règle B |
| `cashSurplusDayRatioThreshold` | `0,70` | règle C |
| `lowCreditUtilizationThreshold` | valeur validée par BOA et segmentée | règle C |
| `inflowDeclineThreshold` | `-0,25` | règle D |
| `balanceDeclineThreshold` | `-0,20` | règle D |
| `utilizationIncreaseThreshold` | valeur validée par BOA | règle D |
| `financingLookbackDays` | valeur validée par BOA | règle A |
| `seasonalityMadMultiplier` | valeur validée par BOA | baseline |
| `strongEvidenceMargin` | valeur validée par BOA | signaux |

Les valeurs à valider par BOA doivent rester explicitement `PENDING_APPROVAL` tant qu’elles ne sont pas acceptées. Le moteur doit refuser l’activation d’une configuration dont un paramètre obligatoire n’a pas de valeur approuvée.

### 14.3 Gouvernance

Un administrateur peut consulter les règles, seuils, produits, activations et versions. La modification exige un motif, une approbation et une date d’effet. Le frontend affiche la configuration active, mais ne porte pas la logique et ne peut pas la modifier directement sans l’API d’administration autorisée.

## 15. Événements métier

Le MVP utilise HTTP et une outbox locale ; un transport de messages est une extension future. Le cœur du moteur ne dépend pas d’un fournisseur de transport particulier.

Les événements minimaux sont : `TransactionImported`, `MetricsCalculated`, `SignalDetected`, `OpportunityCreated`, `OpportunityUpdated`, `OpportunityAccepted`, `OpportunityDismissed`, `CustomerContacted`, `MeetingScheduled`, `OfferCreated`, `OpportunityConverted`, `OpportunityRejected` et `OpportunityNotRelevant`.

Chaque événement contient : `eventId`, `eventType`, `eventVersion`, `occurredAt`, `aggregateType`, `aggregateId`, `customerId`, `correlationId`, `causationId`, `idempotencyKey`, `producer`, `engineVersion`, `ruleSetVersion` et `payload`.

Le payload de `OpportunityCreated` référence les signaux et le snapshot de métriques plutôt que de recopier des données contradictoires. Les consommateurs doivent être idempotents. La publication d’un événement ne doit pas être considérée comme une preuve de succès commercial.

## 16. Audit et traçabilité

Chaque décision du moteur est enregistrée dans un journal append-only. L’audit doit permettre de reconstruire exactement pourquoi l’opportunité a été créée, non créée, mise à jour ou retirée.

L’enregistrement contient au minimum :

- `decisionId`, `opportunityId` et `customerId` ;
- `engineVersion`, `ruleSetVersion`, `configId` et checksum ;
- `asOfDate`, `generatedAt`, fuseau horaire et correlation ID ;
- références des transactions, agrégats et snapshots consommés ;
- métriques courantes, précédentes et historiques ;
- signaux, seuils, confirmations et exclusions ;
- ajustements saisonniers et qualité des données ;
- résultat de chaque condition de règle ;
- composants de confidence et score final ;
- composants de priorité et score final ;
- opportunité produite, statut et produits proposés ;
- actions RM et outcomes ultérieurs.

Une action RM suit le cycle `recommendation → RM action → customer response → commercial outcome`. Les outcomes du MVP sont `CONTACTED`, `MEETING_SCHEDULED`, `OFFER_CREATED`, `CONVERTED`, `REJECTED` et `NOT_RELEVANT`.

Les journaux ne doivent pas exposer de secrets ni de données client non nécessaires. Les accès aux explications et aux audits sont soumis au RBAC et eux-mêmes auditables. Les données de démonstration sont synthétiques ; aucune donnée bancaire réelle ne doit être utilisée.

## 17. Interfaces futures ML

Le MVP conserve une frontière de stratégie permettant d’ajouter une stratégie statistique avancée ou ML sans remplacer les règles déterministes. Les contrats futurs sont conceptuels et doivent être versionnés avant implémentation.

### 17.1 Contrat de features

`FeatureVector` comprendrait `customerId`, `asOfDate`, `featureSetVersion`, les métriques agrégées, les variations, les indicateurs de saisonnalité, les signaux et les métadonnées de qualité. Il ne doit pas contenir de secret ni de donnée non nécessaire au cas d’usage.

### 17.2 Contrat de prédiction

`ModelAssessment` comprendrait `modelId`, `modelVersion`, `score`, `scoreMeaning`, `calibratedAt`, `featureSetVersion`, `explanationReference`, `trainingCutoff`, `driftStatus` et `decisionTrace`. Le champ `scoreMeaning` est obligatoire afin d’interdire de présenter un score de propension comme un score de risque.

### 17.3 Règles de coexistence

- le ML ne décide pas seul d’une opportunité dans le MVP ;
- les garde-fous de données, de confidentialité, d’éligibilité et de libellé restent déterministes ;
- une sortie ML peut enrichir le classement ou proposer une candidate, mais doit être séparée de la décision de règle ;
- toute version de modèle est auditée et reproductible ;
- un modèle en expérimentation utilise un mode `CHALLENGER` sans modifier les recommandations du `CHAMPION` ;
- la performance est évaluée avec les actions et outcomes RM, sans fabriquer un revenu ou une conversion non observée ;
- l’explicabilité de la décision finale distingue les preuves transactionnelles des contributions du modèle.

L’architecture cible est : `Transaction Data → Feature Engineering → Signal Engine → ML Model → Opportunity Engine → Explainability → RM`. L’ajout d’un modèle ne doit pas introduire d’appel LLM externe avec des données client.

## 18. Contrat de tests métier déterministes

Les tests doivent exécuter le moteur avec une date de coupure et une configuration fixes. Toute assertion vérifie également l’explication, la version et l’absence de décision de crédit.

| Test | Entrées principales | Résultat attendu |
|---|---|---|
| A1 | encaissements `+40 %`, fournisseurs `+30 %`, volume `+20 %`, aucun financement récent | `INVESTMENT_FINANCING` |
| B1 | flux internationaux `+50 %`, fréquence en hausse, Trade Finance absent | `TRADE_FINANCE` |
| C1 | excédent persistant, moyenne de solde élevée, utilisation de crédit faible | `CASH_INVESTMENT` |
| D1 | encaissements `-35 %` ou solde `-25 %`, utilisation de crédit `+40 %` | `FINANCIAL_STRESS_SIGNAL` |
| FP1 | hausse saisonnière attendue en décembre | aucune opportunité |
| FP2 | transaction unique de montant élevé | aucune opportunité |
| FP3 | virement international unique sans répétition | aucune `TRADE_FINANCE` |
| FP4 | données insuffisantes ou référentiel produit indisponible | aucune opportunité ; motif explicite |

Les tests d’intégration doivent vérifier la cohérence des snapshots entre analytics, signaux, opportunités et audit. Les tests de non-régression doivent rejouer les mêmes fixtures avec la même configuration et comparer les sorties normalisées.

## 19. Critères d’acceptation du moteur

Le moteur est conforme au MVP lorsque :

1. chaque décision est reproductible avec les mêmes entrées et versions ;
2. les fenêtres `7D`, `30D`, `90D`, `180D` et `365D` sont disponibles ;
3. les quatre règles sont évaluées sans logique de décision dans le frontend ;
4. une saisonnalité connue et un événement ponctuel ne déclenchent pas automatiquement une opportunité ;
5. chaque sortie contient `WHY`, `WHAT`, `WHEN`, `CONFIDENCE` et `EVIDENCE` ;
6. le score de confidence et la priorité sont décomposables ;
7. les seuils et poids sont versionnés, approuvés et auditables ;
8. les événements et actions sont idempotents et traçables ;
9. le signal de tension n’est jamais présenté comme une décision ou un score de crédit ;
10. les interfaces futures ML n’altèrent pas la décision déterministe du MVP ;
11. les scénarios positifs et faux positifs sont couverts par des tests métier ;
12. une décision peut être expliquée à partir des données persistées sans recalcul divergent.

## 20. Références

[1]: file:///home/ubuntu/upload/Pasted_content_100.txt "Requirements — BOA SME Opportunity Intelligence"

Ce document reprend et précise les exigences fonctionnelles et de gouvernance du fichier de requirements fourni. Les paramètres marqués « valeur validée par BOA » doivent faire l’objet d’une décision de configuration avant activation en environnement de démonstration ou d’intégration.

---

**Décision de périmètre :** aucun code n’est inclus dans ce livrable. Les exemples de noms de paramètres et de contrats servent uniquement à formaliser les interfaces et la configuration attendues.

## Décision finale — vocabulaire et transport

Les quatre types sont `INVESTMENT_FINANCING`, `TRADE_FINANCE`, `CASH_INVESTMENT` et `FINANCIAL_STRESS_SIGNAL`. Ce dernier est un signal relationnel à examiner et ne constitue ni un risque, ni une probabilité de défaut, ni une décision de crédit. Les seuils sont des configurations versionnées ; les produits sont résolus par Product Service.

Le chemin MVP est HTTP + outbox locale. Les actions utilisent `ACCEPT_OPPORTUNITY` et `DISMISS_OPPORTUNITY`.

## Références

[1]: file:///home/ubuntu/upload/Pasted_content_100.txt "Cahier d’exigences — BOA SME Opportunity Intelligence"
[2]: ./implementation-blueprint.md "Blueprint d’implémentation exécutable"
[3]: ./data-model.md "Modèle relationnel PostgreSQL"


---

## 21. Politique cible de propension et de fusion

Cette politique précise les interfaces futures lorsqu’un incrément ML est construit. Jusqu’à son acceptation, le mode actif demeure `RULES_ONLY` et les règles déterministes restent seules productrices d’opportunités opérationnelles.

### 21.1 Signification et contrat du score

`propensityScore` estime ou ordonne une propension à un **outcome commercial nommé**, pour un type d’opportunité, un horizon et une population définis. Il est compris entre `0` et `1`. Il n’est une probabilité que si l’interprétation `CALIBRATED_PROBABILITY` et la calibration ont été approuvées ; sinon il sert uniquement au classement.

Le contrat porte cible, horizon, type, modèle/version, feature set/version, snapshot, qualité, dates de génération/expiration et explication. Un score stale, invalide, incompatible ou dépourvu de version ne participe pas à la fusion.

> **Interdiction absolue :** propension, confiance des règles, priorité et fusion ne produisent ni n’alimentent une décision d’octroi, de refus, de limite, de montant, de prix, de solvabilité, de risque ou de défaut. `FINANCIAL_STRESS_SIGNAL` reste un signal relationnel pour préparer un échange humain.

### 21.2 Features admissibles

Seules les features actives du registre, autorisées pour `COMMERCIAL_OPPORTUNITY_PROPENSITY`, sont consommées. Données postérieures à `asOf`, outcomes futurs, notes libres, secrets, identifiants directs inutiles et features exclusivement crédit sont interdits. Une imputation doit être versionnée, expliquée et compatible avec le modèle. Une feature obligatoire absente invalide la prédiction ; aucune valeur neutre silencieuse n’est admise.

### 21.3 Modes de fusion

| Mode | Règle de décision |
|---|---|
| `RULES_ONLY` | résultat actuel, sans dépendance ML |
| `ML_SHADOW` | score persisté et monitoré, sans effet opérationnel |
| `HYBRID_RERANK` | seules les opportunités éligibles par règles sont réordonnées |
| `HYBRID_CANDIDATE` | candidate `TO_REVIEW` gouvernée ; hors MVP initial |

En rerank, la formule de base est `100 × (ruleWeight × ruleConfidence + mlWeight × propensityScore)`, avec poids non négatifs de somme `1`. La politique est versionnée, immuable après activation et approuvée. L’audit distingue confiance, propension, rang fusionné et priorité finale.

### 21.4 Garde-fous, fallback, explication et outcomes

Avant et après fusion, Opportunity Service vérifie scope client, qualité/fraîcheur, finalité, compatibilité, produit actif, exclusions, déduplication, drift, bornes, vocabulaire et versions. Une panne, incompatibilité ou dérive bloquante applique `RULES_ONLY` ou suspend le lot. Aucun score expiré ou inventé n’est utilisé.

L’explication conserve baseline, contributeurs positifs/négatifs, valeurs absentes/imputées, méthode et avertissements. Une contribution est une association, pas une cause. Les outcomes futurs sont gouvernés, pseudonymisés, point-in-time et couverts par consentement ou base approuvée. L’absence d’outcome ne vaut pas non-conversion.

### 21.5 LLM et limites

Le score, la fusion, l’explication et les règles n’appellent aucun LLM. Aucun SDK, modèle, endpoint, secret ou dépendance LLM n’est autorisé. Un futur port narratif pourra seulement résumer une décision persistée et expurgée, sans participer au score, à l’éligibilité ou à la priorité.

Le premier incrément est batch, CPU-only et `ML_SHADOW`. GPU, temps réel, apprentissage en ligne, auto-ML, auto-réentraînement, auto-promotion, causalité et candidate ML opérationnelle sont exclus [4] [5].

## Références de l’extension

[4]: ./ml-engine.md "ML Engine CPU-ready — architecture cible et contrats"
[5]: ./ml-acceptance.md "Acceptation de l’incrément ML"
[6]: ./portfolio-scoping.md "Périmètres agence, chargé de clientèle et portefeuille"
