# Financial Intelligence — production readiness

## Décision

Le Lot 16 est conçu pour un **POC local sur données synthétiques**. Les résultats locaux peuvent autoriser une démonstration technique après validation des artefacts, mais ils ne constituent ni une homologation BOA, ni une autorisation d’exposer des données bancaires réelles.

| Niveau | Décision | Portée |
|---|---|---|
| Local POC | **PASS** | Révision `9c8edc1f09ce7e545c71856ce430b1e2d89dd73d` : 24 conteneurs actifs, 0 unhealthy, contrat `fi.v1`, 334 tests Python, 43 tests frontend, 6 E2E OIDC et matrice PostgreSQL 0021 sur stack isolée fraîche |
| Demo ready | **PASS** | 6/6 E2E Keycloak OIDC, quatre captures desktop/mobile, identités Fonds synthétiques et disclaimer non-production |
| Production ready | **NO-GO / BLOCKED** | Aucun branchement BOA réel ni exposition B2B autorisée |

## Blockers de production

| Domaine | Statut | Condition de levée |
|---|---|---|
| IAM et identité B2B | **BLOCKED** | Fédération BOA, audiences, clients, scopes, certificats, rotation et révocation homologués |
| Consentement et DPO | **BLOCKED** | Base juridique, finalités, minimisation, rétention et processus DataAccessGrant approuvés |
| Données BOA | **BLOCKED** | Contrats sources, qualité, réconciliation, classification et propriétaires validés |
| Sécurité réseau | **BLOCKED** | TLS/mTLS, WAF/API management, segmentation, pentest et protection anti-abus |
| Secrets | **BLOCKED** | Coffre, rotation, certificats et procédures d’urgence opérationnels |
| Exploitation | **BLOCKED** | SIEM, OpenTelemetry/Dynatrace cible, alerting, astreinte, runbooks et capacité de support |
| Immutabilité d’audit | **BLOCKED** | séparation du rôle propriétaire DBA, journal WORM externe et tests de résistance à l’altération DDL |
| Résilience | **BLOCKED** | HA, sauvegarde, restauration, RPO/RTO et disaster recovery testés sur la cible |
| Performance | **BLOCKED** | SLO BOA et campagne multi-utilisateur sur infrastructure cible ; les seuils locaux restent hypothétiques |
| Images et supply chain | **BLOCKED_IMAGE_CVES** | scan `9c8edc1f09ce7e545c71856ce430b1e2d89dd73d` exécuté : zéro secret sur la worktree et 48 commits non-merge atteignables ; backend 52 `HIGH`, frontend 0 `HIGH`/`CRITICAL`, externes 28 `HIGH`/4 `CRITICAL`; exiger correction ou acceptation formelle, images signées, SBOM et provenance |
| Homologation | **BLOCKED** | Revues architecture, sécurité, conformité, DPO et exploitation BOA conclues |

Le benchmark mono-nœud 500 PME mesure un P95 de 125,042 secondes et 2 500 appels interservices par composition. La mémoire du service FI atteint 286,5 MiB sur 320 MiB, soit 89,53 %. Le temps reste dans le budget local hypothétique ; la marge mémoire est faible. Aucune conclusion de capacité n’est possible sans campagne concurrente sur cible, et les pistes de pagination de composition, matérialisation ou lecture batch restent à évaluer.

## Invariants non négociables

La surface reste read-only et n’expose pas les transactions brutes. Elle ne prend aucune décision de crédit. L’accès externe exige le rôle, le sujet, le client, les scopes et la finalité autorisés. La priorité reste `RULES_ONLY`; le ML demeure CPU-only, sans LLM ni GPU. `POC_SHADOW`, `rulesWeight=1` et `mlWeight=0` ne sont attestés que si Portfolio fournit cette combinaison complète ; sinon les champs restent `null`. Les résultats synthétiques, les scopes, les limites de 500 PME, les timeouts et tout seuil de performance sont une **HYPOTHÈSE À VALIDER AVEC BOA**.

## Critère de révision

Ce document devra être réévalué après chaque changement d’authentification, de contrat de données, de frontière réseau, de politique de consentement, de dépendance d’image ou de cible d’hébergement. Une CI verte sur le dépôt ne suffit jamais à déclarer la production prête.
