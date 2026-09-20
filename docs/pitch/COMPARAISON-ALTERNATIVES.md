# Comparaison des alternatives — BOA SME Opportunity Intelligence

## Objet et périmètre

Ce document compare honnêtement cinq voies pour outiller l’identification et le suivi d’opportunités commerciales sur un portefeuille de PME : **le produit présent dans ce dépôt**, un **développement interne**, un **module de CRM éditeur**, une **solution de scoring externe** et le **statu quo outillé**. Il ne constitue ni une décision d’architecture, ni une décision d’achat, ni une autorisation de production.

La comparaison porte sur les critères pertinents pour un établissement bancaire : maîtrise des données, explicabilité, délai, intégration, réversibilité, coûts à chiffrer, dépendance fournisseur, gouvernance, exploitation, personnalisation et risque modèle. Les positions relatives des alternatives sont qualitatives. Aucun score, classement chiffré, coût, délai contractuel, volumétrie BOA, seuil métier ou KPI BOA n’est déduit du dépôt.

> **Règles de lecture.** Toute donnée métier, volumétrie, coût, KPI, seuil ou exigence qui n’est pas démontrée par le dépôt porte explicitement la mention **HYPOTHÈSE À VALIDER AVEC BOA**. Les statuts utilisés sont **IMPLÉMENTÉ**, **PROUVÉ**, **NON IMPLÉMENTÉ** et **À VALIDER**. « PROUVÉ » signifie ici qu’une preuve existe dans le code, les tests ou la documentation du dépôt ; cela ne signifie pas que la capacité est homologuée pour BOA.

## Conclusion de comparaison

Le dépôt démontre un **POC commercial avec ML shadow** combinant règles versionnées, signaux, feature store, score CPU-only observé sans influence, moteur d’opportunités `RULES_ONLY`, portefeuilles, actions, audit et interfaces. Les données de démonstration sont synthétiques et la readiness de production est bloquée : historiques et labels BOA, validation indépendante, gouvernance juridique/DPO, intégrations réelles, HA et restauration ne sont pas démontrés.

Le produit constitue donc une option de **maîtrise fonctionnelle et de réversibilité** à examiner, non une recommandation absolue. Un développement interne peut offrir une maîtrise équivalente, mais avec une charge de construction et d’exploitation à chiffrer. Un module de CRM éditeur peut réduire l’effort d’intégration au CRM concerné, mais sa couverture bancaire, sa maîtrise des données, sa réversibilité et son modèle de scoring doivent être vérifiés. Une solution de scoring externe peut accélérer l’accès à un composant spécialisé, mais augmente potentiellement la dépendance, les questions de transfert de données et le risque de boîte noire. Le statu quo conserve les outils existants, mais ne fournit pas nécessairement une chaîne unifiée, versionnée et auditée ; cette absence n’est pas mesurée dans le dépôt.

**Aucune des cinq options ne doit être présentée comme prenant une décision de crédit.** Dans le produit décrit ici, les règles, signaux et scores servent une aide commerciale : la décision de contact et l’appréciation humaine restent distinctes d’une décision de crédit. Le dépôt ne justifie aucune extension de ce périmètre.

## Ce que le dépôt établit réellement

| Sujet | Statut | Ce qui est établi | Limite à ne pas dépasser |
|---|---|---|---|
| Parcours commercial PME | **IMPLÉMENTÉ / PROUVÉ** | L’architecture expose des services de domaine, une API versionnée, un frontend React/TypeScript, PostgreSQL et une protection OIDC. Le frontend passe par l’API Gateway et ne lit pas directement la base. Voir [`architecture.md`](../../architecture/architecture.md) et [`api.md`](../api.md). | La conformité à l’architecture BOA cible, les SLO et l’homologation restent **À VALIDER**. |
| Règles métier | **IMPLÉMENTÉ / PROUVÉ** | Les règles sont gérées et versionnées avec simulation, activation, audit et mécanismes de rollback décrits dans [`rule-studio.md`](../rule-studio.md) et [`business-rules.md`](../business-rules.md). | Les règles, segments, seuils et pondérations propres à BOA sont **À VALIDER** ; aucune valeur BOA ne doit être supposée. |
| Explications et preuves | **IMPLÉMENTÉ / PROUVÉ** | Le pipeline conserve des composantes, des références de snapshots, des versions de règles/politiques et des traces d’audit selon [`data-model.md`](../data-model.md), [`ml-engine.md`](../ml-engine.md) et [`industrialization-governance.md`](../industrialization-governance.md). | La validation par Risques, Juridique, Audit et les propriétaires métier BOA est **À VALIDER**. |
| Scoring commercial ML | **IMPLÉMENTÉ en `POC_SHADOW` / PROUVÉ techniquement** | Le moteur CPU persiste score, lignée, manifest et évaluation descriptive ; les contraintes imposent règles `1`, ML `0`, et bloquent la promotion locale/synthétique. | La qualité prédictive BOA, la calibration validée, la discrimination, l’uplift, la valeur et toute influence opérationnelle sont **NON IMPLÉMENTÉES / BLOQUÉES**. |
| Labels et entraînement BOA | **NON IMPLÉMENTÉ** | Les labels présents dans le POC sont synthétiques et non training-ready selon [`ml-integration-status.md`](../ml-integration-status.md). | La disponibilité, la définition, la qualité, la finalité et la base de traitement des labels BOA sont **À VALIDER AVEC BOA**. |
| Résilience fonctionnelle | **IMPLÉMENTÉ / PROUVÉ partiellement** | Le dépôt documente un mode de repli `RULES_ONLY` et des contrôles de résilience dans le POC. | La portée exacte du fallback, ses règles de décision, ses alertes et son comportement opérationnel BOA sont **À VALIDER** ; toute absence d’implémentation signalée par le statut final reste **NON IMPLÉMENTÉE**. |
| LLM et GPU | **NON REQUIS** | Le README indique que le LLM est une extension architecturale future, non appelée et non requise par le runtime. Le moteur ML du POC est CPU-ready. | **Aucun LLM ni GPU n’est requis.** Une future proposition LLM devrait être traitée comme un changement de périmètre et soumise à une gouvernance distincte. |
| Décision de crédit | **HORS PÉRIMÈTRE** | Les sorties sont des aides à la prospection et au suivi commercial. | **Aucune décision de crédit n’est prise, automatisée ou déduite par ce produit.** Tout usage crédit est **INTERDIT SANS VALIDATION BOA** et ne peut pas être inféré du dépôt. |
| Intégration bancaire réelle | **NON IMPLÉMENTÉE** | Les adapters et APIs de démonstration sont documentés ; le dépôt distingue les mocks des raccordements réels. Voir [`industrialization-governance.md`](../industrialization-governance.md). | Les contrats, mappings, fréquences, contrôles de qualité et droits d’accès des systèmes BOA sont **À VALIDER AVEC BOA**. |
| Exploitation industrielle | **NON IMPLÉMENTÉE** | La cible de gouvernance est décrite, mais la documentation signale l’absence de haute disponibilité, sauvegarde-restauration, secrets de production, intégration SI bancaire réelle et engagements RPO/RTO. | Les SLO, RPO, RTO, astreintes, niveaux de service, coûts d’exploitation et exigences de sécurité sont **HYPOTHÈSE À VALIDER AVEC BOA**. |

## Comparaison des alternatives selon les critères bancaires

Les formulations ci-dessous décrivent des propriétés généralement attendues d’une option ; elles ne constituent pas des affirmations sur un produit éditeur, un prestataire ou une organisation BOA non documentée. Toute vérification de marché, de contrat, de prix ou de performance est **HYPOTHÈSE À VALIDER AVEC BOA**.

| Critère | Produit du dépôt | Développement interne | Module CRM éditeur | Solution de scoring externe | Statu quo outillé |
|---|---|---|---|---|---|
| **Maîtrise des données** | La maîtrise du schéma, des contrats et des preuves est élevée dans le périmètre développé. Les données de démonstration sont synthétiques. L’usage des données BOA, leur minimisation, conservation, transfert et cloisonnement sont **À VALIDER AVEC BOA**. | Maîtrise potentiellement élevée si BOA impose les architectures, droits et lieux de traitement. La capacité réelle dépend du financement, des compétences et des contrôles internes. **HYPOTHÈSE À VALIDER AVEC BOA**. | Le CRM devient une frontière de données supplémentaire. Les champs réellement accessibles, la rétention, les exports et les copies sont **HYPOTHÈSE À VALIDER AVEC BOA**. | Les données transmises, les transformations, la conservation, la résidence et la suppression doivent être contractuellement vérifiées. **HYPOTHÈSE À VALIDER AVEC BOA**. | Les données restent dans les outils existants, mais leur cohérence, leur fraîcheur et leur traçabilité de bout en bout ne sont pas démontrées par ce dépôt. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| **Explicabilité** | Les règles versionnées, les composantes, les références de snapshot et l’audit sont prévus ou implémentés dans le périmètre POC. La validation métier des explications est **À VALIDER**. | Peut être conçue au niveau voulu, mais doit être spécifiée, testée et maintenue par BOA. **HYPOTHÈSE À VALIDER AVEC BOA**. | Dépend des capacités natives du module et de l’extension possible sans perdre la traçabilité. **HYPOTHÈSE À VALIDER AVEC BOA**. | Dépend de la documentation, des artefacts d’explication et des droits d’audit du fournisseur. **HYPOTHÈSE À VALIDER AVEC BOA**. | L’explication peut rester répartie entre fichiers, requêtes et connaissance des équipes ; son niveau n’est pas mesuré ici. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| **Délai de mise à disposition** | Un POC existe dans le dépôt. Le délai pour le raccorder aux données et contrôles BOA n’est pas fourni. **HYPOTHÈSE À VALIDER AVEC BOA**. | Le délai dépend du périmètre, des équipes et des dépendances SI. Aucun calendrier n’est démontré. **HYPOTHÈSE À VALIDER AVEC BOA**. | Peut réduire le développement d’écrans dans le CRM concerné, mais l’intégration bancaire et la gouvernance restent à traiter. **HYPOTHÈSE À VALIDER AVEC BOA**. | Peut réduire le temps de construction du composant de scoring, mais la qualification, l’intégration et les validations restent nécessaires. **HYPOTHÈSE À VALIDER AVEC BOA**. | Le délai initial de changement peut être faible, mais le dépôt ne mesure ni la charge manuelle ni le délai de traitement actuel. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| **Intégration** | API Gateway, contrats versionnés, services de domaine, OIDC, exports et interfaces sont présents dans le périmètre du POC. Les adapters bancaires réels et certains read models restent **NON IMPLÉMENTÉS**. | Intégration ajustable au SI BOA, au prix d’une construction et d’une maintenance internes. **HYPOTHÈSE À VALIDER AVEC BOA**. | Intégration naturellement centrée sur le CRM ; les flux CBS, paiements, trade, analytique et portefeuille doivent être vérifiés. **HYPOTHÈSE À VALIDER AVEC BOA**. | Requiert des flux entrants et sortants, des contrôles de qualité, de sécurité et de disponibilité. La compatibilité avec les contrats BOA est **À VALIDER**. | Intégration déjà connue des équipes, mais le niveau de standardisation, d’idempotence et de corrélation n’est pas démontré ici. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| **Réversibilité** | Le périmètre est versionné et les règles/politiques prévoient des mécanismes d’activation, désactivation et rollback. La sortie vers les sources BOA et la reprise de l’historique sont **À VALIDER**. | Forte capacité de contrôle si le code, les données et la documentation sont effectivement détenus et maintenus par BOA. **HYPOTHÈSE À VALIDER AVEC BOA**. | Dépend des APIs, du format d’export, de la propriété des configurations et de la capacité à reconstruire les preuves hors CRM. **HYPOTHÈSE À VALIDER AVEC BOA**. | Risque de dépendance aux formats, APIs, modèles et conditions contractuelles. La réversibilité doit être un livrable contractuel. **HYPOTHÈSE À VALIDER AVEC BOA**. | Réversibilité opérationnelle immédiate en conservant l’existant, mais elle peut préserver les limites actuelles. Ces limites ne sont pas mesurées. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| **Coûts à chiffrer** | Coûts de raccordement, sécurité, exploitation, licences éventuelles d’infrastructure, support, tests et maintien en conditions opérationnelles. **HYPOTHÈSE À VALIDER AVEC BOA**. | Coûts de build, recrutement ou mobilisation, exploitation, astreinte, conformité, tests et dette technique. **HYPOTHÈSE À VALIDER AVEC BOA**. | Licences, modules, intégration, personnalisation, stockage, support et éventuels coûts de sortie. **HYPOTHÈSE À VALIDER AVEC BOA**. | Abonnement, consommation, transfert, intégration, audits, support, réversibilité et coût de sortie. **HYPOTHÈSE À VALIDER AVEC BOA**. | Licences et coûts de fonctionnement déjà engagés, plus temps humain et contrôles manuels. Aucun montant ni KPI de charge n’est disponible. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| **Dépendance fournisseur** | Dépendance limitée au runtime documenté, aux composants retenus et aux futurs hébergeurs ; les composants du produit ne garantissent pas à eux seuls une exploitation BOA. **À VALIDER**. | Dépendance moindre à un éditeur, mais dépendance aux compétences, à la capacité interne et aux composants open source demeure. **HYPOTHÈSE À VALIDER AVEC BOA**. | Dépendance au CRM, à sa feuille de route, à ses versions, à ses APIs et à ses conditions contractuelles. **HYPOTHÈSE À VALIDER AVEC BOA**. | Dépendance directe au fournisseur du score, à son modèle, à ses données et à sa continuité de service. **HYPOTHÈSE À VALIDER AVEC BOA**. | Dépendance aux outils déjà en place et aux fournisseurs actuels ; sa cartographie n’est pas fournie dans le dépôt. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| **Gouvernance** | Le dépôt prévoit versionnement, audit, RBAC, séparation des rôles et lignée MLOps de POC. La gouvernance DPO, juridique, modèle et usages BOA est **NON IMPLÉMENTÉE**. | Gouvernance entièrement à définir et à faire vivre par BOA. Cela donne du contrôle, pas une preuve automatique de conformité. **À VALIDER**. | Gouvernance partagée entre BOA et l’éditeur ; les responsabilités sur règles, données, modèle et preuves doivent être contractualisées. **HYPOTHÈSE À VALIDER AVEC BOA**. | Exige accès aux éléments de validation, audits, versions, incidents, changements et sous-traitants du fournisseur. **HYPOTHÈSE À VALIDER AVEC BOA**. | Gouvernance fondée sur les pratiques existantes ; son niveau de formalisation n’est pas démontré. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| **Exploitation** | Docker Compose et les tests du POC facilitent la démonstration. HA, backup/restore, secrets de production, TLS opérationnel, runbooks et RPO/RTO restent **NON IMPLÉMENTÉS**. | BOA contrôle potentiellement les runbooks et l’observabilité, mais doit financer et opérer la chaîne complète. **HYPOTHÈSE À VALIDER AVEC BOA**. | L’exploitation peut être simplifiée dans le périmètre CRM, sans supprimer la responsabilité BOA sur les flux, les données et les usages. **HYPOTHÈSE À VALIDER AVEC BOA**. | Une partie de l’exploitation est externalisée, mais les contrôles de disponibilité, incident, changement et preuve restent nécessaires. **HYPOTHÈSE À VALIDER AVEC BOA**. | Les équipes connaissent l’exploitation actuelle, mais le dépôt n’en donne ni les procédures ni les indicateurs. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| **Personnalisation** | Forte personnalisation du parcours, des règles, des rôles, des preuves et des vues dans le périmètre codé. La personnalisation BOA complète est **À VALIDER**. | Personnalisation maximale en théorie, avec une charge de maintenance correspondante. **HYPOTHÈSE À VALIDER AVEC BOA**. | Personnalisation bornée par le modèle de données, le workflow et les extensions du CRM. **HYPOTHÈSE À VALIDER AVEC BOA**. | Personnalisation bornée par les variables acceptées, les interfaces et la gouvernance du fournisseur. **HYPOTHÈSE À VALIDER AVEC BOA**. | Personnalisation limitée par les outils et pratiques actuels ; le besoin résiduel n’est pas quantifié. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| **Risque modèle** | Le ML est commercial, CPU-only et en POC/shadow ; les labels BOA matures et la validation de production manquent. Le risque modèle est donc explicitement non clos. | BOA maîtrise le choix du modèle, mais porte toute la validation, la surveillance et la responsabilité. **HYPOTHÈSE À VALIDER AVEC BOA**. | Le risque dépend des modèles embarqués, des explications, des données et des possibilités d’audit du module. **HYPOTHÈSE À VALIDER AVEC BOA**. | Le risque inclut la qualité du fournisseur, la transférabilité, la stabilité et l’auditabilité du modèle. **HYPOTHÈSE À VALIDER AVEC BOA**. | Les heuristiques et pratiques existantes peuvent rester non mesurées ; aucun risque modèle n’est quantifié par le dépôt. **HYPOTHÈSE À VALIDER AVEC BOA**. |

## Analyse par alternative

### 1. Produit du dépôt

**Position documentée : IMPLÉMENTÉ pour un POC shadow, PROUVÉ techniquement dans son périmètre, NON IMPLÉMENTÉ pour la production bancaire.** Le produit apporte une chaîne cohérente entre signaux, règles, features, observation de propension, opportunités rules-only, actions et audit. Le modèle de service sépare les domaines et expose des contrats API.

L’avantage comparatif démontré est la cohérence du parcours et la capacité à inspecter les preuves au même endroit. Cet avantage ne doit pas être transformé en promesse de performance commerciale. Le dépôt ne fournit ni données BOA, ni benchmark contre le statu quo, ni KPI de conversion, ni coût total, ni niveau de service BOA. Ces éléments sont **HYPOTHÈSE À VALIDER AVEC BOA**.

Le produit doit rester en **POC/shadow** pour le scoring ML tant que les labels BOA matures, la validation indépendante, la surveillance de dérive et les décisions d’usage ne sont pas établis. Le ML classique est **CPU-only** dans ce périmètre. **Aucun LLM ni GPU n’est requis.**

### 2. Développement interne

Un développement interne peut fournir une maîtrise fine du modèle de données, des contrôles, de la sécurité et des interfaces BOA. Il peut aussi reprendre les principes du dépôt : contrats API, règles versionnées, audit, séparation des rôles et rollback. En contrepartie, BOA porterait la totalité de la construction, de la qualification, de l’exploitation, de la maintenance et de la preuve de conformité. La capacité interne disponible, le coût, le calendrier et le niveau de service sont **HYPOTHÈSE À VALIDER AVEC BOA**.

Cette option n’est pas automatiquement plus réversible que le produit : la réversibilité dépend de la documentation, de la propriété effective du code, des composants retenus, des compétences et de la capacité à reprendre les données et les modèles. Aucun de ces éléments ne peut être chiffré à partir du dépôt.

### 3. Module CRM éditeur

Un module CRM peut être pertinent si le besoin principal est l’activation dans le poste de travail déjà utilisé par les chargés de clientèle. Il peut réduire les interfaces visibles et rapprocher les recommandations du processus commercial. Cette hypothèse ne prouve ni l’accès aux données bancaires nécessaires, ni la compatibilité avec les règles de périmètre BOA, ni l’explicabilité exigée, ni la conservation de preuves hors du CRM.

L’évaluation devrait distinguer ce que le module configure nativement de ce qui requiert une extension, un flux hors CRM ou un service complémentaire. Il faudrait notamment vérifier la version des règles, la traçabilité des changements, la gestion des rôles, les exports, la réversibilité, la localisation des données et la possibilité d’un mode sans score. Ces vérifications sont **À VALIDER AVEC BOA**.

### 4. Solution de scoring externe

Une solution externe peut isoler le composant de scoring et potentiellement réduire le développement du modèle. Elle introduit néanmoins une dépendance sur les variables, les données transmises, les versions, les explications, la disponibilité, la continuité de service et les conditions de sortie. La présence d’un score externe ne résout pas la définition des opportunités, des actions, des responsabilités ou de la gouvernance commerciale.

La diligence devrait exiger au minimum une description des données, des transformations, des limites d’usage, de la validation, de la surveillance, des changements de modèle, des incidents, des sous-traitants, de la rétention et de la restitution des artefacts. Aucun fournisseur, contrat ou niveau de service n’est identifié dans le dépôt. Toute conclusion positive ou négative sur cette famille est donc **HYPOTHÈSE À VALIDER AVEC BOA**.

### 5. Statu quo outillé

Le statu quo peut être rationnel pour préserver la continuité et éviter une intégration prématurée. Il ne fournit toutefois pas, par lui-même, la preuve qu’une chaîne de détection, d’explication, de versionnement, d’audit et de suivi est disponible de bout en bout. Le dépôt ne décrit pas l’outillage actuel de BOA, sa charge opérationnelle, ses contrôles ni ses résultats. Il est donc impossible de quantifier l’écart ou le bénéfice attendu.

Le statu quo doit être comparé avec un inventaire factuel : sources utilisées, traitements manuels, délais observés, contrôles de périmètre, traçabilité, incidents, réconciliations et modes de sortie. Les volumes, coûts, KPI, délais et seuils de cette comparaison sont **HYPOTHÈSE À VALIDER AVEC BOA**.

## Points de décision à instruire avant toute sélection

| Question | Statut | Preuve attendue |
|---|---|---|
| Le besoin est-il strictement commercial et assistif, sans décision de crédit ? | **À VALIDER** | Validation écrite du propriétaire métier, Risques, Juridique et Conformité. |
| Quelles données BOA sont autorisées, pour quelle finalité et avec quelle conservation ? | **À VALIDER** | Cartographie des données, base de traitement, règles de minimisation, accès et conservation. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| Les labels BOA nécessaires au scoring existent-ils, sont-ils définis et suffisamment matures ? | **NON DÉMONTRÉ / À VALIDER** | Échantillon gouverné, définition des outcomes, qualité, biais, temporalité et validation indépendante. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| Le scoring doit-il rester en POC/shadow et sans effet de production ? | **À VALIDER** | Décision de gouvernance modèle précisant le périmètre, les utilisateurs et l’absence d’automatisation. |
| Quel niveau d’explicabilité est requis pour une aide commerciale ? | **À VALIDER** | Critères d’acceptation BOA sur les facteurs, les preuves, l’historique et les limites d’interprétation. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| Quels systèmes sources doivent être raccordés ? | **NON IMPLÉMENTÉ / À VALIDER** | Contrats réels, propriétaire de chaque source, fréquence, fraîcheur, qualité, reprise et gestion des absences. |
| Quels SLO, RPO, RTO et contrôles d’exploitation sont exigés ? | **NON DÉMONTRÉ / À VALIDER** | Exigences approuvées, exercices de restauration, runbooks, observabilité et responsabilités. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| Quel est le coût total de chaque alternative ? | **NON DÉMONTRÉ / À VALIDER** | Chiffrage comparable : build, intégration, licences, exploitation, support, sécurité, migration et sortie. **HYPOTHÈSE À VALIDER AVEC BOA**. |
| Quelles clauses de réversibilité et d’audit sont nécessaires ? | **À VALIDER** | Formats de restitution, délais, propriété des artefacts, accès aux logs, assistance de sortie et tests de reprise. **HYPOTHÈSE À VALIDER AVEC BOA**. |

## Proposition de démarche réversible, sans recommandation absolue

La comparaison ne justifie pas un choix irréversible. Une démarche de décision peut commencer par un cadrage BOA des usages, des données et des contrôles. Elle peut ensuite comparer, sur un même périmètre synthétique ou dûment autorisé, les contrats d’intégration, les explications, les traces d’audit, le mode dégradé, la réversibilité et les coûts complets de chaque alternative. Les critères d’acceptation, la durée de l’essai, la population et les KPI éventuels sont **HYPOTHÈSE À VALIDER AVEC BOA** et ne sont pas proposés comme des seuils par ce document.

Pour le produit du dépôt, l’étape suivante doit rester une qualification contrôlée des adapters et des données, puis une validation indépendante avant tout usage autre que shadow. `RULES_ONLY` est le seul mode opérationnel actuel, non une garantie de performance. Aucun passage en production bancaire ne doit être déduit des tests techniques.

## Références internes

[1]: ../../README.md "README et mode local"
[2]: ../../architecture/architecture.md "Architecture exécutable — BOA SME Opportunity Intelligence"
[3]: ../../architecture/data-flow.md "Flux de données — BOA SME Opportunity Intelligence"
[4]: ../finalization-status-2026-09-19.md "Statut de finalisation et limites de production"
[5]: ../audit/ETAT-REEL-2026-09-19.md "Rapport consolidé État réel"
[6]: ../ml-engine.md "ML Engine CPU-ready"
[7]: ../ml-integration-status.md "Statut d’intégration ML"
[8]: ../ml-acceptance.md "Critères d’acceptation ML"
[9]: ../industrialization-governance.md "Gouvernance d’industrialisation"
[10]: ../api.md "Contrats API-first"
[11]: ../data-model.md "Modèle relationnel PostgreSQL et pipeline de données"
[12]: ../business-rules.md "Règles métier"
[13]: ../rule-studio.md "Rule Engine et Rule Studio"
[14]: ../security.md "Sécurité"
[15]: ../portfolio-scoping.md "Périmètre portefeuille"
[16]: ../test-plan.md "Plan de tests"
[17]: ../../backend/src/boa_oi/ml_engine_api.py "API du moteur ML"
[18]: ../../backend/src/boa_oi/opportunity_api.py "API des opportunités"
[19]: ../../backend/src/boa_oi/rule_management_api.py "API de gestion des règles"
[20]: ../../backend/src/boa_oi/portfolio_api.py "API des portefeuilles"
[21]: ../../backend/src/boa_oi/action_api.py "API des actions et outcomes"
[22]: ../../database/migrations/versions/0004_ml_and_portfolio.py "Migration ML et portefeuille"
[23]: ../../database/migrations/versions/0006_governance_resilience.py "Migration gouvernance et résilience"

*Document rédigé à partir du contenu présent dans le dépôt. Les conclusions BOA, les données réelles, les exigences, les coûts et les KPI restent à établir et à valider par les fonctions compétentes.*
