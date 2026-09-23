# Lot 16 — Financial Intelligence API sécurisée

**Branche :** `feat/financial-intelligence-api`
**Statut :** **PASS local / DEMO READY**, production **NO-GO / BLOCKED**
**Révision fonctionnelle prouvée :** `9c8edc1f09ce7e545c71856ce430b1e2d89dd73d`
**Run consolidé :** `fi-final-20260923T161020Z`
**Date de référence des données :** `2026-09-30`
**Données :** synthétiques uniquement
**Déploiement :** POC local Docker Compose, non-production

## 1. Objectif

Le lot ajoute une capability B2B read-only permettant à un fonds, une holding ou un partenaire autorisé de consulter des agrégats financiers, signaux et opportunités existantes sur un portefeuille explicitement autorisé. L’extension réutilise les domaines propriétaires de BOA SME Opportunity Intelligence et n’introduit ni décision de crédit, ni transaction brute, ni priorité ML opérationnelle.

## 2. Architecture livrée

Le Gateway expose `/api/v1/financial-intelligence/**`. `financial-intelligence-service` compose cinq contrats propriétaires au moyen d’une identité technique OAuth2 distincte : Customer, Analytics, Signal, Opportunity et Portfolio. Le service possède uniquement le schéma d’entitlements `financial_intelligence` et le journal d’accès append-only.

Le frontend ajoute `/financial-intelligence` et `/financial-intelligence/companies/:companyId`. Les pages consomment exclusivement les hooks React Query du contrat `fi.v1`. Les données absentes, indisponibles ou non implémentées restent visibles comme telles ; aucun tableau d’indicateurs n’est codé en dur.

## 3. Sécurité et non-fuite

L’accès est réservé au rôle `EXTERNAL_CONSUMER` ; `ADMIN`, `SERVICE` et tout token mixte externe + rôle privilégié sont refusés au Gateway et au service. Il exige un `client_id` OAuth non vide et l’intersection des scopes explicites du token, des scopes maximaux du Consumer et des grants actifs. Les ressources sont résolues côté serveur par sujet, client OIDC, Consumer, Fund, Portfolio, membership, scope et finalité fixe `SYNTHETIC_PORTFOLIO_MONITORING`. L’activité du grant est vérifiée à l’instant d’accès, tandis que la validité du membership société est évaluée séparément à `asOf`. Un objet hors périmètre et un objet inconnu rendent le même `404`. `consumerId` est refusé comme filtre.

Le rôle SQL FI ne peut lire aucune transaction. Le bearer externe n’est pas propagé aux domaines internes. L’audit contient la décision, le scope, les références et le `traceId`, sans secret ni donnée bancaire brute.

## 4. Invariants métier

- `NO_CREDIT_DECISION` dans les projections société et portfolio ;
- `executionMode=DETERMINISTIC_RULES` ;
- `mlGovernanceStatus=VERIFIED` seulement si Portfolio retourne un objet valide attestant `POC_SHADOW`, `rulesWeight=1` et `mlWeight=0` ; sinon ces métadonnées restent `null` ou la réponse malformée est refusée ;
- mode CPU-only, `RULES_ONLY`, sans influence ML ;
- aucun LLM, aucun GPU ;
- transactions non `BOOKED` exclues par Analytics ;
- `asOf` obligatoire, memberships filtrés point-in-time, propension bornée par la date et la validité du score ainsi que les opportunités à cette date, snapshots de visibilité datés sans fuite future, projections locales bornées sur 365 jours ;
- statuts Signal/Opportunity non historisés : `status=null`, `stateAsOfStatus=NOT_IMPLEMENTED` ;
- données synthétiques, non-production.

## 5. Matrice de conformité

| Exigence | Statut final | Preuve |
|---|---|---|
| capability FI séparée | **PASS** | 24 conteneurs actifs, 0 unhealthy, `/health` FI et Compose |
| réutilisation des services existants | **PASS** | cinq contrats propriétaires, `sourceStatus` et compteurs d’appels aval |
| aucun accès transaction brut | **PASS** | rôle SQL sans accès Transaction et DTO minimisés |
| OAuth2/OIDC et scopes | **PASS** | six E2E Keycloak Authorization Code + PKCE |
| isolation Fonds A/B | **PASS** | accès croisé rendu en `404`, sans différence d’énumération |
| grant expiré/révoqué | **PASS** | tests unitaires et E2E grant expiré |
| audit append-only DML | **PASS local** | 190 décisions sur la stack finale ; matrice PostgreSQL : mutations directes `UPDATE`/`DELETE`/`TRUNCATE` refusées au runtime et au propriétaire administratif ; résistance à l’altération DDL par DBA non prouvée |
| point-in-time | **PASS** | membership, score, opportunité de priorité et fenêtre locale des projections couverts par tests |
| cohérence Consumer–Portfolio | **PASS** | contrainte composite PostgreSQL et prédicat d’autorisation fail-closed |
| pagination publique | **PASS** | `pageSize` + `offset` traversent Gateway et service ; seconde page exercée en E2E |
| réponses partielles explicites | **PASS** | indisponibilité Analytics rendue `PARTIAL` sans valeur inventée |
| pages Portfolio et Company | **PASS** | quatre captures inspectées, dont 390 × 844 mobile |
| benchmark 10/50/100/500 | **PASS local** | P95 : 3,912 s / 13,262 s / 25,060 s / 125,042 s ; 20 mesures et seuils hypothétiques ; FI à 89,53 % de sa limite mémoire locale |
| migrations vierge/existante/downgrade/ré-upgrade | **PASS** | matrice 0021 complète et garde destructive |
| suite complète Python/frontend | **PASS** | 334 pytest, 43 Vitest, Ruff, mypy, TypeScript, build et ShellCheck |
| scans automatisés | **EXÉCUTION PASS / RELEASE BLOCKED** | zéro secret dans la worktree et 48 commits non-merge atteignables ; 52 `HIGH` backend, 28 `HIGH` et 4 `CRITICAL` externes |
| CI GitHub | **PENDING jusqu’au push** | workflow hérité laissé strictement inchangé ; ne pas assimiler le local au verdict distant |

## 6. Périmètre non implémenté ou bloqué

Le lot n’implémente pas une API Banking-as-a-Service générale, un moteur de crédit, des transactions brutes, une surveillance continue, une architecture de production, un consentement juridiquement validé, une conformité BIAN intégrale ou une exposition publique permanente. Les SLO, limites, scopes, politiques de rétention et contrats restent une **HYPOTHÈSE À VALIDER AVEC BOA**.

La production reste **BLOCKED** jusqu’à IAM et consentement BOA, DPO, réseau/mTLS, coffre de secrets, séparation du propriétaire DBA et journal WORM externe, SIEM, monitoring, charge concurrente, tests d’intrusion, correction des vulnérabilités d’image et homologation.

Le benchmark 500 PME effectue exactement 2 500 lectures interservices par composition et mesure un P50 de 123,860 s, un P95 de 125,042 s et un rendu dashboard de 120,209 s. Le service FI atteint 286,5 MiB sur sa limite locale de 320 MiB, soit 89,53 % : le gate de durée est **PASS**, mais la marge mémoire locale est faible et reste à surveiller. Ces résultats sont des mesures POC mono-nœud ; ils ne sont ni un SLO ni une capacité bancaire validée, et la capacité de production reste **BLOCKED** faute de campagne cible.

Les contre-revues successives ont fait corriger les familles P1 suivantes : binding rôle/sujet/client/finalité, refus des rôles privilégiés y compris mixtes, fenêtres point-in-time des memberships, scores, snapshots de visibilité et opportunités de priorité, rebornage local des projections Signal/Opportunity, statut historique explicitement non implémenté, partialité de `NOT_IMPLEMENTED`, validation stricte du payload Portfolio, gouvernance ML fail-closed, immutabilité sans bypass de l’audit contre `UPDATE`/`DELETE`/`TRUNCATE` et manifeste reproductible des scopes de digest. Les grants restent contrôlés à l’instant réel de l’accès.

## 7. Références

- [Contrat FI](../financial-intelligence-api.md)
- [Sécurité et autorisation](../financial-intelligence-security.md)
- [Modèle de menace](../financial-intelligence-threat-model.md)
- [Plan de capacité](../financial-intelligence-capacity-plan.md)
- [Runbook](../financial-intelligence-runbook.md)
- [Rapport de tests](../financial-intelligence-tests.md)
- [Production readiness](../financial-intelligence-production-readiness.md)
- [Mapping BIAN candidat](../financial-intelligence-bian-mapping.md)
- [Preuve consolidée](../evidence/financial-intelligence/RESULTATS-FINANCIAL-INTELLIGENCE.json)
- [Manifeste source des digests](../evidence/financial-intelligence/SOURCE-MANIFEST-FI.json)
