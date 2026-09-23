# Changelog

**Révision fonctionnelle Lot 16 :** `9c8edc1f09ce7e545c71856ce430b1e2d89dd73d`
Les changements notables de BOA SME Opportunity Intelligence sont documentés dans ce fichier.

## [Non publié] — Lot 16 Financial Intelligence

### Ajouté

- Capability read-only `financial-intelligence-service` et surface Gateway `/api/v1/financial-intelligence/**`.
- Modèles persistés `ExternalConsumer`, `ExternalPortfolio`, `ExternalPortfolioCompany`, `DataAccessGrant` et audit append-only.
- Autorisation backend par sujet OIDC, client, Consumer, scopes, grants, Portfolio/Fund et membership point-in-time.
- Composition d’agrégats provenant des services propriétaires Customer, Analytics, Signal, Opportunity et Portfolio, sans accès aux transactions brutes.
- Écrans Portfolio Intelligence et Company Intelligence alimentés par `fi.v1`, avec états partiels et capacités non implémentées explicitement visibles.
- Identités synthétiques Fonds A/B, grant expiré et scope limité pour les tests OIDC de non-fuite.
- Migration additive `0021_financial_intelligence`, downgrade destructif fail-closed et matrice de privilèges PostgreSQL.
- Tests backend, frontend, E2E OIDC, captures responsive et benchmark 10/50/100/500 PME.
- Documentation API, sécurité/autorisation, modèle de menace, capacité, runbook et mapping BIAN candidat.

### Modifié

- Le Gateway rejette les paramètres FI non documentés plutôt que de les ignorer.
- L’identité technique FI est séparée du bearer externe pour les appels interservices.
- Portfolio expose la version du dataset d’entraînement lorsqu’elle existe ; FI conserve `modelVersion`, `featureVersion` et `trainingDatasetVersion` en mode shadow.
- L’accès FI est désormais réservé à `EXTERNAL_CONSUMER` ; le `client_id` OAuth est obligatoire et le grant doit correspondre au sujet, au client et à la finalité fixe `SYNTHETIC_PORTFOLIO_MONITORING`.
- `ADMIN`, `SERVICE` et les tokens mixtes externe + rôle privilégié sont refusés au Gateway comme au service FI.
- La propension Portfolio est bornée par `score.as_of_date <= asOf`, par la fenêtre `valid_until` et par les bornes de génération/expiration des opportunités ; une sélection de visibilité datée exclut les snapshots futurs. Un score intrinsèquement incohérent (`valid_until < as_of_date`) est rejeté même en lecture latest-only. FI rebornne localement les projections sur `[asOf-364 jours, asOf]` et réapplique la borne `expiresAt` en défense en profondeur. Les statuts courants Signal/Opportunity ne sont plus présentés comme historiques et `NOT_IMPLEMENTED` rend la réponse partielle.
- Les triggers de l’audit append-only refusent désormais les mutations DML directes `UPDATE`, `DELETE` et `TRUNCATE`, y compris au propriétaire administratif et même si l’ancien GUC de contournement est positionné ; seul le downgrade destructif explicite réalise le teardown du schéma. La résistance à un DBA qui altérerait le DDL n’est pas revendiquée.
- Les métadonnées ML ne sont attestées que si Portfolio confirme `RULES_ONLY`, `POC_SHADOW` et les poids 1/0 ; elles restent `null` si cette gouvernance est indisponible.
- Les réponses Portfolio mal typées, incomplètes ou contenant un champ inconnu à la racine, dans `model` ou dans `combination` échouent en `502 DEPENDENCY_INVALID_RESPONSE` au lieu de provoquer une erreur interne.
- Un manifeste source versionné explicite les scopes runtime, migration et sécurité, les fichiers, SHA-256 et algorithmes d’agrégation de chaque digest de preuve.
- La CSP frontend autorise uniquement l’origine Keycloak configurée, sans wildcard.
- La CI ajoute les gates FI et conserve l’échec obligatoire des vrais blockages sécurité.

### Garde-fous

- **Aucune décision de crédit** et aucune exposition de transaction brute.
- ML classique CPU uniquement, `POC_SHADOW`, `rulesWeight=1`, `mlWeight=0` ; aucune influence sur la priorité.
- Aucun LLM, aucun GPU et aucune donnée BOA réelle.
- Production **BLOCKED** jusqu’à validation IAM, consentement/DPO, sécurité, exploitation, secrets, HA/DR, monitoring, performance cible, scans d’images et homologation BOA.

Toutes les données, autorisations, seuils et volumétrie du Lot 16 sont synthétiques. Toute cible métier ou opérationnelle est une **HYPOTHÈSE À VALIDER AVEC BOA**.
