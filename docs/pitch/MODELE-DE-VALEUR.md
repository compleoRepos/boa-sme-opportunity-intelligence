# Modèle de valeur — BOA SME Opportunity Intelligence

**Statut du document :** proposition de cadre de mesure, sans valeur BOA renseignée.
**Périmètre :** POC/shadow d’aide au travail commercial, sans décision de crédit.
**Règle de lecture :** toute valeur métier, volumétrie, coût, KPI, seuil ou exigence qui n’est pas démontrée par une preuve interne est explicitement marquée **HYPOTHÈSE À VALIDER AVEC BOA**. Les champs de la matrice ci-dessous sont volontairement non renseignés : chaque valeur est **À RENSEIGNER PAR BOA**.

## 1. Objet et principes de mesure

Ce document propose un modèle paramétrable pour estimer et suivre la valeur potentielle de **BOA SME Opportunity Intelligence** auprès des chargés de clientèle (CC), sans transformer une hypothèse commerciale en résultat observé. Le modèle sépare les faits établis par le dépôt, les capacités présentes dans le code, les éléments non implémentés et les décisions à prendre avec BOA.

Le produit est un outil d’identification et de suivi d’opportunités commerciales à partir de signaux et de règles explicables. Il ne prend **aucune décision de crédit**, ne calcule pas de score de risque de crédit et ne doit pas être présenté comme un moteur d’octroi, de refus ou de tarification. Cette frontière est documentée dans les règles et le blueprint d’implémentation ([`docs/business-rules.md`](../business-rules.md), [`docs/implementation-blueprint.md`](../implementation-blueprint.md)).

Le POC utilise un modèle ML classique **CPU-only**, en mode POC/shadow, faute de labels BOA matures. Le dépôt décrit un modèle logistique déterministe et des contrôles de maturité des labels, mais l’entraînement BOA réel et la preuve de performance sur données BOA ne sont pas implémentés. **Aucun LLM ni GPU n’est requis.** La stratégie de secours `RULES_ONLY` doit rester disponible et auditable ([`docs/ml-acceptance.md`](../ml-acceptance.md), [`docs/ml-integration-status.md`](../ml-integration-status.md), [`docs/workstreams/mlops-governance.md`](../workstreams/mlops-governance.md)).

Aucun ROI chiffré, aucune promesse de revenu, de conversion, de productivité ou de performance ML ne peut être déduit du dépôt. Les données visibles dans le POC sont synthétiques et ne constituent pas une preuve de performance commerciale ou ML ([`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md), [`docs/lots/LOT-07-ACCESSIBILITE-RESPONSIVE.md`](../lots/LOT-07-ACCESSIBILITE-RESPONSIVE.md)).

## 2. Légende de statut et niveau de preuve

| Statut | Signification dans ce document | Règle d’interprétation |
|---|---|---|
| **IMPLÉMENTÉ** | Une capacité existe dans le code ou dans les contrats documentés. | Cela ne constitue pas, à lui seul, une preuve de valeur métier BOA, de capacité de production ou de performance commerciale. |
| **PROUVÉ** | Une capacité est étayée par une exécution, un test, une inspection ou un artefact versionné dans le dépôt. | La preuve est limitée à son périmètre, à son environnement et à ses données ; elle ne vaut pas généralisation à BOA. |
| **NON IMPLÉMENTÉ** | La capacité, la mesure ou la preuve attendue n’existe pas dans le dépôt au périmètre audité. | Aucun résultat ne doit être extrapolé ni affiché comme acquis. |
| **À VALIDER** | Une décision, une donnée, un seuil, une définition ou une exigence dépend de BOA. | Toute valeur correspondante est **HYPOTHÈSE À VALIDER AVEC BOA** et doit être fournie, approuvée et sourcée par BOA. |

## 3. Ce que le dépôt établit

| Élément | Statut | Ce que la preuve permet de dire | Limite à ne pas dépasser |
|---|---|---|---|
| Détection d’opportunités à partir de signaux, règles et explications persistées | **IMPLÉMENTÉ / PROUVÉ** | Le modèle de données et les tests couvrent des opportunités, leurs preuves, leurs recommandations et leur cycle de vie ([`docs/business-rules.md`](../business-rules.md), [`docs/data-model.md`](../data-model.md), [`docs/lots/LOT-02-LIFECYCLE-OPPORTUNITY-ACTIONS.md`](../lots/LOT-02-LIFECYCLE-OPPORTUNITY-ACTIONS.md)). | Aucun volume mensuel BOA ni taux de pertinence BOA n’est démontré. **HYPOTHÈSE À VALIDER AVEC BOA.** |
| Consultation par un CC dans son portefeuille et par un responsable dans son périmètre | **IMPLÉMENTÉ / PROUVÉ** | Les contrats et contrôles de périmètre prévoient des accès différenciés ([`docs/portfolio-scoping.md`](../portfolio-scoping.md), [`docs/api.md`](../api.md)). | Le nombre de CC, la taille des portefeuilles et le périmètre d’un pilote BOA restent à définir. **HYPOTHÈSE À VALIDER AVEC BOA.** |
| Actions commerciales et outcomes (`CONTACTED`, `CONVERTED`, etc.) | **IMPLÉMENTÉ / PROUVÉ** | Les actions, outcomes et leur audit sont modélisés ; `value_origin` distingue notamment `OBSERVED`, `SIMULATED` et `NOT_REPORTED` ([`docs/data-model.md`](../data-model.md), [`docs/lots/LOT-02-LIFECYCLE-OPPORTUNITY-ACTIONS.md`](../lots/LOT-02-LIFECYCLE-OPPORTUNITY-ACTIONS.md)). | Aucun taux de contact ou de conversion BOA n’est mesuré dans le dépôt. **HYPOTHÈSE À VALIDER AVEC BOA.** |
| Scoring commercial ML local | **IMPLÉMENTÉ / PROUVÉ dans le POC** | Le dépôt décrit une inférence logistique locale, ses métadonnées de lignée et son mode de repli. | Les labels BOA matures, l’entraînement BOA, la calibration et la performance de production ne sont pas démontrés. Le ML reste **POC/shadow CPU-only**. |
| Décision de crédit | **NON IMPLÉMENTÉE et interdite par le périmètre** | Le périmètre sépare l’opportunité commerciale d’un score ou d’une décision de crédit ([`docs/implementation-blueprint.md`](../implementation-blueprint.md), [`docs/ml-acceptance.md`](../ml-acceptance.md)). | **Aucune décision de crédit.** Aucune utilisation du produit pour accepter, refuser, noter ou tarifer un crédit. |
| LLM ou GPU | **NON REQUIS** | Les critères d’acceptation prévoient un fonctionnement sans LLM, sans GPU obligatoire et sans appel externe ([`docs/ml-acceptance.md`](../ml-acceptance.md)). | Ne pas ajouter de coût LLM/GPU au modèle sans exigence BOA explicitement approuvée. Toute exigence nouvelle serait **HYPOTHÈSE À VALIDER AVEC BOA**. |
| ROI, PNB et valeur financière | **NON IMPLÉMENTÉ / NON MESURÉ** | Le modèle de données interdit l’invention d’une valeur de revenu et conserve l’origine des outcomes. | Aucun ROI, PNB moyen, marge ou coût BOA n’est disponible dans le dépôt. Tous les champs financiers ci-dessous sont **À RENSEIGNER PAR BOA**. |

## 4. Modèle de valeur entièrement paramétrable

### 4.1 Paramètres de périmètre et de volumétrie

La colonne **Valeur BOA** est la seule valeur à utiliser dans un calcul. Tant qu’elle n’est pas remplie et approuvée, le résultat est **NON DISPONIBLE — HYPOTHÈSE À VALIDER AVEC BOA**. Les notations `N`, `p`, `C`, `M` et autres identifiants de formule sont des variables de calcul, pas des valeurs observées.

| Paramètre | Identifiant de formule | Valeur BOA | Unité | Formule ou usage | Source attendue | Propriétaire BOA | Fréquence | Garde-fous |
|---|---|---|---|---|---|---|---|---|
| Nombre de chargés de clientèle (CC) dans le périmètre | `N_CC` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | CC | Paramètre de couverture ; `N_CC = nombre de CC inclus` | Référentiel RH/commercial BOA, périmètre de pilote approuvé | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | À définir par BOA ; revue à chaque changement de périmètre | Définir la population active, les doublons, les remplacements et les exclusions ; ne pas déduire ce nombre du jeu synthétique. |
| Taille totale du portefeuille PME couvert | `N_PME` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | PME | `N_PME = nombre de clients PME autorisés` | Référentiel portefeuille/CRM BOA, extraction datée et contrôlée | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Mensuelle ou selon le cycle de synchronisation approuvé | Périmètre d’accès par CC/agence ; dédoublonnage stable ; date d’observation ; aucune donnée client hors autorisation. |
| Taille moyenne du portefeuille par CC | `M_PME_CC` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | PME/CC | `M_PME_CC = N_PME / N_CC` ; conserver aussi médiane et distribution si BOA les exige | Référentiel portefeuille BOA et table d’affectation CC | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Mensuelle | Signaler les portefeuilles incomplets, les CC sans portefeuille et les affectations temporaires. |
| Période d’observation | `T_OBS` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | jours/mois | Fenêtre commune pour comparer exposition, actions et outcomes | Décision méthodologique BOA approuvée | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Fixée avant le pilote ; révision uniquement gouvernée | Ne pas modifier la fenêtre après observation sans versionner le protocole ; éviter toute fuite temporelle. |
| Fréquence de rafraîchissement des signaux | `F_REFRESH` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | exécutions/période | Détermine les opportunités candidates produites pendant `T_OBS` | Calendrier d’exploitation et sources BOA | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | À définir ; suivi à chaque exécution | Rejouabilité, idempotence, horodatage `asOf`, traçabilité de la source et traitement des échecs. |
| Opportunités détectées par mois | `O_M` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | opportunités/mois | `O_M = nombre d’opportunités créées sur la période` | Journal `OpportunityCreated` ou export BOA contrôlé, après définition des doublons | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Mensuelle | Compter les opportunités uniques selon `deduplication_key` ; séparer ouvertes, expirées et régénérées ; ne pas compter une fixture synthétique comme production. |
| Opportunités présentées à un CC | `O_PRESENTED_M` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | opportunités/mois | `O_PRESENTED_M = opportunités effectivement visibles dans le périmètre CC` | Journaux d’accès/consultation et événements applicatifs BOA | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Mensuelle | Définir « présentée » ; distinguer génération, affichage, ouverture et prise en charge ; respecter la confidentialité et le périmètre. |
| Taux de pertinence | `p_REL` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | % | `p_REL = opportunités jugées pertinentes / opportunités évaluées` | Échantillonnage annoté par BOA, outcome `NOT_RELEVANT` ou protocole de revue approuvé | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Mensuelle pendant le pilote | Définition métier et population d’évaluation approuvées ; annotateurs et désaccords tracés ; ne pas assimiler `confidence` à la pertinence. |

### 4.2 Parcours de contact, conversion et valeur produit

Les taux ci-dessous ne sont pas des sorties du score ML et ne doivent pas être imputés au produit sans protocole de comparaison. Une conversion doit être reliée à une opportunité et à une action, avec une date et une source observée. Si BOA ne fournit pas une valeur observée, inscrire `NOT_REPORTED` plutôt qu’une valeur par défaut, conformément au modèle de données ([`docs/data-model.md`](../data-model.md)).

| Paramètre | Identifiant de formule | Valeur BOA | Unité | Formule ou usage | Source attendue | Propriétaire BOA | Fréquence | Garde-fous |
|---|---|---|---|---|---|---|---|---|
| Taux de contact | `p_CONTACT` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | % | `p_CONTACT = clients contactés / opportunités présentées` | CRM BOA, événements `CustomerContacted`, définition de contact approuvée | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Mensuelle | Définir le contact valide, la fenêtre d’attribution et les tentatives ; exclure les contacts simulés ; contrôler les doublons. |
| Taux de conversion parmi les contacts | `p_CONV_CONTACT` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | % | `p_CONV_CONTACT = conversions / clients contactés` | CRM/outil commercial BOA, outcome `CONVERTED` observé et réconcilié | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Mensuelle et cohorte à maturité définie par BOA | Attribution déterministe à l’opportunité ; fenêtre d’attribution figée ; distinguer offre, acceptation et conversion ; ne pas utiliser `SIMULATED` comme conversion réelle. |
| Taux de conversion parmi les opportunités présentées | `p_CONV_PRESENTED` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | % | `p_CONV_PRESENTED = conversions / opportunités présentées` | CRM BOA et journal applicatif corrélés par `correlationId` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Mensuelle et par cohorte | Vérifier le dénominateur, les opportunités non traitées et les conversions antérieures ; ne pas conclure à un effet causal sans design d’évaluation approuvé. |
| Délai de maturation d’une conversion | `T_MATURITY` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | jours | Définit quand une cohorte est considérée suffisamment mature | Politique CRM/marketing BOA approuvée | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Révision avant chaque pilote | Pas de comparaison de cohortes de maturités différentes ; conserver les censures et les conversions tardives. |
| PNB moyen par produit | `PNB_AVG_PRODUCT[p]` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | devise BOA / produit / période | `PNB_OPP = Σ_p (CONVERSIONS_p × PNB_AVG_PRODUCT[p])` | Système financier/finance BOA, définition PNB approuvée, période et niveau de produit | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Mensuelle ou selon clôture financière | Préciser brut/net, période, produits et règles d’imputation ; exclure toute valeur synthétique ; faire valider par Finance BOA ; aucune promesse de PNB. |
| Produits inclus dans le périmètre de mesure | `PRODUCT_SET` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | liste de `product_id` | Somme restreinte à `p ∈ PRODUCT_SET` | Catalogue produit BOA et décision de périmètre | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | À chaque version du catalogue | Conserver les identifiants techniques ; dater l’éligibilité ; ne pas déduire un produit recommandé d’une valeur financière non fournie. |
| Revenu ou marge incrémentale attribuable | `VALUE_INCREMENTAL` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | devise BOA / période | `VALUE_INCREMENTAL = valeur cohorte exposée − valeur cohorte de comparaison`, selon protocole approuvé | Finance/CRM BOA et plan d’évaluation approuvé | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Selon le protocole d’évaluation | Ne pas appeler cette valeur « ROI » sans définition complète, groupe de comparaison, coûts et fenêtre ; l’attribution causale est **À VALIDER**. |

### 4.3 Coûts d’intégration et d’exploitation

Aucun coût BOA n’est fourni par le dépôt. Les éléments techniques montrent une architecture de services, de persistance, d’audit et d’intégration, mais ne permettent pas de chiffrer l’effort, l’infrastructure, les licences, la sécurité ou l’exploitation chez BOA. Les lignes suivantes doivent donc être complétées par les propriétaires concernés.

| Paramètre | Identifiant de formule | Valeur BOA | Unité | Formule ou usage | Source attendue | Propriétaire BOA | Fréquence | Garde-fous |
|---|---|---|---|---|---|---|---|---|
| Coût d’intégration initiale | `C_INTEGRATION` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | devise BOA | `C_INTEGRATION = C_DATA + C_SECURITY + C_CONNECTORS + C_CHANGE + C_TEST + C_TRAINING` | Chiffrage approuvé par architecture, sécurité, data, intégration et métier | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Une fois par scénario ; rebaselining gouverné | Détailler CAPEX/OPEX, hypothèses de charge, environnements, réversibilité et coûts de conformité ; ne pas omettre les tests d’accès et d’audit. |
| Coût d’exploitation récurrent | `C_RUN_M` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | devise BOA/mois | `C_RUN_M = C_INFRA_M + C_SUPPORT_M + C_MONITORING_M + C_DATA_QUALITY_M + C_SECURITY_M` | FinOps/production BOA, factures ou budgets approuvés | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Mensuelle | Mesurer les coûts réellement facturés ; séparer POC, pilote et production ; aucune hypothèse GPU/LLM, sauf exigence BOA expressément validée. |
| Coût de maintenance et évolution | `C_CHANGE_M` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | devise BOA/mois | `C_CHANGE_M = effort de maintenance + évolutions approuvées` | Backlog, feuilles de temps, contrats et budget BOA | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Mensuelle ou trimestrielle | Distinguer correction, sécurité, conformité, changement de règle et nouvelle fonctionnalité ; ne pas inclure une capacité non demandée. |
| Coût de qualité et gouvernance des données | `C_DATA_GOV_M` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | devise BOA/mois | `C_DATA_GOV_M = ingestion + contrôles + annotation + revue + réconciliation` | Data Office/risque opérationnel BOA | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Mensuelle | Traiter l’absence ou l’immaturité des labels comme un état explicite ; aucune imputation silencieuse ni score par défaut. |
| Coût de formation et conduite du changement | `C_TRAINING_M` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | devise BOA | `C_TRAINING_M = sessions + supports + temps CC/manager` | Plan de déploiement BOA et suivi de participation | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Par vague de pilote | Ne pas convertir automatiquement le temps libéré en gain financier ; documenter la participation et les abandons. |
| Coût total de possession sur la période | `TCO` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | devise BOA / période | `TCO = C_INTEGRATION + Σ_t (C_RUN_t + C_CHANGE_t + C_DATA_GOV_t + C_TRAINING_t)` | Finance/FinOps BOA, période approuvée | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | À la clôture de chaque période | Versionner la période, la devise et les postes ; ne pas comparer à une valeur créée sans protocole d’attribution approuvé. |

### 4.4 KPI de suivi et critères de décision

Les KPI ci-dessous sont des cadres de calcul, pas des cibles. Toute cible, seuil d’alerte ou exigence de passage est **HYPOTHÈSE À VALIDER AVEC BOA** jusqu’à approbation écrite et rattachement à une source.

| KPI | Identifiant | Valeur BOA / seuil | Unité | Formule | Source attendue | Propriétaire BOA | Fréquence | Garde-fous |
|---|---|---|---|---|---|---|---|---|
| Couverture des portefeuilles autorisés | `K_COVERAGE` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | % | `clients traités / clients autorisés` | Logs d’import, portefeuille et contrôle de périmètre | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | À chaque run et mensuelle | Échec de synchronisation explicite ; ne pas traiter un périmètre partiel comme complet. |
| Taux d’opportunités avec preuve exploitable | `K_EVIDENCE` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | % | `opportunités avec evidence complète / opportunités créées` | `opportunity_evidence`, audit de qualité | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | À chaque run | Une preuve doit être persistée et reconstituable ; aucune explication inventée à l’affichage. |
| Taux d’actions dans la fenêtre de suivi | `K_ACTION` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | % | `opportunités ayant une action valide / opportunités présentées` | `opportunity_actions`, CRM BOA | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Mensuelle | Définir la fenêtre, l’action minimale et les exclusions ; séparer action créée et action exécutée. |
| Taux de contact observé | `K_CONTACT` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | % | `CONTACTED observés / opportunités présentées` | Outcomes CRM et audit applicatif | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | Mensuelle | Source observée uniquement ; les outcomes `SIMULATED` et `NOT_REPORTED` sont séparés. |
| Taux de conversion observé | `K_CONVERSION` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | % | `CONVERTED observés / opportunités éligibles à la cohorte` | CRM/finance BOA, rapprochement contrôlé | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | À maturité de cohorte | Ne pas comparer des cohortes non matures ; ne pas attribuer une causalité sans comparaison approuvée. |
| Taux de repli `RULES_ONLY` | `K_RULES_ONLY` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | % | `requêtes en RULES_ONLY / requêtes ML tentées` | Observabilité ML et audit `fallbackMode` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | À chaque run et mensuelle | Cause du repli obligatoire ; aucun score inventé ; le repli ne doit pas être masqué. |
| Taux d’erreurs d’intégration | `K_ERROR` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | % | `requêtes en erreur / requêtes totales` | Observabilité, logs et alertes d’exploitation BOA | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | À chaque run et mensuelle | Définir les erreurs techniques et métier ; conserver `correlationId` ; distinguer retry et duplication. |
| Temps de traitement | `K_LATENCY` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | ms ou s | Percentile convenu sur la durée observée | Traces d’exécution et métrologie BOA | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | À chaque run | Le percentile et le périmètre doivent être approuvés ; aucune cible de performance n’est déduite du POC. |
| Taux de données fraîches et valides | `K_DATA_FRESHNESS` | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | % | `lignes valides et dans la fraîcheur attendue / lignes utilisées` | Contrôles d’intégrité temporelle, sources BOA | **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA** | À chaque import | Rejeter ou isoler les données stales ; documenter `observationAsOf` et la provenance. |

## 5. Formules de synthèse, sans valeur par défaut

Les formules suivantes sont des relations paramétrables. Elles ne produisent un résultat qu’après renseignement et validation de toutes les variables BOA nécessaires.

| Mesure | Formule | Interprétation autorisée |
|---|---|---|
| Opportunités pertinentes par mois | `O_REL_M = O_M × p_REL` | Estimation de volume pertinent uniquement si `O_M` et `p_REL` sont observés selon le même protocole. **HYPOTHÈSE À VALIDER AVEC BOA** tant que les entrées ne sont pas fournies. |
| Contacts attribuables à la cohorte | `CONTACTS_M = O_PRESENTED_M × p_CONTACT` | Compte attendu de contacts dans une cohorte définie ; ne constitue pas un gain de productivité. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| Conversions attendues de la cohorte | `CONVERSIONS_M = O_PRESENTED_M × p_CONTACT × p_CONV_CONTACT` | Projection paramétrique, jamais un résultat mesuré ni une promesse. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| PNB associé aux conversions | `PNB_M = Σ_p (CONVERSIONS_M,p × PNB_AVG_PRODUCT[p])` | Valeur financière à rapprocher des systèmes BOA ; aucune valeur par défaut ni valeur synthétique. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| Valeur nette paramétrique | `NET_VALUE = VALUE_INCREMENTAL − C_INTEGRATION − Σ_t(C_RUN_t + C_CHANGE_t + C_DATA_GOV_t + C_TRAINING_t)` | Calcul possible uniquement après définition de l’attribution, des coûts, de la période et de la devise. **Aucun ROI chiffré ni promesse. HYPOTHÈSE À VALIDER AVEC BOA.** |
| ROI, si BOA l’exige | `ROI = (VALUE_INCREMENTAL − coûts attribuables) / coûts attribuables` | Ne pas publier ni interpréter avant définition BOA de la valeur, des coûts, de la période, du groupe de comparaison et des règles d’attribution. **HYPOTHÈSE À VALIDER AVEC BOA.** |

## 6. Protocole proposé de collecte et d’attribution

Avant toute mesure, BOA doit approuver la population, la période, les produits, la définition d’une opportunité, la définition de la pertinence, la fenêtre de contact, la maturité d’une conversion, la source du PNB et les postes de coûts. Ces éléments sont **HYPOTHÈSE À VALIDER AVEC BOA** tant qu’ils ne sont pas consignés dans une décision BOA versionnée.

La collecte doit conserver la provenance, la date d’observation, le périmètre d’accès et le `correlationId`. Les événements de génération, d’action et d’outcome doivent être rapprochés sans écraser l’évidence originale. Le modèle interne distingue explicitement `OBSERVED`, `SIMULATED` et `NOT_REPORTED`; seul `OBSERVED` peut alimenter une mesure commerciale présentée comme observée. Les règles de données, d’audit et de lignée sont décrites dans [`docs/data-model.md`](../data-model.md), [`docs/ml-acceptance.md`](../ml-acceptance.md) et [`docs/workstreams/mlops-governance.md`](../workstreams/mlops-governance.md).

Pour isoler un effet éventuel du dispositif, BOA doit encore choisir et approuver un protocole d’évaluation — par exemple comparaison temporelle, groupe de comparaison ou autre méthode conforme aux règles internes. Ce choix, la puissance statistique, la durée et les seuils de décision ne sont pas démontrés par le dépôt et sont donc **HYPOTHÈSE À VALIDER AVEC BOA**. En l’absence de protocole approuvé, il est permis de décrire des volumes et outcomes observés, mais pas d’attribuer une valeur incrémentale au produit.

## 7. Garde-fous non négociables

1. **Aucune décision de crédit.** Le produit ne doit ni décider, ni recommander l’acceptation ou le refus d’un crédit, ni produire un score interprétable comme une note de crédit. Le signal de tension financière reste relationnel et commercial, jamais une décision de risque.
2. **ML classique CPU-only, POC/shadow.** En l’absence de labels BOA matures, le ML reste en POC/shadow. Les labels doivent être définis, observés, rattachés temporellement et validés avant toute évolution de mode. Le POC ne justifie aucune revendication de performance de production.
3. **Aucun LLM/GPU requis.** Le chemin nominal et le repli doivent fonctionner sans LLM, sans GPU obligatoire et sans appel externe. `RULES_ONLY` est un mode de secours explicite, pas une valeur de score implicite.
4. **Pas de valeur inventée.** Aucun PNB, revenu, coût, taux ou ROI ne doit être complété par une moyenne, une valeur synthétique ou une valeur par défaut. Une absence de mesure doit rester `NOT_REPORTED` ou **À RENSEIGNER PAR BOA**.
5. **Traçabilité et périmètre.** Toute mesure doit être reliée à une source, un horodatage, un périmètre et un propriétaire. Les accès CC/agence doivent rester limités au portefeuille autorisé ; les données synthétiques ne doivent pas être présentées comme BOA.
6. **Séparation valeur / score.** `confidence`, `priorityScore` et les métadonnées ML sont des éléments de classement ou d’explication technique ; ils ne sont ni un taux de pertinence, ni un taux de conversion, ni une valeur financière.
7. **Décision de passage.** Toute cible, tout seuil d’alerte, toute exigence de disponibilité, de volume, de performance, de conformité ou de sécurité ajoutée au pilote est **HYPOTHÈSE À VALIDER AVEC BOA** jusqu’à approbation et preuve correspondante.

## 8. Registre des décisions ouvertes à BOA

| Décision ouverte | Statut | Décideur attendu | Preuve attendue avant utilisation |
|---|---|---|---|
| Population des CC et portefeuille PME du pilote | **À VALIDER** | BOA métier, distribution et data | Extraction datée, périmètre approuvé et règles d’affectation |
| Définition opérationnelle d’une opportunité détectée, présentée et pertinente | **À VALIDER** | BOA métier | Dictionnaire métier et protocole d’annotation |
| Définition d’un contact et d’une conversion | **À VALIDER** | BOA métier/CRM | Mapping CRM, fenêtre d’attribution et règles de dédoublonnage |
| Sources et définition du PNB moyen par produit | **À VALIDER** | BOA Finance et propriétaires produits | Référentiel produit, méthode de calcul et rapprochement financier |
| Postes de coûts d’intégration, d’exploitation et de gouvernance | **À VALIDER** | BOA Architecture, FinOps, Sécurité et Data | Chiffrage approuvé, période et hypothèses versionnées |
| Méthode d’évaluation de la valeur incrémentale | **À VALIDER** | BOA Data/Finance/Risque et métier | Plan d’évaluation approuvé ; groupe de comparaison ou méthode retenue |
| Maturité suffisante des labels BOA pour quitter le shadow | **À VALIDER** | BOA Data Science, Gouvernance et métier | Définition de label, couverture, qualité, split temporel, validation et approbation |
| Seuils de qualité, pertinence, conversion, fraîcheur, latence et repli | **À VALIDER** | Propriétaires BOA concernés | Registre de seuils signé et métriques observables |
| Conditions d’un éventuel passage au-delà de `ML_SHADOW` | **À VALIDER** | Comité de gouvernance BOA | Evidence pack, validation indépendante, rollback `RULES_ONLY` et décision formelle |

## 9. Références internes

- [`README.md`](../../README.md) — démarrage et périmètre du dépôt.
- [`docs/business-rules.md`](../business-rules.md) — règles de génération et limites du domaine.
- [`docs/data-model.md`](../data-model.md) — opportunités, actions, outcomes, provenance et audit.
- [`docs/implementation-blueprint.md`](../implementation-blueprint.md) — architecture cible, contrôles et limites du MVP.
- [`docs/ml-acceptance.md`](../ml-acceptance.md) — critères d’acceptation, shadow, fallback et interdiction de décision de crédit.
- [`docs/ml-integration-status.md`](../ml-integration-status.md) — état de l’intégration ML et nature synthétique du dataset du POC.
- [`docs/workstreams/mlops-governance.md`](../workstreams/mlops-governance.md) — lignée, labels et gouvernance ML.
- [`docs/portfolio-scoping.md`](../portfolio-scoping.md) — périmètres CC, agence et analyste.
- [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md) — état des preuves et limites.
- [`docs/lots/LOT-02-LIFECYCLE-OPPORTUNITY-ACTIONS.md`](../lots/LOT-02-LIFECYCLE-OPPORTUNITY-ACTIONS.md) — cycle de vie des opportunités et actions.
- [`docs/lots/LOT-07-ACCESSIBILITE-RESPONSIVE.md`](../lots/LOT-07-ACCESSIBILITE-RESPONSIVE.md) — rappel de la nature synthétique des données et du statut POC/shadow.

**Conclusion :** ce document fournit un cadre de mesure paramétrable, pas un résultat commercial. Tant que BOA n’a pas renseigné, sourcé et approuvé les champs de la matrice, toute volumétrie, coût, KPI, seuil, PNB, conversion ou valeur reste **À RENSEIGNER PAR BOA — HYPOTHÈSE À VALIDER AVEC BOA**.
