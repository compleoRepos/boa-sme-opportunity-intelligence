# Statut final de préparation pilote — BOA SME Opportunity Intelligence

**Date :** 23 septembre 2026

## Décision

Le dépôt public constitue un **POC technique gouverné et démontrable** d’intelligence commerciale pour PME. La préparation locale est **PASS sur les périmètres explicitement testés**, dont la chaîne métier, l’isolation CC/agence, l’ingestion, le ML shadow, le catalogue produit indicatif et les parcours E2E. Le produit fonctionne sans LLM et sans GPU. Le modèle classique CPU reste strictement en **`POC_SHADOW`** et la priorité commerciale demeure **`RULES_ONLY`**. Aucune décision de crédit, d’octroi, de refus, de limite ou de tarification n’est produite.

La preuve consolidée FI est `BLOCKED`, et non `READY` : elle relie la révision fonctionnelle, les artefacts locaux et le gate sécurité. Le verdict CI distant est suivi séparément après publication ; aucune action AWS n’est incluse.[18]

La décision de release reste **NO-GO / `BLOCKED_IMAGE_CVES`**. Le scan final sur `9c8edc1f09ce7e545c71856ce430b1e2d89dd73d` détecte 52 constats `HIGH` sans correctif amont connu dans l’image backend, aucun `HIGH`/`CRITICAL` dans l’image frontend et 28 `HIGH`/4 `CRITICAL` dans les trois images externes pinées. Les bases de vulnérabilités sont temporelles ; ce verdict remplace les anciens comptes pour la branche courante.[18]

Le déploiement AWS est **hors périmètre à la demande du propriétaire du projet**. Aucun compte, secret, variable GitHub Actions, rôle OIDC, registre, cluster ou base AWS n’a été utilisé ou créé. Aucun résultat local n’est présenté comme une validation AWS.

## État vérifié

| Domaine | Statut | Résultat vérifié |
|---|---|---|
| Dépôt GitHub | **PASS — branche lot 15 publique** | dépôt public `compleoRepos/boa-sme-opportunity-intelligence`; branche `feat/multibank-visibility`, preuves rattachées au commit fonctionnel `7842902` |
| Stack locale | **PASS** | 23 services définis ; lors du run final, 22 services étaient `healthy` et le worker de notification `running` sans healthcheck |
| Tests backend | **PASS** | 283 tests unitaires ; 10 avertissements non bloquants |
| Frontend | **PASS** | TypeScript, build Vite et 35 tests Vitest répartis dans 9 fichiers |
| E2E | **PASS** | 24/24 parcours Playwright, 0 échec, 0 ignoré et 0 flaky en 107,7 secondes ; mode `DEV_PERSONA`, login navigateur Keycloak non exercé[16] |
| Catalogue produit indicatif | **PASS local** | 28 produits publics, 7 familles, 6 produits Trade Finance, filtre famille, provenance, readiness, scope backend et rejet des codes/détentions inconnus[5][11] |
| Migration catalogue | **PASS local** | `0001→0018`, `0017→0018`, downgrade `0018→0017` et ré-upgrade ; règles synthétiques bornées et règles utilisateur préservées[5] |
| Charge 50 000 PME | **PASS dans le protocole isolé** | 50 000 clients, affectations et opportunités synthétiques ; tous les scénarios dotés d’un seuil passent ; les deux dashboards sans cible sont seulement mesurés[1] |
| Ingestion gouvernée | **PASS local** | contrat versionné, manifeste, quarantaine, rejouabilité, conflit, catégorisation versionnée et claim concurrent atomique[2] |
| ML shadow | **PASS pour le comportement shadow** | chaîne 500 PME, 500 observations shadow, zéro fallback ; priorité inchangée ; manifest et évaluation bloqués faute de labels BOA[3] |
| Visibilité des flux | **PASS local synthétique** | 500 snapshots, trois méthodes actives exercées, règle `FLOW_DOMICILIATION` publiée avec séparation des rôles, 100 recommandations de reconquête, isolation hors portefeuille refusée en 403 et trois captures 1440 × 900[15][16] |
| Financial Intelligence B2B | **PASS local / DEMO READY** | contrat `fi.v1` read-only, rôles exclusifs/client/finalité/grants, isolation Fonds A/B, 6/6 E2E, 334 pytest, migrations 0021 et 20 mesures jusqu’à 500 PME sur `9c8edc1f09ce7e545c71856ce430b1e2d89dd73d`[17][18] |
| Backup/restore | **PASS local** | dump contrôlé, altération détectée, restauration isolée jusqu’à Alembic `0017`, nettoyage et sentinelle vérifiés[4] |
| Readiness opérationnelle | **PASS local** | logs corrélés, métriques, liveness maintenue, readiness `503` lors de la panne DB puis récupération[4] |
| Scans de sécurité | **EXÉCUTION PASS / RELEASE BLOCKED** | Gitleaks : 0 constat sur la worktree et 48 commits non-merge atteignables ; dépendances Python sans vulnérabilité connue, frontend sans `HIGH`/`CRITICAL` ; backend 52 `HIGH`, images externes 28 `HIGH` et 4 `CRITICAL`[18] |
| CI distante du lot 11 | **CANCELLED** | run `35538673248` arrêté à la limite de 60 minutes pendant le job Compose/E2E ; il ne constitue pas un PASS[7] |
| CI distante du catalogue | **CANCELLED** | run `35547449760` sur `0b7b2b5` arrêté après 64 minutes : six jobs amont réussis, `compose-e2e-and-operations` annulé à sa limite de 60 minutes, `quality-gate` en échec et `release-image-gate` ignoré[8] |
| AWS | **HORS PÉRIMÈTRE** | aucun déploiement demandé ; aucune ressource créée |

## Ce qui est prouvé

La chaîne métier du POC relie Rule Studio, Signals, Feature Store, inférence ML shadow, Opportunity Engine et dashboards. Le score est persisté avec `modelVersion`, `featureVersion`, version et hash de dataset, manifest, période et statut de calibration. Opportunity et Portfolio conservent l’observation ML séparée, mais ne l’utilisent ni pour l’éligibilité, ni pour l’ordre, ni comme départage.[3]

Le périmètre d’accès est imposé côté backend. Un chargé de clientèle ne peut pas étendre son portefeuille en modifiant un paramètre de requête ou l’IHM. Le responsable d’agence reçoit une consolidation limitée à son périmètre. L’E2E final couvre également le détournement de la route produits par modification de `customerId`.[12]

Le catalogue est un **référentiel indicatif issu de pages publiques**, pas un catalogue commercial BOA validé. Les critères, ciblages, tarifs, montants, durées et disponibilités sont **HYPOTHÈSE À VALIDER AVEC BOA**. Product Service reste non ready sans les 28 entrées gouvernées, réapplique le scope objet et refuse avant écriture les produits ou détentions inconnus, absents, inactifs ou divergents. Les preuves catalogue, migration et 20 E2E ont été régénérées sur la révision publique exacte `0b7b2b5`.[5][11][12]

Les protocoles 50 000 PME et 500 PME prouvent des exécutions locales synthétiques reproductibles, pas une capacité de production, un SLO bancaire ou une performance prédictive. Les sources BOA réelles, leurs contrats, cadences, volumes et seuils de qualité restent à fournir et approuver.[1][2][3]

## Blocages avant pilote BOA avec données réelles

1. **Sécurité des images :** le statut `BLOCKED_IMAGE_CVES` doit être levé par des images externes corrigées ou par une décision formelle d’acceptation de risque ; le dépôt n’accorde aucune dérogation automatique.[6]
2. **CI distante :** les runs du lot 11 et du catalogue sont `CANCELLED`. Le workflow CI hérité reste strictement inchangé dans le Lot 16, conformément à la décision de publication sans modification CI. Aucun contournement par jeton exposé n’a été utilisé. Les succès locaux ne remplacent pas le verdict distant qui sera observé après publication.[7][8]
3. **Données et interfaces BOA :** contrats sources, accès non productif, mapping, qualité, réconciliation et propriétaires restent à valider.
4. **Identité et secrets :** annuaire, comptes techniques, coffre, certificats, rotation, TLS/mTLS et révocation sont non implémentés sur une cible BOA.
5. **Exploitation cible :** stockage indépendant et chiffré des sauvegardes, rétention, haute disponibilité, supervision centralisée, alerting, SIEM, astreinte et objectifs RPO/RTO/SLO restent à définir.
6. **ML :** les outcomes actuels restent des labels candidats. Sans labels historiques BOA matures, dataset temporel approuvé, calibration et validation indépendante, toute promotion ou influence commerciale reste bloquée.[3]
7. **Conformité :** finalité, minimisation, conservation, base de traitement, résidence, habilitations et procédures d’incident doivent être approuvées par les fonctions BOA compétentes.

## Évolutions Studio ML et visibilité des flux

La branche `feat/ml-studio-parallel` a livré le Studio ML gouverné : entraînement CPU `DEMO_ONLY`, registre et comparaison de modèles, simulation serveur auditée, séparation des rôles Karim/Nadia/Youssef, sept captures 1440 × 900 et E2E multi-rôles. Cette implémentation ne change pas la priorité opérationnelle : `POC_SHADOW`, `RULES_ONLY`, `rules_weight=1`, `ml_weight=0`. Sans labels historiques BOA, validation indépendante G3 et décision formelle, toute promotion réelle reste bloquée.[14]

La branche `feat/multibank-visibility` ajoute la visibilité `HIGH/PARTIAL/LOW/UNKNOWN`, l’historique point-in-time des déclarations, la règle gouvernée `FLOW_DOMICILIATION`, la requalification `ABSENT_OR_ELSEWHERE`, les vues CC/agence et les seuils versionnés. Le run final lié à `7842902` produit 500 snapshots après recalcul intégral avec exclusion stricte de tout statut autre que `BOOKED` : 0 `HIGH`, 50 `PARTIAL`, 50 `LOW` et 400 `UNKNOWN`; les trois méthodes actives sont exercées. Cette distribution et tous les volumes sont exclusivement synthétiques ; les paramètres 0,70/0,30, -10/-25/-5, deux empreintes et 180 jours sont **HYPOTHÈSE À VALIDER AVEC BOA**.[15][16]

## Décision d’usage

**GO** pour une démonstration locale sur données synthétiques, une revue architecture/sécurité, une recette des parcours et la préparation d’un pilote contrôlé.

**NO-GO** pour une release bancaire de production, un branchement aux données BOA réelles ou une activation ML tant que les blocages ci-dessus ne sont pas levés. Le déploiement de démonstration sur Cloud Computer n’est ni une homologation ni une cible BOA. Le plan pilote d’une agence, cinq chargés de clientèle et douze semaines demeure une **proposition à valider avec BOA**, et non une volumétrie ou un engagement approuvé.[9]

La capability Financial Intelligence est **GO pour une démonstration locale contrôlée** sur données synthétiques. Elle ne rend pas le produit production-ready : l’IAM B2B BOA, le consentement, le mTLS, la séparation du propriétaire DBA, le stockage d’audit WORM, le SIEM, les secrets, le pentest, la charge concurrente et l’homologation restent bloquants. Le benchmark 500 PME mesure un P95 de 125,042 secondes et un pic mémoire FI de 286,5 MiB sur 320 MiB (89,53 %) ; ce résultat est une **HYPOTHÈSE À VALIDER AVEC BOA**, pas un SLO ni une preuve de capacité de production.[17][18]

## Références

[1]: lots/LOT-08-CHARGE-50000.md "Lot 08 — validation de charge isolée sur 50 000 PME"
[2]: lots/LOT-09-INGESTION-QUALITE.md "Lot 09 — ingestion gouvernée et qualité Transaction"
[3]: lots/LOT-10-ML-SHADOW-DEFENDABLE.md "Lot 10 — ML shadow défendable"
[4]: lots/LOT-11-INDUSTRIALISATION-EXPLOITATION.md "Lot 11 — industrialisation pilote et exploitation prouvée"
[5]: lots/LOT-12-CATALOGUE-PRODUITS-BOA.md "Lot 12 — catalogue produit public et garde-fous"
[6]: evidence/security/RESULTATS-SCANS-SECURITE.json "Preuve consolidée des scans de sécurité"
[7]: https://github.com/compleoRepos/boa-sme-opportunity-intelligence/actions/runs/35538673248 "GitHub Actions — CI du lot 11"
[8]: https://github.com/compleoRepos/boa-sme-opportunity-intelligence/actions/runs/35547449760 "GitHub Actions — CI du catalogue"
[9]: pilot/PLAN-PILOTE-AGENCE.md "Plan pilote agence"
[10]: https://github.com/compleoRepos/boa-sme-opportunity-intelligence/tree/feat/pilot-readiness "Branche pilote publique"
[11]: evidence/catalog/RESULTATS-CATALOGUE-PRODUITS.json "Preuve catalogue finale"
[12]: evidence/catalog/RESULTATS-PLAYWRIGHT-CATALOGUE.json "Résultats détaillés des vingt E2E"
[13]: evidence/closure/RESULTATS-CLOTURE-PILOTE.json "Preuve consolidée de clôture pilote"
[14]: lots/LOT-14-STUDIO-ML-APERÇU.md "Lot 14 — aperçu gouverné du Studio ML"
[15]: lots/LOT-15-MULTIBANCARISATION-VISIBILITE.md "Lot 15 — multibancarisation et visibilité des flux"
[16]: evidence/visibility/RESULTATS-VISIBILITE.json "Preuve lot 15 — visibilité, oracles et Playwright"
[17]: lots/LOT-16-FINANCIAL-INTELLIGENCE-API.md "Lot 16 — Financial Intelligence API sécurisée"
[18]: evidence/financial-intelligence/RESULTATS-FINANCIAL-INTELLIGENCE.json "Preuve consolidée Financial Intelligence"
