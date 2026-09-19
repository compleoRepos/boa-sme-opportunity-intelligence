# FAQ comité — BOA SME Opportunity Intelligence

**Périmètre.** Ce document répond aux questions difficiles qu’un comité BOA devrait poser avant de considérer le POC. Il décrit uniquement ce qui est lisible ou démontré dans le dépôt, sans inventer de donnée BOA, de résultat commercial, de coût, de KPI, de seuil approuvé ou d’exigence réglementaire.

**Rappel de décision.** Le produit est une aide commerciale explicable. Il ne prend **aucune décision de crédit**. Le modèle ML est un modèle classique, CPU-only, limité à un **POC assistif et/ou à un mode shadow** tant que les labels BOA matures ne sont pas disponibles. **Aucun LLM ni GPU n’est requis.** La readiness de production est `BLOCKED`.

## Lecture des statuts

| Statut | Sens dans cette FAQ |
|---|---|
| **IMPLÉMENTÉ** | Le code ou le contrat existe dans le dépôt, sans que cela suffise à prouver une homologation de production. |
| **PROUVÉ** | Une validation interne, un test ou un rapport du dépôt démontre le point dans l’environnement indiqué. |
| **NON IMPLÉMENTÉ** | Le dépôt ne fournit pas le composant ou la preuve attendue. |
| **À VALIDER** | Une décision, une donnée, une valeur ou une exigence doit être approuvée par BOA avant usage réel. |

Les mentions **HYPOTHÈSE À VALIDER AVEC BOA** signalent explicitement toute proposition qui ne constitue pas un fait démontré. Les liens cités sont exclusivement internes au dépôt.

## Questions et réponses

### 1. Quelle valeur commerciale peut être revendiquée aujourd’hui ?

**Réponse — PROUVÉ, mais sans KPI de valeur.** Le dépôt démontre une chaîne transactions synthétiques → métriques → signaux → opportunités → actions/outcomes, avec explications et audit. Il ne démontre aucun gain de conversion, de revenu, de productivité ou de satisfaction sur des données BOA ; tout KPI de valeur est donc une **HYPOTHÈSE À VALIDER AVEC BOA**. Source : [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md) et [`docs/business-rules.md`](../business-rules.md).

### 2. Quelles données sont réellement disponibles et peut-on déjà charger des données BOA ?

**Réponse — PROUVÉ pour la démonstration, NON IMPLÉMENTÉ pour BOA.** Le périmètre validé utilise 500 PME exclusivement synthétiques et aucune donnée bancaire réelle. Les adaptateurs CBS/CRM/Payments/Trade réels ne sont pas raccordés ; tout calendrier ou volume de données BOA est une **HYPOTHÈSE À VALIDER AVEC BOA**. Source : [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md) et [`docs/industrialization-governance.md`](../industrialization-governance.md).

### 3. Comment la qualité des données empêche-t-elle une recommandation trompeuse ?

**Réponse — IMPLÉMENTÉ et PROUVÉ sur données synthétiques.** Les contrôles de fraîcheur, couverture, doublons, qualité, cohérence point-in-time et absence de données obligatoires peuvent invalider une sortie ; le système ne remplace pas silencieusement un score manquant par une valeur par défaut. Les taux de qualité observés chez BOA restent **À VALIDER**. Source : [`docs/business-rules.md`](../business-rules.md), [`docs/ml-engine.md`](../ml-engine.md) et [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md).

### 4. Le dispositif de sécurité est-il homologué pour un usage bancaire ?

**Réponse — PROUVÉ pour le POC, À VALIDER pour la production.** Keycloak/OIDC, la validation des tokens, les rôles, les tests de périmètre et la non-divulgation d’erreurs sont couverts dans le POC. Il n’existe toutefois ni homologation de sécurité de production, ni preuve complète de TLS, WAF, coffre de secrets ou configuration réseau BOA ; ces exigences sont **À VALIDER** par BOA. Source : [`docs/security.md`](../security.md) et [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md).

### 5. Où le système est-il hébergé et quelle résidence des données garantit-il ?

**Réponse — PROUVÉ uniquement en local.** Le dépôt fournit Docker Compose avec PostgreSQL, Keycloak, FastAPI et React, mais aucun déploiement AWS, cloud ou datacenter BOA n’est démontré. La plateforme, la résidence, les transferts et les zones de panne sont des **HYPOTHÈSES À VALIDER AVEC BOA**. Source : [`infrastructure/README.md`](../../infrastructure/README.md), [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md) et [`docs/industrialization-governance.md`](../industrialization-governance.md).

### 6. Le RBAC empêche-t-il réellement un chargé de clientèle de voir un autre portefeuille ?

**Réponse — IMPLÉMENTÉ et PROUVÉ dans le POC.** L’autorisation combine rôle, scopes, périmètre organisationnel, affectation temporelle et ownership ; les tests montrent notamment qu’un `RELATIONSHIP_MANAGER` ne peut pas élargir son `relationshipManagerId` ni ouvrir le dashboard agence. Les délégations complexes et politiques ABAC avancées sont **À VALIDER** par BOA. Source : [`docs/portfolio-scoping.md`](../portfolio-scoping.md), [`docs/security.md`](../security.md) et [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md).

### 7. Une décision ou un accès sensible est-il reconstructible après coup ?

**Réponse — IMPLÉMENTÉ et PROUVÉ pour l’audit applicatif.** Les décisions, règles, politiques, modèles, fallbacks et changements de gouvernance conservent acteur ou service, versions, corrélation, résultat et métadonnées append-only. L’immutabilité externe, l’archivage et l’export SIEM ne sont pas démontrés et sont **À VALIDER**. Source : [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md), [`docs/security.md`](../security.md) et [`docs/business-rules.md`](../business-rules.md).

### 8. Que se passe-t-il si le ML, le réseau ou le service de scoring tombe ?

**Réponse — IMPLÉMENTÉ et PROUVÉ.** `ResilientMLClient` applique timeout, retries bornés et circuit breaker ; un timeout, un 5xx, une indisponibilité, un score absent ou obsolète bascule vers `RULES_ONLY` avec `score=None`, sans réutiliser un ancien score. Le circuit breaker reste par processus, limite **À VALIDER** en déploiement multi-réplicas. Source : [`backend/src/boa_oi/resilience/ml_client.py`](../../backend/src/boa_oi/resilience/ml_client.py), [`docs/workstreams/fallback-rules-only.md`](../workstreams/fallback-rules-only.md) et [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md).

### 9. Les sauvegardes et la restauration ont-elles été testées ?

**Réponse — NON IMPLÉMENTÉ.** Le dépôt ne démontre ni sauvegarde de production, ni réplication, ni restauration exécutée, ni rotation des secrets, ni exercice de reprise. Les RPO/RTO, fréquences, rétention et objectifs de reprise sont des **HYPOTHÈSES À VALIDER AVEC BOA**, non des engagements. Source : [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md), [`docs/industrialization-governance.md`](../industrialization-governance.md) et [`docs/audit/workstreams/security-ops.md`](../audit/workstreams/security-ops.md).

### 10. Comment remplacer les mocks par les systèmes BOA sans réécrire le métier ?

**Réponse — IMPLÉMENTÉ pour les contrats, NON IMPLÉMENTÉ pour les raccordements réels.** Les ports et l’adaptateur HTTP normalisent clients, comptes, transactions et produits, avec corrélation et idempotence ; les systèmes CBS, CRM, paiements et trade BOA ne sont pas connectés. Le mapping de champs, les codes d’erreur, la fraîcheur et le plan de repli sont **À VALIDER** par les propriétaires BOA. Source : [`backend/src/boa_oi/adapters/ports.py`](../../backend/src/boa_oi/adapters/ports.py), [`docs/industrialization-governance.md`](../industrialization-governance.md) et [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md).

### 11. Quelle est exactement la place du ML et pourquoi ne pas le mettre en production ?

**Réponse — PROUVÉ en POC, NON AUTORISÉ en production.** Le modèle `sales-propensity-logit-poc-v1` est une régression logistique classique, locale et CPU-only ; il ordonne une propension commerciale et ne décide pas seul. Faute de labels BOA matures et de validation prédictive indépendante, la position de comité doit rester `POC_ASSISTIVE` ou `ML_SHADOW`, avec les règles comme référence ; toute activation opérationnelle supplémentaire est **À VALIDER AVEC BOA**. Source : [`docs/ml-engine.md`](../ml-engine.md), [`docs/ml-acceptance.md`](../ml-acceptance.md) et [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md).

### 12. Une erreur de dépendance peut-elle créer une opportunité ou un score inventé ?

**Réponse — NON, par conception et par test.** En cas de score absent, stale, invalide ou de panne, le résultat est `RULES_ONLY` et les candidats déterministes restent inchangés ; aucun zéro, `0.5`, moyenne sectorielle ou dernière valeur ne masque l’erreur. Les budgets de retry et de timeout en production sont **À VALIDER**. Source : [`docs/workstreams/fallback-rules-only.md`](../workstreams/fallback-rules-only.md) et [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md).

### 13. Comment le drift est-il détecté et qui décide de bloquer le modèle ?

**Réponse — IMPLÉMENTÉ comme socle, NON IMPLÉMENTÉ comme exploitation complète.** Le monitoring distingue drift `DATA`, `FEATURE` et `PREDICTION`, avec états `OK`, `WARNING` et `CRITICAL`; un état bloquant peut sélectionner `RULES_ONLY` et aucune promotion automatique n’est prévue. Les populations de référence, seuils BOA, alertes externes et réactions opérationnelles sont **À VALIDER**. Source : [`docs/workstreams/operations-readiness.md`](../workstreams/operations-readiness.md), [`docs/workstreams/mlops-governance.md`](../workstreams/mlops-governance.md) et [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md).

### 14. Qui fixe les règles, les seuils et les pondérations, et peut-on les modifier sans trace ?

**Réponse — IMPLÉMENTÉ et PROUVÉ pour la gouvernance de configuration.** Les règles et la Scoring Policy sont versionnées, simulables, soumises, approuvées par un autre acteur, publiées, activées et restaurables ; les décisions historiques ne sont pas réécrites. Tout seuil ou poids métier non explicitement approuvé par BOA, y compris les paramètres initiaux documentés, reste une **HYPOTHÈSE À VALIDER AVEC BOA**. Source : [`docs/business-rules.md`](../business-rules.md), [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md) et [`backend/src/boa_oi/scoring_policy/`](../../backend/src/boa_oi/scoring_policy/).

### 15. Comment limiter les faux positifs dus à la saisonnalité ou à un événement ponctuel ?

**Réponse — IMPLÉMENTÉ et PROUVÉ sur cas synthétiques.** Le moteur compare la période courante à la période précédente, à la baseline historique et, lorsque possible, à la même période annuelle ; il exige persistance, couverture et confirmations, et traite séparément transaction unique, virement international isolé et référentiel incomplet. La fréquence acceptable de faux positifs sur données BOA est **À VALIDER**. Source : [`docs/business-rules.md`](../business-rules.md) et [`docs/test-plan.md`](../test-plan.md).

### 16. Comment éviter le harcèlement commercial, les relances répétées et la pression sur une PME ?

**Réponse — NON IMPLÉMENTÉ comme politique complète.** Le dépôt trace les actions et outcomes et rend une opportunité idempotente, mais ne démontre pas un cooldown métier, un plafond de contacts, une gestion de préférences ou une règle de suppression après refus. Toute durée de cooldown, fréquence de relance, canal et règle d’exclusion sont des **HYPOTHÈSES À VALIDER AVEC BOA** et à faire approuver par les métiers, la conformité et la protection des données. Source : [`docs/business-rules.md`](../business-rules.md), [`docs/portfolio-scoping.md`](../portfolio-scoping.md) et [`backend/src/boa_oi/action_api.py`](../../backend/src/boa_oi/action_api.py).

### 17. Le système peut-il influencer une décision de crédit, même indirectement ?

**Réponse — NON, explicitement.** Le système produit une propension commerciale ou un signal relationnel `FINANCIAL_STRESS_SIGNAL` à examiner par un humain ; il ne produit ni risque de défaut, ni score de crédit, ni décision d’octroi, de refus, de limite, de prix ou de montant. Toute extension vers le crédit est hors périmètre et **À VALIDER** séparément par BOA. Source : [`README.md`](../../README.md), [`docs/ml-engine.md`](../ml-engine.md) et [`docs/business-rules.md`](../business-rules.md).

### 18. Pourquoi aucun LLM ou GPU n’est-il nécessaire ?

**Réponse — PROUVÉ.** Les explications sont structurées et déterministes, l’inférence est une fonction logistique locale sur CPU, et les contrôles internes ne trouvent aucune dépendance runtime LLM, CUDA ou GPU. Un futur `OpportunityNarrativePort` est seulement conceptuel et ne pourrait pas modifier score, éligibilité ou priorité ; toute activation serait **À VALIDER** par une décision d’architecture BOA. Source : [`docs/ml-engine.md`](../ml-engine.md), [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md) et [`docs/roadmap.md`](../roadmap.md).

### 19. Quelle performance est réellement démontrée et quel SLO peut-on annoncer ?

**Réponse — PROUVÉ à une échelle de démonstration seulement.** Le rapport final indique un batch de 500 PME synthétiques exécuté en 585 secondes dans le sandbox, sans en faire un SLO BOA ni un benchmark de production ; les essais 1 000 et 5 000 PME ne sont pas exécutés. Tout p95, débit, concurrence, volumétrie cible ou SLO est une **HYPOTHÈSE À VALIDER AVEC BOA** par une campagne de charge représentative. Source : [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md) et [`docs/test-plan.md`](../test-plan.md).

### 20. Quel est le coût total de possession du dispositif ?

**Réponse — NON MESURÉ et donc non chiffrable honnêtement.** Le dépôt ne contient ni tarif d’infrastructure BOA, ni coût d’exploitation, ni coût de raccordement, ni coût de support, ni budget de sécurité ou de reprise. L’absence de GPU et de LLM est un choix d’architecture, pas une économie mesurée ; tout montant ou ROI est une **HYPOTHÈSE À VALIDER AVEC BOA**. Source : [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md), [`docs/ml-engine.md`](../ml-engine.md) et [`docs/industrialization-governance.md`](../industrialization-governance.md).

### 21. Peut-on revenir en arrière après une mauvaise règle, politique ou version de modèle ?

**Réponse — IMPLÉMENTÉ et PROUVÉ pour les registres gouvernés.** La Scoring Policy possède un workflow avec rollback, et le Model Registry retire le champion précédent puis peut restaurer une version approuvée ; les règles et décisions historiques restent versionnées. La réversibilité des raccordements SI réels, des migrations de données et d’une release d’infrastructure est **À VALIDER** par BOA. Source : [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md), [`docs/workstreams/mlops-governance.md`](../workstreams/mlops-governance.md) et [`docs/industrialization-governance.md`](../industrialization-governance.md).

### 22. Quels moyens d’exploitation et d’alerte sont disponibles au quotidien ?

**Réponse — IMPLÉMENTÉ comme contrat, PARTIELLEMENT PROUVÉ comme exploitation.** Readiness, métriques de latence/erreurs/volume/fallback, snapshots de monitoring et événements structurés existent ; aucun backend centralisé de logs/traces, canal d’alerte externe ou politique de rétention approuvée n’est démontré. L’astreinte, les seuils d’alerte et les runbooks sont **À VALIDER**. Source : [`docs/workstreams/operations-readiness.md`](../workstreams/operations-readiness.md) et [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md).

### 23. À quoi ressemblerait un pilote BOA prudent et que prouve le dépôt à ce sujet ?

**Réponse — À VALIDER, aucun pilote BOA réel n’étant démontré.** Le dépôt propose des portes réversibles : données gouvernées, shadow ML, comparaison aux règles, monitoring, puis éventuelle activation limitée après acceptation. Le seul résultat prouvé est un POC sur données synthétiques ; population, durée, périmètre, critères de succès, groupes de contrôle et KPI du pilote sont des **HYPOTHÈSES À VALIDER AVEC BOA**. Source : [`docs/roadmap.md`](../roadmap.md), [`docs/ml-acceptance.md`](../ml-acceptance.md) et [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md).

### 24. Quelles exigences réglementaires sont déjà couvertes ?

**Réponse — Aucune conformité réglementaire ne doit être déclarée sur la seule base du dépôt.** La gouvernance DPO/data est explicitement `BLOCKED`, et la base de traitement, les droits, la conservation, les transferts, la classification et les usages autorisés restent à examiner. Toute affirmation réglementaire est **À CONFIRMER PAR LA CONFORMITÉ BOA**; aucun texte externe non vérifié n’est cité ici. Source : [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md) et [`docs/industrialization-governance.md`](../industrialization-governance.md).

### 25. Les labels et outcomes sont-ils assez matures pour entraîner un modèle BOA ?

**Réponse — NON.** Le mécanisme d’outcomes est structuré et distingue `OBSERVED`, `SIMULATED` et `NOT_REPORTED`, mais la preuve finale ne contient que des outcomes synthétiques, avec `automaticTraining=false` et `trainingReady=false`. La définition, maturité, représentativité et gouvernance de labels BOA sont **À VALIDER** avant tout entraînement. Source : [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md), [`docs/ml-engine.md`](../ml-engine.md) et [`docs/workstreams/mlops-governance.md`](../workstreams/mlops-governance.md).

### 26. Une explication de modèle est-elle une preuve causale de besoin client ?

**Réponse — NON.** L’explication expose baseline, contributeurs, features manquantes, qualité et versions ; une contribution décrit une association avec la sortie du modèle, pas une cause du comportement du client. La qualification finale appartient au chargé de clientèle et doit rester distincte de l’explication technique. Source : [`docs/ml-engine.md`](../ml-engine.md) et [`docs/business-rules.md`](../business-rules.md).

### 27. Les frontières SQL et la minimisation sont-elles prêtes pour des données sensibles ?

**Réponse — PARTIELLEMENT PROUVÉ, NON PRÊT pour la production.** Le chemin Feature Store–ML utilise des contrats HTTP authentifiés et le navigateur n’accède pas à PostgreSQL, mais des lectures SQL transverses subsistent pour Portfolio, Analytics, Action et certains labels. La matrice de privilèges effective, la suppression de `CREATE` aux comptes runtime et les vues minimales sont **À VALIDER** par BOA. Source : [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md), [`docs/industrialization-governance.md`](../industrialization-governance.md) et [`docs/security.md`](../security.md).

### 28. Comment éviter la fuite temporelle entre données, labels et prédictions ?

**Réponse — IMPLÉMENTÉ et PROUVÉ.** Les features portent `featureTimestamp`, `observationAsOf` et `sourcePeriod`, avec contrôle `featureTimestamp <= observationAsOf`; un exemple contaminé est rejeté et les splits temporels contrôlent les bornes. Le cutoff BOA, les fenêtres métier et les règles de conservation des exports restent **À VALIDER**. Source : [`docs/workstreams/mlops-governance.md`](../workstreams/mlops-governance.md), [`backend/src/boa_oi/features/domain.py`](../../backend/src/boa_oi/features/domain.py) et [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md).

### 29. Que se passe-t-il si une source BOA est partielle, lente, dupliquée ou hors service ?

**Réponse — IMPLÉMENTÉ dans les contrats de résilience, NON PROUVÉ sur les SI BOA.** Les imports disposent d’idempotence, corrélation, erreurs explicites, pagination et contrôles de fraîcheur ; une donnée inconnue, absente ou en erreur ne doit pas devenir silencieusement une absence commerciale. Les modes dégradés par source, seuils de fraîcheur et responsabilités de reprise sont **À VALIDER** avec les propriétaires BOA. Source : [`docs/industrialization-governance.md`](../industrialization-governance.md), [`docs/api.md`](../api.md) et [`docs/test-plan.md`](../test-plan.md).

### 30. Quel est le go/no-go défendable devant le comité aujourd’hui ?

**Réponse — GO pour démontrer le POC assistif synthétique ; NO-GO pour la production BOA.** Le rapport final classe la readiness `BLOCKED` en raison notamment des données et labels BOA, de l’homologation DPO/Sécurité, de la HA, des sauvegardes restaurées, des secrets de production et des adaptateurs SI réels. Aucun passage en production, décision de crédit, GPU ou LLM ne doit être inféré sans validations BOA explicites. Source : [`docs/finalization-status-2026-09-19.md`](../finalization-status-2026-09-19.md) et [`README.md`](../../README.md).

## Points ouverts de comité

Les points bloquants à inscrire au registre de décision sont la disponibilité de données BOA gouvernées, la maturité des labels et outcomes, la validation indépendante du cas d’usage ML, la politique de cooldown et de contact, la conformité DPO et la confirmation par la conformité BOA de toute exigence réglementaire, les adaptateurs CBS/CRM/Payments/Trade, les rôles SQL runtime, l’hébergement et la résidence, la HA, les sauvegardes et exercices de restauration, les secrets et TLS, les alertes d’exploitation, les SLO, la capacité cible, le modèle de coûts et les critères d’un pilote réversible. Chacun reste **À VALIDER** et ne doit pas être transformé en engagement BOA sans décision documentée.

**Conclusion.** Le dépôt fournit un socle technique démontré pour une aide commerciale déterministe et un ML classique CPU-only en POC/shadow. Il ne fournit ni preuve de valeur BOA, ni homologation de production, ni décision de crédit. **Aucun LLM et aucun GPU ne sont requis.**
