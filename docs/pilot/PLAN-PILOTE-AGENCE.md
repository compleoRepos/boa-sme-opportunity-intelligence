# Plan pilote — une agence, cinq CC, trois mois

**Identifiant :** `BOA-OI-PILOT-AGENCE-001`
**Version :** 1.0 — document de cadrage à faire approuver
**Périmètre :** une agence BOA, cinq chargés de clientèle PME (CC), douze semaines (`S1` à `S12`)
**Statut du document :** **À VALIDER** par BOA avant tout accès à une donnée réelle ou démarrage opérationnel

## 1. Décision proposée et limites non négociables

Ce document propose un **pilote contrôlé de trois mois** pour vérifier l’utilité opérationnelle de `BOA SME Opportunity Intelligence` auprès d’une agence et de cinq CC volontaires. Le pilote ne constitue ni une homologation bancaire, ni une autorisation de production, ni une preuve de performance commerciale ou de modèle.

Le périmètre proposé est strictement assistif. Il aide le CC à examiner des opportunités commerciales explicables et à consigner les actions et résultats observés. Il ne prend **aucune décision de crédit** : il ne décide ni octroi, ni refus, ni montant, ni limite, ni prix, ni probabilité de défaut. `FINANCIAL_STRESS_SIGNAL` reste un **signal relationnel à examiner**, et ne doit jamais être présenté comme un score de risque ou de crédit. La décision de contact et la qualification du besoin appartiennent au CC.

Le ML classique est limité à une exécution **CPU-only**, en **POC/shadow**, car le dépôt ne démontre pas de labels BOA réels et matures. En `ML_SHADOW`, le score est calculé et audité sans modifier les opportunités, le classement ou les actions visibles. Le mode de référence opérationnel reste `RULES_ONLY`. **Aucun LLM ni GPU n’est requis** ; aucun LLM ne doit être ajouté au pilote et aucune dépendance GPU/CUDA ne doit être introduite.

Toute donnée, volumétrie, coût, KPI, délai cible, seuil métier, population détaillée, règle d’éligibilité, durée de conservation ou exigence de sécurité qui n’est pas démontrée par les éléments BOA approuvés porte la mention **HYPOTHÈSE À VALIDER AVEC BOA**. Les chiffres du dépôt sont des données synthétiques de POC et ne sont pas des résultats du pilote BOA. En particulier, les 500 PME, les 25 CC, les cinq agences, les scénarios et les 614 opportunités décrits dans les documents du dépôt ne doivent pas être extrapolés au pilote.

## 2. Lecture de l’état du dépôt

Le dépôt fournit un socle technique et documentaire qui peut être examiné dans un environnement isolé. La qualification ci-dessous distingue la présence d’un composant, la preuve d’exécution, ce qui n’existe pas encore et ce qui relève d’une décision BOA.

| Domaine | Statut | Ce que le dépôt permet d’affirmer | Limite pour le pilote |
|---|---|---|---|
| Règles métier versionnées, signaux, preuves et explications | **IMPLÉMENTÉ** | Les règles sont configurables et les opportunités portent des éléments `WHY`, `WHAT`, `WHEN`, `CONFIDENCE` et `EVIDENCE` selon [`docs/business-rules.md`](../business-rules.md). | La pertinence dans une population BOA et les seuils de configuration restent **À VALIDER**. |
| Chaîne déterministe `RULES_ONLY` | **IMPLÉMENTÉ** et **PROUVÉ** par les tests et rapports du dépôt | Le fallback explicite est documenté dans [`docs/workstreams/fallback-rules-only.md`](../workstreams/fallback-rules-only.md) et le rapport final décrit les cas de panne, de score absent et de score obsolète. | La preuve du dépôt n’est pas une mesure d’exploitation dans l’agence pilote. |
| Dashboards agence/CC, portefeuille, opportunités et actions | **IMPLÉMENTÉ** au niveau POC | Les rôles et le périmètre sont décrits dans [`docs/portfolio-scoping.md`](../portfolio-scoping.md). | Le périmètre objet par objet, les données et les droits BOA doivent être testés et approuvés avant usage réel. |
| `Scoring Policy` versionnée, audit et rollback métier | **IMPLÉMENTÉ** et **PROUVÉ** par les artefacts de test déclarés | La policy conserve une version et un audit ; elle ne doit pas être modifiée en place. | Le rollback d’infrastructure, de secrets, de schéma et de release n’est pas démontré. |
| ML logistique et Feature Store | **IMPLÉMENTÉ** en POC sur données synthétiques | Le moteur est CPU-ready et le contrat de lignée est décrit dans [`docs/ml-engine.md`](../ml-engine.md). | Les données BOA, labels matures, calibration, matrice `TP/FP/TN/FN` et comparaison ML/règles ne sont pas démontrés. |
| Performance commerciale ou qualité prédictive BOA | **NON IMPLÉMENTÉ** / non démontrée | Le dépôt refuse une revendication de performance de production et marque la readiness production `BLOCKED` dans [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md). | Aucune promesse de gain, de conversion, de rendement ou de précision ne doit figurer dans le pilote. |
| Données BOA réelles et adapters SI BOA | **NON IMPLÉMENTÉ** | Les adapters présents sont mock/synthétiques ; aucune connexion CBS/CRM/Payments/Trade réelle n’est démontrée. | Les sources, contrats, fréquence, fraîcheur et responsabilités BOA sont **À VALIDER**. |
| Sécurité de production, HA, sauvegarde/restauration et secrets | **NON IMPLÉMENTÉ** pour une mise en production bancaire | Les écarts sont détaillés dans [`docs/audit/workstreams/security-ops.md`](../audit/workstreams/security-ops.md). | Le pilote doit rester dans un environnement contrôlé tant que les prérequis BOA ne sont pas approuvés. |
| Plan pilote agence/cinq CC/trois mois | **NON IMPLÉMENTÉ** dans le dépôt avant ce document | Le présent fichier apporte le cadrage demandé. | Il n’est valable qu’après validation formelle de BOA. |

## 3. Objectifs du pilote, exclusivement non financiers

L’objectif premier est d’apprendre si les CC peuvent **identifier, comprendre, prioriser et documenter** des sujets de contact à partir de faits bancaires et de règles explicables, sans automatiser une décision réservée à l’humain. Les objectifs sont non financiers : aucune cible de revenu, de marge, de production de crédit, de montant financé ou de rentabilité n’est incluse.

Les objectifs opérationnels proposés sont les suivants :

1. Vérifier que chaque opportunité visible est rattachée à une règle, une version, une date de coupure, une preuve et un niveau de qualité des données.
2. Vérifier que le CC peut comprendre pourquoi une opportunité est proposée, décider de l’action appropriée ou la déclarer non pertinente, et laisser une trace exploitable.
3. Observer le délai de traitement du portefeuille, depuis la réception de la liste jusqu’à une action documentée, sans imposer de cible avant validation BOA.
4. Mesurer la capacité à distinguer les alertes utiles des alertes non pertinentes, règle par règle, sans appeler « faux positif » une absence de conversion non observée ou non mature.
5. Mesurer la qualité, la fraîcheur et la complétude des données nécessaires, ainsi que le nombre d’alertes bloquées ou dégradées par ces contrôles.
6. Vérifier l’adoption volontaire par les cinq CC et la charge de support, sans confondre une ouverture d’écran avec une utilisation utile.
7. Démontrer que le fallback `RULES_ONLY` permet de poursuivre le parcours déterministe en cas d’indisponibilité, de score absent, de score obsolète ou de problème de dépendance ML.
8. Vérifier que la séparation des rôles, des périmètres, des actions et des audits est respectée dans le périmètre autorisé.

Le mot « conversion » est utilisé ici uniquement pour un **outcome commercial observé et défini par BOA**. Il ne signifie ni accord de crédit ni résultat financier. Une conversion ne peut être mesurée qu’après définition de l’outcome, de la date d’observation et de la période de maturité par BOA.

## 4. Population, périmètre organisationnel et données à confirmer

### 4.1 Population proposée

Le pilote porte sur **une seule agence** et **cinq CC volontaires**, nommés par BOA. La sélection des cinq CC, la taille de leurs portefeuilles, leur secteur, leur ancienneté, leur niveau d’équipement et leur disponibilité ne sont pas définis par le dépôt : ils constituent des **HYPOTHÈSES À VALIDER AVEC BOA**. Aucun nom réel, identifiant client réel ou agence réelle ne doit être écrit dans ce document de cadrage.

Le périmètre technique attendu est `Branch → RelationshipManager → Portfolio → Customer`, avec le rôle technique `BRANCH_MANAGER` pour la supervision d’agence et `RELATIONSHIP_MANAGER` pour le CC, conformément à [`docs/portfolio-scoping.md`](../portfolio-scoping.md). L’accès d’un CC doit être limité à son affectation active. La lecture d’un dashboard d’agence ne doit pas accorder automatiquement le droit d’écrire une action au nom d’un CC.

Le nombre de PME couvertes, le choix d’un éventuel groupe de comparaison, les critères d’exclusion, les clients sans consentement ou base de traitement approuvée, les comptes inactifs, les clients récemment réaffectés et les populations sensibles sont **HYPOTHÈSE À VALIDER AVEC BOA**. Le pilote ne doit pas inventer un groupe témoin ni inclure une population par défaut.

### 4.2 Données nécessaires et statut de confirmation

| Domaine de données | Usage limité dans le pilote | Source et contrat à confirmer | Statut |
|---|---|---|---|
| Affectations agence/CC/portefeuille | Filtrer les accès et rattacher les actions | Customer Service ou source BOA équivalente, avec dates `validFrom`/`validTo`, provenance et watermark | **À VALIDER** — **HYPOTHÈSE À VALIDER AVEC BOA** |
| Clients PME et segment | Décrire le portefeuille et appliquer les règles autorisées | Référentiel client BOA, définition de `customerId`, statuts et segmentation | **À VALIDER** — **HYPOTHÈSE À VALIDER AVEC BOA** |
| Transactions normalisées | Calculer flux, fréquence, fournisseurs et international | Contrat Transaction/Payments, catégories, contreparties, corrections, doublons, retards et devise | **À VALIDER** — **HYPOTHÈSE À VALIDER AVEC BOA** |
| Soldes et lignes existantes | Calculer soldes et utilisation observée | Contrat Account, dates de clôture, devise, limites disponibles et historique autorisé | **À VALIDER** — **HYPOTHÈSE À VALIDER AVEC BOA** |
| Produits détenus et catalogue | Détecter `ABSENT` ou `UNDERUTILIZED` selon le catalogue | Product Catalog approuvé ; `ABSENT` ne doit jamais être déduit d’un référentiel non synchronisé | **À VALIDER** — **HYPOTHÈSE À VALIDER AVEC BOA** |
| Calendrier de complétude et `asOfDate` | Empêcher une décision sur une journée incomplète | Règle de clôture de chaque source, fuseau, fréquence et watermark | **À VALIDER** — **HYPOTHÈSE À VALIDER AVEC BOA** |
| Actions CC | Mesurer `CONTACTED`, suivi et autres événements autorisés | Action Service/CRM, acteur, horodatage, type d’action et notes minimisées | **À VALIDER** — **HYPOTHÈSE À VALIDER AVEC BOA** |
| Outcomes | Observer la pertinence et les conversions définies | Dictionnaire BOA des outcomes, origine `OBSERVED`/`SIMULATED`/`NOT_REPORTED`, maturité et corrections | **À VALIDER** — **HYPOTHÈSE À VALIDER AVEC BOA** |
| Données de formation ML | Non nécessaires pour afficher les règles ; interdites sans gouvernance | Dataset gouverné, finalité, base de traitement, labels matures et manifeste | **NON IMPLÉMENTÉ** dans le dépôt pour BOA ; **À VALIDER** |

Aucune note libre contenant des données sensibles n’est requise pour mesurer le pilote. Les notes, si BOA les autorise, doivent être minimisées, redigées selon sa politique et exclues d’un futur dataset ML initial, conformément aux limites documentées dans [`docs/ml-engine.md`](../ml-engine.md).

### 4.3 Données synthétiques et données réelles

Le dépôt ne contient que des données synthétiques pour le POC. Les valeurs du seed servent à tester la chaîne technique, pas à représenter l’agence pilote. Avant toute importation réelle, BOA doit approuver la finalité, la base de traitement, la minimisation, les habilitations, la rétention, la purge, les transferts et l’environnement. Ces exigences sont des **HYPOTHÈSES À VALIDER AVEC BOA** tant qu’elles ne sont pas approuvées par les fonctions compétentes.

## 5. Mode de fonctionnement du pilote

Le parcours opérationnel proposé est le suivant :

1. Les sources autorisées déposent ou exposent un snapshot avec `asOfDate`, provenance, qualité et watermark.
2. Analytics calcule les fenêtres et baselines configurées ; une donnée insuffisante ou invalide empêche ou dégrade l’opportunité selon la règle publiée.
3. Signal Service et Rule Engine évaluent les règles versionnées et produisent les preuves.
4. Opportunity Service persiste l’opportunité, son explication, ses versions et l’audit.
5. Le dashboard du CC affiche uniquement les clients du périmètre autorisé.
6. Le CC choisit une action autorisée, indique le résultat observé ou déclare l’alerte non pertinente selon le dictionnaire BOA.
7. Les revues hebdomadaires examinent les résultats, les incidents, la qualité et les alertes règle par règle.

Pendant le pilote, la production visible doit rester **`RULES_ONLY`**, sauf décision BOA séparée autorisant un mode de test. Si un test ML est autorisé, il s’exécute en **`ML_SHADOW`** : le score et sa lignée peuvent être monitorés, mais le ML ne crée pas d’opportunité, ne modifie pas le classement visible et ne déclenche aucune action. Il n’existe pas de seuil universel d’activation du score. `HYBRID_RERANK` et `HYBRID_CANDIDATE` sont hors périmètre de ce pilote, sauf nouvelle approbation formelle.

## 6. Critères de succès à définir avant le démarrage

Les critères suivants doivent être remplis, chiffrés lorsque cela est pertinent, approuvés par les propriétaires BOA et figés avant le début de `S1`. Le plan ne fixe **aucun seuil métier BOA**. Toute valeur à renseigner dans la colonne « cible approuvée » est une **HYPOTHÈSE À VALIDER AVEC BOA**. Une cellule vide ne peut pas être transformée en succès après observation.

| Critère | Définition de mesure proposée | Cible approuvée avant `S1` | Preuve attendue | Statut |
|---|---|---|---|---|
| Pertinence CC | Part des opportunités examinées que le CC qualifie selon le vocabulaire BOA (`pertinente`, `à revoir`, `non pertinente`, autre valeur approuvée) | À renseigner par BOA ; aucune valeur fixée ici — **HYPOTHÈSE À VALIDER AVEC BOA** | Export d’actions/outcomes, version du dictionnaire, échantillon audité | **À VALIDER** |
| Délai de traitement | Temps entre la mise à disposition d’une opportunité et la première action ou qualification enregistrée, avec définition du fuseau et des pauses | À renseigner par BOA ; **HYPOTHÈSE À VALIDER AVEC BOA** | Horodatages `generatedAt`, consultation, action et audit | **À VALIDER** |
| Actions | Proportion d’opportunités traitées par une action autorisée, sans assimiler consultation à action | À renseigner par BOA ; **HYPOTHÈSE À VALIDER AVEC BOA** | `opportunity_actions`, acteur, type, horodatage et corrélation | **À VALIDER** |
| Conversions | Nombre et taux d’outcomes `CONVERTED` ou autre outcome approuvé, uniquement après maturité et avec `value_origin = OBSERVED` | Définition, horizon, maturité et cible par BOA ; **HYPOTHÈSE À VALIDER AVEC BOA** | Outcomes source, règle de label, date disponible, exclusions et audit | **À VALIDER** |
| Faux positifs par règle | Alerte déclarée non pertinente selon une définition BOA, séparée par `INVESTMENT_FINANCING`, `TRADE_FINANCE`, `CASH_INVESTMENT` et `FINANCIAL_STRESS_SIGNAL` | Définition, dénominateur, fenêtre et cible par BOA ; **HYPOTHÈSE À VALIDER AVEC BOA** | Revue CC, échantillon et preuves de la règle | **À VALIDER** |
| Qualité des données | Fraîcheur, couverture, nulls, doublons, catégories inconnues, retards, corrections et taux de lignes rejetées par source | Domaines, tolérances et réactions par BOA ; **HYPOTHÈSE À VALIDER AVEC BOA** | Rapport quotidien de qualité et incidents source | **À VALIDER** |
| Adoption | Utilisation active définie par BOA, par CC et par semaine, incluant une action ou qualification utile | Définition et cible par BOA ; **HYPOTHÈSE À VALIDER AVEC BOA** | Journaux minimisés d’accès et actions, sans surveillance individuelle excessive | **À VALIDER** |
| Sécurité et périmètre | Aucun accès hors portefeuille/agence autorisé, aucun secret exposé, aucun usage de `BOA_AUTH_DISABLED` hors environnement local isolé | Conditions de blocage BOA et jeux de tests à approuver ; **HYPOTHÈSE À VALIDER AVEC BOA** | Matrice route × rôle × objet, 401/403/404, logs et revue d’habilitations | **À VALIDER** |
| Explicabilité | Toute opportunité visible comporte règle, version, `asOfDate`, données de preuve et qualité compréhensible par le CC | Exigences de contenu et échantillon de contrôle par BOA ; **HYPOTHÈSE À VALIDER AVEC BOA** | Audit décisionnel et revue utilisateur | **À VALIDER** |
| Disponibilité du service | Disponibilité et réaction aux incidents définies pour le pilote, sans reprendre un SLO inventé du dépôt | Cible, fenêtre d’observation et exclusion des maintenances par BOA ; **HYPOTHÈSE À VALIDER AVEC BOA** | Journaux d’incident, health/readiness et temps de rétablissement | **À VALIDER** |

### 6.1 Règles d’interprétation des résultats

Un résultat positif ne peut être déclaré que si la cible, la population, le dénominateur, la fenêtre, la source et la méthode étaient approuvés avant l’observation. Les taux dont le dénominateur est insuffisant, dont la donnée est non mature ou dont la qualité est invalide sont `N/A`, et non zéro.

L’absence d’un outcome ne vaut pas une non-conversion. Un client non contacté ne peut pas être classé comme refus. Une action simulée porte `value_origin = SIMULATED` et ne doit pas être confondue avec une observation BOA. Cette distinction est cohérente avec le contrat de labels documenté dans [`docs/ml-engine.md`](../ml-engine.md) et [`docs/ml-acceptance.md`](../ml-acceptance.md).

## 7. Mesure de la pertinence et des faux positifs par règle

Le pilote doit mesurer la pertinence avec une revue humaine structurée, et non déduire un faux positif d’un simple absence de conversion. BOA doit choisir une définition stable de « pertinent », « non pertinent », « non observé » et « données insuffisantes ». Tant que cette définition et l’horizon de maturité ne sont pas approuvés, les résultats sont **À VALIDER** et ne peuvent pas être présentés comme une matrice de confusion.

| Règle technique | Revue spécifique proposée | Ce qui peut être appelé « faux positif » après validation BOA | Garde-fou |
|---|---|---|---|
| `INVESTMENT_FINANCING` | Vérifier les trois signaux de croissance, l’historique de financement et la qualité des preuves ; demander au CC si l’échange sur un besoin d’investissement ou de fonds de roulement était pertinent | Une alerte qualifiée non pertinente selon la définition et la fenêtre BOA approuvées, pas une absence de financement | Ne jamais proposer une décision, un montant ou une limite de crédit |
| `TRADE_FINANCE` | Vérifier la répétition des flux internationaux, la fréquence et la couverture produit `ABSENT`/`UNDERUTILIZED` | Une alerte déclarée non pertinente après revue, notamment lorsqu’un flux isolé ou un catalogue incomplet a trompé l’analyse | Un transfert isolé ne doit pas suffire ; un référentiel produit non synchronisé bloque la conclusion |
| `CASH_INVESTMENT` | Vérifier la persistance du surplus, la comparaison historique et l’utilisation observée de ligne | Une alerte déclarée non pertinente parce que l’excédent était ponctuel ou déjà expliqué, selon la règle BOA | Ne pas qualifier une situation de besoin financier sans échange humain ; ne pas transformer le signal en décision |
| `FINANCIAL_STRESS_SIGNAL` | Vérifier les baisses observées, la baseline, la qualité, les changements de compte connus et la pertinence d’un contact relationnel | Un signal déclaré non pertinent pour le contact relationnel, selon la définition BOA ; il ne s’agit jamais de diagnostiquer un risque | Afficher uniquement `FINANCIAL_STRESS_SIGNAL` et « signal relationnel à examiner » |

Pour chaque règle, le rapport doit présenter le nombre d’alertes examinées, le nombre d’alertes avec statut `NON_REPORTED`, la qualité des données, les qualifications CC, les actions et les outcomes matures. Les valeurs et dénominateurs seront ceux approuvés par BOA ; aucun résultat n’est inventé dans ce document.

## 8. Mesure des actions, du traitement et des conversions

### 8.1 Actions et délai de traitement

Le délai de traitement est une mesure opérationnelle, pas une promesse de productivité. BOA doit définir l’événement de départ : création d’une opportunité, publication dans le dashboard ou première visibilité par le CC. BOA doit également définir l’événement de fin : qualification, contact, suivi ou autre action autorisée. Les maintenances, indisponibilités source et pauses doivent être traitées selon une règle approuvée.

Le journal doit conserver au minimum l’identifiant technique de l’opportunité, la règle, la date de génération, l’acteur autorisé, le type d’action, la date d’action, l’outcome éventuel et le `correlationId`, sans note sensible inutile. Le temps de traitement ne doit pas être calculé sur des données synthétiques ou sur un horodatage de démonstration.

### 8.2 Outcomes et conversions

Avant `S1`, BOA doit approuver le dictionnaire des outcomes et son usage : `CONTACTED`, `MEETING_SCHEDULED`, `OFFER_CREATED`, `CONVERTED`, `REJECTED`, `NOT_RELEVANT` et `NOT_REPORTED` sont des identifiants présents dans la documentation technique ; leur définition opérationnelle, leur ordre, leur date de maturité, leur source et leur traitement des corrections restent **HYPOTHÈSE À VALIDER AVEC BOA**.

Une conversion, si BOA choisit d’en mesurer une, doit être non financière dans le tableau de bord du pilote : elle peut être un événement commercial observé approuvé, sans montant ni décision de crédit. L’usage d’un outcome pour évaluer le ML est interdit tant que le label, l’horizon, la population, le cutoff point-in-time, la maturité et la base de traitement ne sont pas approuvés. Avec les seules preuves du dépôt, les labels BOA matures sont absents ; la performance ML demeure `N/A`.

## 9. Qualité des données et contrôle quotidien

La qualité des données est une condition d’éligibilité, pas un détail de reporting. Le contrôle quotidien doit couvrir la fraîcheur et la complétude de chaque source, la date de clôture, les doublons, les corrections, les devises, les catégories inconnues, les comptes inactifs, les valeurs hors bornes, les affectations incohérentes et les événements hors ordre. Les seuils de tolérance et les délais d’escalade sont **HYPOTHÈSE À VALIDER AVEC BOA**.

Chaque lot doit avoir un manifeste avec source, version de contrat, watermark, période, nombre de lignes, hash et statut. Les opportunités dont une donnée obligatoire est invalide, trop récente ou insuffisante doivent être bloquées, marquées comme non éligibles ou dégradées selon la règle approuvée. Une donnée manquante ne doit jamais être remplacée silencieusement par une valeur par défaut.

Le tableau de suivi distingue :

- données reçues et données attendues, avec le dénominateur approuvé ;
- lignes acceptées, rejetées, corrigées ou retardées ;
- taux de couverture par fenêtre utilisée ;
- catégories inconnues et produits non synchronisés ;
- incidents d’affectation ou de périmètre ;
- opportunités produites, bloquées par qualité et générées en `RULES_ONLY`.

Aucune valeur de qualité observée n’est fournie ici. Les volumes et taux seront produits durant le pilote après validation de la méthode.

## 10. Phases et calendrier `Avant/S1-S12`

Le calendrier ci-dessous est un séquencement de contrôle. Il ne constitue pas une promesse de délai technique ou métier. Les jalons qui demandent une validation BOA sont bloquants.

| Période | Phase | Activités principales | Livrable et décision |
|---|---|---|---|
| Avant le démarrage | Cadrage et autorisation | Désigner sponsor, propriétaire métier, cinq CC volontaires, responsable d’agence, sécurité, DPO/data governance et support. Fixer population, finalité, sources, périmètre, outcomes, critères de succès, règles d’arrêt et réversibilité. | Charte signée ; critères et seuils approuvés ; **HYPOTHÈSE À VALIDER AVEC BOA** jusqu’à signature. Sans signature : `STOP`. |
| Avant le démarrage | Préparation technique | Environnement isolé, secrets non DevOnly, authentification active, comptes nominatifs, périmètre agence/CC, imports contrôlés, audit, sauvegarde de l’environnement pilote et procédure de restauration vérifiée selon politique BOA. | Checklist de readiness du pilote. La readiness production reste `BLOCKED`. |
| Avant le démarrage | Préparation data | Manifestes de sources, contrats, `asOfDate`, qualité minimale, population exclue, rétention, purge et procédure d’incident. Aucun import réel avant approbation. | PV d’acceptation data et DPO/Sécurité ; **À VALIDER**. |
| `S1` | Installation contrôlée et baseline | Charger la population approuvée, vérifier affectations, tester les rôles, exécuter `RULES_ONLY` sur une période de référence, former les CC et réaliser un parcours guidé. | Baseline non financière et rapport de contrôles ; aucune cible inventée. Décision de poursuivre ou `STOP`. |
| `S2` | Pilote à blanc | Rejouer un cycle complet sans action client ou avec actions explicitement autorisées. Contrôler preuves, qualité, sécurité, pagination, audit, filtres et fallback. | PV de simulation, incidents classés et corrections de procédure. |
| `S3` | Mise en service contrôlée | Ouvrir l’usage aux cinq CC selon la plage approuvée. Les opportunités visibles restent issues de `RULES_ONLY`. | Premier rapport hebdomadaire ; décision de maintien du périmètre. |
| `S4` | Stabilisation | Examiner compréhension des règles, délais de traitement, actions, données manquantes et incidents d’accès. Ajuster la procédure, pas les seuils métier sans gouvernance. | Compte rendu et registre des décisions ; nouvelle version de règle uniquement si approuvée et auditée. |
| `S5` | Observation active | Poursuivre l’usage et la revue par règle. Échantillonner les alertes positives et non pertinentes. | Tableau de bord hebdomadaire ; résultats provisoires non conclusifs. |
| `S6` | Revue intermédiaire 1 | Comparer les observations aux critères pré-enregistrés ; vérifier la maturité des outcomes et la qualité du dénominateur. | `GO` de continuation, `ADAPTER` de procédure ou `STOP` selon la matrice de décision. |
| `S7` | Observation active | Maintenir la population et le mode assistif ; surveiller la charge support, les réaffectations et le fallback. | Rapport hebdomadaire et audit des habilitations. |
| `S8` | Shadow technique éventuel | Si BOA l’a autorisé et si les prérequis sont réunis, exécuter le ML classique CPU-only en `ML_SHADOW`. Le score reste invisible au classement opérationnel. Sinon rester `RULES_ONLY`. | Rapport de lignée, disponibilité, qualité et drift ; aucune performance BOA revendiquée. |
| `S9` | Observation active | Poursuivre la mesure des actions, de la pertinence et des faux positifs définis par BOA. Contrôler les différences entre `RULES_ONLY` et le shadow sans modifier les actions. | Rapport hebdomadaire ; les résultats ML non matures restent `N/A`. |
| `S10` | Revue intermédiaire 2 | Vérifier la stabilité du processus, la sécurité, la qualité et la capacité à restituer une preuve par opportunité et par action. | Liste de remédiations et décision sur la clôture. |
| `S11` | Consolidation | Geler la collecte selon la politique approuvée, contrôler les outcomes arrivés à maturité, auditer un échantillon, documenter les incidents et préparer les options. | Dossier de clôture provisoire et registre des écarts. |
| `S12` | Clôture et décision | Comparer les résultats aux critères pré-enregistrés, distinguer `PROUVÉ`, `NON PROUVÉ`, `N/A` et hypothèses, décider `GO`, `ADAPTER` ou `STOP`, puis lancer la réversibilité ou la suite approuvée. | Rapport final, décision signée et plan d’actions. |

## 11. Gouvernance hebdomadaire

Une réunion hebdomadaire de 45 à 60 minutes est proposée. Sa durée et sa cadence sont **HYPOTHÈSE À VALIDER AVEC BOA**. La réunion ne doit pas afficher de données client non nécessaires à la décision de gouvernance.

L’ordre du jour est fixe :

1. décisions et actions ouvertes de la semaine précédente ;
2. qualité des données par source et statut des lots ;
3. sécurité, habilitations, incidents d’accès et audit ;
4. volume d’opportunités et répartition par règle, sans interpréter un volume comme une performance ;
5. pertinence CC, délais, actions et outcomes selon les définitions approuvées ;
6. faux positifs opérationnels par règle et échantillon de preuves ;
7. adoption et support, de façon agrégée et proportionnée ;
8. incidents ML shadow, taux de fallback `RULES_ONLY`, drift et absence éventuelle de labels ;
9. risques, décisions demandées à BOA et statut `GO/ADAPTER/STOP`.

Le secrétariat conserve un compte rendu avec décision, propriétaire, échéance, preuve attendue et niveau de confidentialité. Une décision qui modifie une règle, un périmètre, un outcome, une conservation ou un mode ML doit être versionnée, approuvée et auditée. Le CC ne peut pas modifier une règle ou un seuil depuis le parcours opérationnel.

## 12. Support et conduite du changement

Le support est organisé en trois niveaux :

- **Niveau 1 — agence :** le responsable d’agence collecte les questions d’usage, les problèmes de compréhension et les demandes de clarification sans contourner les contrôles de périmètre.
- **Niveau 2 — équipe produit/pilote :** elle qualifie les anomalies fonctionnelles, les données manquantes, les incohérences de règles et les demandes de support. Elle ne change pas silencieusement la configuration.
- **Niveau 3 — sécurité, data governance et exploitation :** ces fonctions traitent les incidents de sécurité, de confidentialité, de source, d’audit et d’infrastructure.

Les horaires, le canal, les délais de prise en charge et la couverture hors heures ouvrées sont **HYPOTHÈSE À VALIDER AVEC BOA**. Chaque ticket doit comporter un niveau d’urgence, un `correlationId`, l’environnement, la règle ou la fonctionnalité concernée, l’impact et la preuve minimale. Il ne doit pas contenir de secret, token, identifiant client inutile ou note libre sensible.

La formation initiale doit expliquer la finalité commerciale, les limites, la lecture d’une preuve, la qualification d’une action, le vocabulaire interdit et le recours au support. Elle doit rappeler qu’un signal n’est pas une décision et que le CC conserve la responsabilité du contact.

## 13. Sécurité, confidentialité et exploitation

Le pilote doit être déployé dans un environnement isolé et approuvé, avec authentification active. `BOA_AUTH_DISABLED=true`, `X-Dev-Principal`, les secrets `DevOnly-*` et les comptes de démonstration ne sont pas autorisés dans un environnement exposé ou contenant une donnée réelle. Le dépôt documente ces limites dans [`docs/audit/workstreams/security-ops.md`](../audit/workstreams/security-ops.md) et [`docs/security.md`](../security.md).

Les contrôles minimaux avant ouverture sont :

| Contrôle | Exigence du pilote | Statut |
|---|---|---|
| Identité | Compte nominatif, OIDC/JWT validé, expiration et audience contrôlées | **À VALIDER** sur l’environnement pilote |
| Périmètre | Intersection rôle, scope, agence, affectation active et finalité | **IMPLÉMENTÉ** dans le contrat ; campagne exhaustive **À VALIDER** |
| Accès horizontal | Un CC ne peut pas deviner `customerId`, `portfolioId`, `relationshipManagerId` ou `branchId` pour élargir son accès | **À PROUVER** par tests 401/403/404 |
| Actions | Le CC agit uniquement sur son portefeuille ; l’écriture agence exige un scope séparé | **À VALIDER** par BOA et par test |
| Secrets | Gestionnaire de secrets, rotation et absence de secrets de développement actifs | **NON IMPLÉMENTÉ** dans la cible de production du dépôt ; prérequis pilote **À VALIDER** |
| Audit | Accès, décisions, actions, changements de règles et fallback corrélés et consultables | **IMPLÉMENTÉ** au niveau POC ; immutabilité forte externe **NON IMPLÉMENTÉE** |
| Données sensibles | Minimisation, classification, chiffrement, rétention et purge approuvés | **À VALIDER** — **HYPOTHÈSE À VALIDER AVEC BOA** |
| Sauvegarde | Sauvegarde et restauration de l’environnement pilote testées avant ouverture | **NON IMPLÉMENTÉ** dans le dépôt ; prérequis **À VALIDER** |
| Observabilité | Journaux corrélés, health/readiness, alertes et runbook accessibles au support | **PARTIELLEMENT IMPLÉMENTÉ** ; dashboards externes et alerting sont **À VALIDER** |

Les cellules d’agrégation qui pourraient réidentifier un client ou un petit groupe doivent être supprimées ou regroupées selon la politique BOA. Les métriques ne doivent pas utiliser `customerId` comme label opérationnel. Toute fuite, accès hors périmètre, secret exposé ou présentation de `FINANCIAL_STRESS_SIGNAL` comme risque ou crédit est un incident bloquant.

## 14. Prérequis de démarrage

Le pilote ne démarre que lorsque les conditions suivantes sont satisfaites et tracées :

1. BOA a approuvé la finalité, la population, l’agence, les cinq CC et les rôles.
2. BOA a approuvé les contrats de données, les sources, le calendrier de disponibilité, `asOfDate`, le watermark, les exclusions et les règles de qualité.
3. BOA a défini les outcomes, la maturité, la non-réponse, les conversions éventuelles et les règles d’échantillonnage.
4. Les critères de succès et leurs seuils, lorsqu’ils sont nécessaires, sont écrits avant `S1`; aucune valeur n’est déduite du dépôt.
5. DPO/juridique, sécurité, data governance et exploitation ont donné leurs validations requises pour la population et l’environnement.
6. Les comptes nominatifs, les rôles et le périmètre effectif ont été testés ; aucun mode d’authentification de développement n’est actif.
7. Les imports, les manifests, la qualité, les erreurs et la reprise sont testés sur un jeu approuvé.
8. Le fallback `RULES_ONLY`, la procédure d’arrêt, la restauration et la réversibilité sont testés.
9. Le support, les responsables d’astreinte éventuels, les canaux d’escalade et le registre des incidents sont opérationnels.
10. Les CC ont reçu la formation sur la finalité, les preuves, les actions, les limites et le vocabulaire interdit.

L’absence d’un prérequis critique entraîne `STOP` ou reporte le démarrage ; elle ne peut pas être compensée par un résultat synthétique.

## 15. Risques et réponses

| Risque | Conséquence | Réponse de pilote | Décision si non maîtrisé |
|---|---|---|---|
| Données BOA incomplètes, retardées ou mal catégorisées | Opportunités non fiables ou absentes | Contrôle qualité, blocage des règles concernées, affichage du statut qualité | `ADAPTER` ou `STOP` selon la criticité validée |
| Périmètre d’accès incorrect | Exposition de données ou action non autorisée | Tests négatifs par rôle et ressource, revue des affectations | `STOP` immédiat |
| Interprétation de `FINANCIAL_STRESS_SIGNAL` comme crédit | Risque de décision ou de communication inappropriée | Libellé imposé, formation, contrôle de contenu et revue hebdomadaire | `STOP` immédiat |
| Absence de labels BOA matures | Performance ML non mesurable | `ML_SHADOW` seulement, métriques ML `N/A`, aucune activation de classement | `RULES_ONLY` |
| Score ML obsolète ou indisponible | Classement non fiable | Fallback explicite `RULES_ONLY`, cause auditée | Continuer en règles seules ou `STOP` si fallback non prouvé |
| Faux positifs opérationnels élevés | Charge inutile et perte de confiance | Revue par règle, échantillon et adaptation approuvée de la configuration | `ADAPTER` ; jamais de seuil improvisé |
| Adoption faible ou charge CC excessive | Processus non utile | Formation, simplification de procédure, mesure du temps et des actions | `ADAPTER` ou `STOP` selon critères pré-approuvés |
| Secret, token ou donnée sensible exposé | Incident de sécurité | Isolement, révocation, conservation de preuve et notification | `STOP` immédiat |
| Indisponibilité source ou infrastructure | Interruption ou données périmées | Fenêtre de maintenance approuvée, readiness et procédure de reprise | `ADAPTER` ou `STOP` |
| Modification non auditée d’une règle ou d’un périmètre | Résultats non comparables | Versioning, approbation séparée, journal de décision | `STOP` du lot concerné |

## 16. Conditions d’arrêt immédiat et suspension

Le sponsor ou le responsable sécurité peut suspendre le pilote immédiatement en cas de :

- accès confirmé ou suspecté hors périmètre agence/CC ;
- exposition d’un secret, token ou donnée client non autorisée ;
- présentation d’une sortie comme décision de crédit, score de risque, probabilité de défaut, montant, limite, prix ou refus ;
- absence d’audit permettant de reconstituer une décision ou une action importante ;
- données sources corrompues, non traçables, trop anciennes ou non couvertes par la politique approuvée ;
- impossibilité de revenir à `RULES_ONLY` quand le ML est activé en shadow ;
- utilisation d’un LLM, d’un GPU/CUDA ou d’un service externe non approuvé ;
- incident légal, DPO, sécurité ou gouvernance demandant l’arrêt ;
- seuil de risque ou critère de succès pré-approuvé atteint, sans que ce seuil soit inventé après coup.

Une suspension conserve les audits et interdit la suppression opportuniste des traces. La reprise exige une analyse de cause, une décision documentée, un test de non-régression et l’accord des responsables concernés.

## 17. Réversibilité et fin du pilote

La réversibilité est conçue pour ne pas réécrire l’historique :

1. arrêter l’exposition opérationnelle et empêcher la création de nouvelles actions dans le périmètre pilote ;
2. repasser explicitement à `RULES_ONLY` ou suspendre le lot si la cause concerne les règles, les données ou la sécurité ;
3. désactiver les imports réels et conserver les manifests, audits et décisions selon la politique BOA ;
4. retirer les habilitations temporaires et les accès des cinq CC selon la date de fin approuvée ;
5. restaurer l’environnement pilote ou le snapshot approuvé si nécessaire, après vérification d’intégrité ;
6. purger ou archiver les données conformément à la décision DPO/data governance ;
7. conserver séparément le rapport final, les preuves, les incidents et la décision `GO/ADAPTER/STOP`.

Le rollback d’une `Scoring Policy`, d’un modèle ou d’une règle ne suffit pas à garantir le rollback d’une image, d’un schéma, d’une configuration Keycloak, d’un secret, d’un frontend ou d’une version Compose. Ces éléments sont **NON IMPLÉMENTÉS** comme capacité de production dans le dépôt et doivent être couverts par la procédure BOA avant un pilote sur données réelles.

## 18. RACI proposé

Les intitulés de responsabilités doivent être associés à des personnes ou fonctions BOA avant `S1`. Les rôles ci-dessous sont une proposition ; leur attribution est **HYPOTHÈSE À VALIDER AVEC BOA**.

| Activité | Sponsor BOA | Métier agence | Responsable d’agence | Cinq CC | Product Owner | Data Governance/DPO | Sécurité | Exploitation | Équipe technique |
|---|---|---|---|---|---|---|---|---|---|
| Autoriser le pilote et les objectifs non financiers | A | C | C | I | R | C | C | C | C |
| Choisir la population et les cinq CC | A | R | R | C | C | C | I | I | I |
| Approuver les sources et finalités de données | A | C | I | I | R | R | C | C | C |
| Définir outcomes, maturité et conversions | A | R | C | C | R | C | I | I | C |
| Préparer les habilitations et périmètres | A | C | R | C | C | C | R | C | R |
| Préparer l’environnement et les secrets | A | I | I | I | C | C | R | R | R |
| Vérifier la qualité des données | I | C | C | I | R | A | C | R | R |
| Exploiter `RULES_ONLY` au quotidien | I | A | R | R | C | I | I | C | C |
| Autoriser ou refuser le `ML_SHADOW` | A | C | I | I | R | C | C | C | R |
| Modifier une règle ou une policy | A | C | I | I | R | C | C | C | R |
| Répondre aux tickets et incidents | A | R | R | C | R | C | R | R | R |
| Conduire la revue hebdomadaire | A | R | R | C | R | C | C | C | C |
| Déclarer un arrêt immédiat de sécurité | I | C | C | I | I | C | A/R | R | C |
| Produire le rapport final | A | R | C | C | R | C | C | C | R |
| Décider `GO`, `ADAPTER` ou `STOP` | A | C | C | I | R | C | C | C | C |

**Légende :** `R` réalise, `A` est responsable de la décision finale, `C` est consulté, `I` est informé. Une personne ne doit pas cumuler des pouvoirs incompatibles d’auteur, d’approbateur et d’opérateur lorsque la séparation est requise par la policy.

## 19. Décision de clôture : `GO`, `ADAPTER` ou `STOP`

La décision de fin est prise en `S12` à partir des critères figés avant le démarrage et des preuves conservées. Elle ne dépend pas d’un chiffre isolé et ne transforme pas une hypothèse en résultat.

| Décision | Conditions minimales proposées | Suite |
|---|---|---|
| **GO** | Critères de succès approuvés atteints ou état jugé acceptable par BOA ; aucun incident bloquant ; sécurité et périmètre prouvés ; qualité et audit suffisants ; CC capables d’expliquer et d’utiliser le parcours ; `RULES_ONLY` réversible ; ML, s’il a été testé, reste explicitement shadow et sans revendication de performance | Étape suivante séparée, avec nouveau périmètre, nouvelles validations et décision d’architecture ; pas de passage automatique en production bancaire |
| **ADAPTER** | Intérêt opérationnel partiel, mais corrections nécessaires sur qualité, formation, règles, support, périmètre ou instrumentation ; aucun incident irréversible ; critères de poursuite et actions de remédiation approuvés | Prolongation ou nouveau pilote avec version, population et critères révisés et approuvés avant reprise |
| **STOP** | Incident de sécurité, de confidentialité ou de périmètre ; crédit ou risque présenté à tort ; absence d’audit ; fallback non fonctionnel ; données non gouvernées ; LLM/GPU non autorisé ; ou critères d’arrêt pré-approuvés atteints | Arrêt, réversibilité, analyse de cause, conservation/purge selon BOA et nouvelle décision formelle avant toute reprise |

`GO` ne signifie pas « production ». Le rapport final doit continuer à mentionner la readiness de production comme bloquée tant que les données et labels BOA, la validation indépendante, la gouvernance DPO/Sécurité, les adapters réels, les secrets, la haute disponibilité et la sauvegarde/restauration ne sont pas démontrés et approuvés.

## 20. Livrables et preuves attendus

Le dossier de pilote doit contenir, au minimum :

| Livrable | Contenu | Statut attendu |
|---|---|---|
| Charte et approbations | Population, finalité, rôles, critères, arrêt, réversibilité | **À VALIDER** avant `S1` |
| Manifeste de données | Sources, versions, watermarks, période, qualité, hashes, exclusions | **À PRODUIRE** par le pilote |
| Matrice d’accès | Routes, rôles, scopes, objets, 401/403/404, tests de devinette d’identifiant | **À PRODUIRE** avant ouverture |
| Journal de règles et policies | Version, auteur, approbateur, motif, date d’effet, rollback éventuel | **IMPLÉMENTÉ** au niveau du socle ; preuve pilote **À PRODUIRE** |
| Rapports hebdomadaires | Qualité, pertinence, délais, actions, outcomes, faux positifs par règle, adoption, incidents | **À PRODUIRE** chaque semaine |
| Rapport shadow éventuel | Score, versions, lignée, qualité, drift, fallback, sans classement opérationnel | **À PRODUIRE** seulement si autorisé ; performance BOA `N/A` sans labels matures |
| Rapport final | Résultats pré-enregistrés, limites, écarts, incidents, décision | **À PRODUIRE** en `S12` |

## 21. Conclusion

Le pilote proposé est un dispositif d’apprentissage opérationnel limité à une agence et cinq CC pendant trois mois. Il doit démontrer la compréhension des preuves, l’utilité du parcours, la traçabilité, la qualité des données, la sécurité et la capacité d’arrêt ; il ne doit pas promettre un gain financier ni une performance ML.

La configuration opérationnelle de référence est `RULES_ONLY`. Le ML classique peut rester en **POC/shadow CPU-only** faute de labels BOA matures, sans effet sur le classement et sans seuil de production. **Aucune décision de crédit, aucun LLM et aucun GPU ne sont requis ou autorisés par ce plan.** Les données, seuils, KPI, conversions, exigences de conservation, critères d’éligibilité et critères d’arrêt non approuvés portent explicitement la mention **HYPOTHÈSE À VALIDER AVEC BOA**.

## Références internes

[1]: ../../README.md "README du dépôt et limites du POC"

[2]: ../business-rules.md "Règles métier et absence de décision de crédit"

[3]: ../data-model.md "Modèle de données et outcomes"

[4]: ../ml-engine.md "ML Engine CPU-ready, mode shadow et limites"

[5]: ../ml-acceptance.md "Portes d’acceptation ML et contrôles bloquants"

[6]: ../portfolio-scoping.md "Périmètres agence, CC et portefeuille"

[7]: ../security.md "Exigences de sécurité"

[8]: ../finalization-status-2026-09-19.md "Statut final, readiness bloquée et preuves POC"

[9]: ../audit/ETAT-REEL-2026-09-19.md "État réel audité du dépôt"

[10]: ../audit/workstreams/data-ml.md "Audit data/ML et absence de labels BOA matures"

[11]: ../audit/workstreams/security-ops.md "Audit sécurité et exploitation"

[12]: ../workstreams/fallback-rules-only.md "Fallback explicite RULES_ONLY"

[13]: ../test-plan.md "Plan de tests métier, sécurité et robustesse"

[14]: ../workstreams/scoring-policy.md "Scoring Policy versionnée et rollback métier"

[15]: ../../backend/src/boa_oi/ml/service.py "Service ML et sérialisation du score"

[16]: ../../backend/src/boa_oi/opportunity_api.py "Service Opportunity et génération d’opportunités"

[17]: ../../backend/src/boa_oi/models/entities.py "Entités persistées, actions, outcomes et audit"

[18]: ../../database/seed/generate.py "Générateur de données synthétiques"

[19]: ../../infrastructure/docker-compose.yml "Composition d’environnement et limites d’exploitation"

[20]: ../../scripts/validate-ml-integration.sh "Script de validation de l’intégration ML"

[21]: ../../tests/e2e/governance.spec.ts "Tests E2E de gouvernance et rollback"

[22]: ../../tests/unit/test_resilience.py "Tests du fallback et de la résilience ML"

[23]: ../../backend/src/boa_oi/platform.py "Authentification, périmètre technique et métriques"

[24]: ../../backend/src/boa_oi/mlops/domain.py "Lignée, labels, métriques et Model Registry"

[25]: ../../backend/src/boa_oi/feature_store_api.py "Feature Store et matérialisation point-in-time"

[26]: ../../backend/src/boa_oi/action_api.py "Actions et outcomes commerciaux"

[27]: ../../scripts/migrate.sh "Migrations et privilèges PostgreSQL"

[28]: ../../infrastructure/keycloak/realm.json "Realm Keycloak et comptes de démonstration"

[29]: ../../infrastructure/.env.example "Variables et secrets de développement"

[30]: ../industrialization-governance.md "Gouvernance d’industrialisation et limites"

[31]: ../DECISIONS.md "Journal de décisions attendu, à créer séparément si BOA le demande"

> Les liens ci-dessus sont des liens relatifs vers les fichiers internes du dépôt. Les statuts du présent document qualifient le dépôt au moment de sa rédaction et ne remplacent pas une validation BOA.
