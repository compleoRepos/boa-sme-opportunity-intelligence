# Lot 13 — Clôture de la préparation pilote

**Date :** 21 septembre 2026

**Branche :** `feat/pilot-readiness`

**Dépôt :** public

**Commit catalogue publié :** `0b7b2b5`

**AWS :** hors périmètre à la demande du propriétaire

**Décision release :** **NO-GO — `BLOCKED_IMAGE_CVES`**

## 1. Conclusion exécutive

Les lots 1 à 12 ont produit un dépôt public autonome, des parcours intégrés et des preuves exécutées. Le produit est démontrable localement sur données synthétiques. La chaîne métier, les périmètres backend, l’ingestion gouvernée, le ML shadow, les tests de charge, la restauration, la dégradation de readiness et le catalogue indicatif de 28 produits sont couverts par des artefacts versionnés.

L’artefact consolidé de ce lot porte volontairement le statut `BLOCKED` et relie la révision publique, les preuves catalogue/E2E, le gate sécurité et le verdict CI `cancelled`.[13]

Cette clôture ne transforme pas le POC en production bancaire. Les images externes pinées présentent encore 25 constats `HIGH` et 4 `CRITICAL`, même si les images applicatives backend et frontend sont à zéro dans le protocole local. La release reste donc bloquée.[4][7]

Le propriétaire a demandé **aucun déploiement AWS**. Le chantier AWS est clos comme **HORS PÉRIMÈTRE**. Aucun accès AWS, secret GitHub Actions, variable AWS, rôle OIDC, registre ECR, service de calcul, base RDS, stockage S3, clé KMS ou ressource CloudWatch n’a été configuré ou créé.

## 2. Matrice de clôture

| Sujet | Statut | Décision |
|---|---|---|
| Dépôt public | **PASS** | `compleoRepos/boa-sme-opportunity-intelligence` est public[11] |
| Branche pilote | **PASS** | `feat/pilot-readiness` est publiée au commit catalogue `0b7b2b5` |
| Pack bancaire | **PASS** | positionnement, valeur, architecture, alternatives, plan pilote, démo, FAQ, sécurité et RBAC versionnés |
| Chaîne métier | **PASS local** | Rules → Signals/Features → ML shadow → Opportunity → dashboards |
| Isolation CC/agence backend | **PASS local** | périmètre imposé dans les services ; l’IHM n’est pas la frontière d’autorisation |
| Catalogue produit indicatif | **PASS local** | 28 produits, 7 familles, provenance publique, scope backend, readiness et erreurs fail-closed[5][8] |
| Ingestion et qualité | **PASS dans le protocole local** | manifeste, quarantaine, qualité, version et concurrence prouvés[2] |
| Charge 50 000 PME | **PASS dans le protocole isolé** | scénarios avec seuil conformes ; dashboards sans seuil seulement mesurés[1] |
| ML défendable | **PASS pour `POC_SHADOW`** | 500 observations shadow, zéro fallback, priorité `RULES_ONLY` ; labels BOA indisponibles[3] |
| Sauvegarde/restauration | **PASS local** | restauration jusqu’à Alembic `0017`, altération détectée, nettoyage vérifié[4] |
| Readiness dégradée | **PASS local** | DB arrêtée : `/ready=503` ; liveness maintenue ; récupération mesurée localement[4] |
| Tests finaux | **PASS local** | 259 backend, 27 frontend, 20 E2E détaillés[9] |
| CI distante lot 11 | **CANCELLED** | run `35538673248` arrêté à la limite de 60 minutes ; ne pas le présenter comme PASS[6] |
| CI distante catalogue | **CANCELLED** | run `35547449760` sur `0b7b2b5` arrêté après 64 minutes : six jobs amont réussis, job Compose/E2E annulé à 60 minutes, quality gate en échec[10] |
| Scans de sécurité | **EXÉCUTION PASS** | Gitleaks, dépendances et cinq images scannés sans `--ignore-unfixed`[7] |
| Release | **BLOCKED** | 25 `HIGH` et 4 `CRITICAL` sur images externes[7] |
| Studio ML premium parallèle | **BLOCKED / NON INTÉGRÉ** | backend partiel en worktree isolée ; aucune campagne finale, aucun commit, frontend/E2E/docs incomplets |
| AWS | **HORS PÉRIMÈTRE** | aucune ressource ni preuve AWS |
| Production BOA | **NON AUTORISÉE** | prérequis SI, sécurité, conformité, exploitation et données non levés |

## 3. Ce qui est livré

Le dépôt contient douze rapports de lots techniques avant cette clôture, les documents bancaires, les scripts de validation, les manifestes SHA-256 et les artefacts JSON issus des exécutions. Le workflow GitHub Actions versionné rejoue les contrôles backend, frontend, sécurité, Docker, E2E, migration, backup/restore et panne DB. Il ne publie aucune image et ne déploie aucun environnement.

Le frontend distingue le score ML shadow de la priorité métier. La priorité provient des règles publiées. Le verrou rules-only est testé côté backend et frontend. Les 20 E2E finaux sont détaillés dans un JSON versionné avec leurs statuts et durées.[9]

Le catalogue indicatif est alimenté par 28 pages publiques BANK OF AFRICA et réparti en 7 familles internes. Il ne constitue pas un catalogue commercial BOA validé. Les ciblages, critères, tarifs, montants, durées et disponibilités restent **HYPOTHÈSE À VALIDER AVEC BOA**. Les recommandations utilisent des codes précis ; Rule Studio et Product Service refusent explicitement les codes inconnus, et Product Service ne devient ready qu’avec le seed gouverné complet. Les preuves catalogue, migration et les 20 E2E ont été régénérées sur le commit public `0b7b2b5`.[5][8][9]

La dernière stack observée comporte 23 services : 22 `healthy` et le worker de notification `running` sans healthcheck. Ce constat est une observation locale, pas un SLO.

## 4. Blocages de release

Le blocage principal immédiatement mesuré est `BLOCKED_IMAGE_CVES`. Les 28 constats disposant d’une `FixedVersion` exigent une mise à jour d’image ou une construction maîtrisée. Le constat sans correctif amont exige une décision de risque. Aucune dérogation n’est ajoutée au dépôt. Les scans restent sans `--ignore-unfixed`.[7]

Les runs CI du lot 11 et du catalogue ont été annulés lorsque le job Compose/E2E a atteint la limite versionnée de 60 minutes. Sur le run catalogue, sécurité, lint/tests unitaires, infrastructure, frontend et les deux builds Docker ont réussi ; `compose-e2e-and-operations` a été annulé, `quality-gate` a échoué et `release-image-gate` a été ignoré. Une hausse locale à 120 minutes a été préparée, mais l’intégration GitHub App a refusé toute modification de `.github/workflows/ci.yml` faute de permission `workflows`. Ce changement n’a pas été poussé et le jeton précédemment exposé n’a pas été réutilisé. Les succès locaux ne remplacent pas ce verdict distant.[6][10]

Les autres prérequis restent explicites : interfaces sources BOA, annuaire, comptes techniques, coffre, certificats, TLS/mTLS, SIEM, alerting, haute disponibilité, stockage indépendant des sauvegardes, RPO/RTO/SLO, procédures de support et validation conformité sont **NON IMPLÉMENTÉS / À VALIDER AVEC BOA**.

Les données et labels historiques BOA ne sont pas disponibles. Les outcomes sont des labels candidats, `trainingReady=false`, le manifest d’activation est bloqué et la calibration n’est pas validée. Aucune métrique issue de la fixture synthétique ne constitue une performance ML de production.[3]

## 5. Règles de décision conservées

Le produit reste une aide commerciale. Il ne prend aucune décision de crédit. `FINANCIAL_STRESS_SIGNAL` est un élément relationnel à examiner humainement. Aucun LLM ou GPU n’est nécessaire. Toute influence future du ML exige des labels BOA gouvernés, une évaluation temporelle indépendante, une calibration validée, des critères approuvés et une modification explicite des gates techniques.

Le Studio ML premium demandé en parallèle n’est pas livré sur la branche pilote. Les travaux partiels restent dans une worktree isolée, non commités et non intégrés. Ils ne modifient donc aucun statut fonctionnel ou de release du dépôt public.

## 6. Prochaines décisions externes

Une pull request vers `main` ne doit être ouverte que lorsque le propriétaire souhaite engager formellement la revue de release. Avec le statut actuel, elle sera volontairement bloquée par `release-image-gate`. Les prochaines actions utiles sont :

1. remédier aux images externes ou faire prendre une décision formelle d’acceptation de risque ;
2. accorder, si souhaité, une permission GitHub dédiée permettant une modification gouvernée du workflow et relancer la CI complète ;
3. fournir les contrats, données, identité et exigences d’exploitation BOA nécessaires au pilote réel ;
4. terminer et valider séparément le Studio ML avant tout cherry-pick sur la branche pilote.

Aucun déploiement AWS ne fait partie des prochaines actions.

## Références

[1]: LOT-08-CHARGE-50000.md "Lot 08 — validation de charge isolée sur 50 000 PME"
[2]: LOT-09-INGESTION-QUALITE.md "Lot 09 — ingestion gouvernée et qualité Transaction"
[3]: LOT-10-ML-SHADOW-DEFENDABLE.md "Lot 10 — ML shadow défendable"
[4]: LOT-11-INDUSTRIALISATION-EXPLOITATION.md "Lot 11 — industrialisation pilote et exploitation prouvée"
[5]: LOT-12-CATALOGUE-PRODUITS-BOA.md "Lot 12 — catalogue produit public et garde-fous"
[6]: https://github.com/compleoRepos/boa-sme-opportunity-intelligence/actions/runs/35538673248 "GitHub Actions — CI du lot 11"
[7]: ../evidence/security/RESULTATS-SCANS-SECURITE.json "Preuve consolidée des scans de sécurité et gate release"
[8]: ../evidence/catalog/RESULTATS-CATALOGUE-PRODUITS.json "Preuve catalogue finale"
[9]: ../evidence/catalog/RESULTATS-PLAYWRIGHT-CATALOGUE.json "Résultats détaillés des vingt E2E"
[10]: https://github.com/compleoRepos/boa-sme-opportunity-intelligence/actions/runs/35547449760 "GitHub Actions — CI catalogue"
[11]: https://github.com/compleoRepos/boa-sme-opportunity-intelligence "Dépôt public"
[12]: ../final-status.md "Statut final de préparation pilote"
[13]: ../evidence/closure/RESULTATS-CLOTURE-PILOTE.json "Preuve consolidée de clôture pilote"
