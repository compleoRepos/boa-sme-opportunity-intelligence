# Cartographie BIAN-inspired — BOA SME Opportunity Intelligence

**Statut :** cartographie documentaire du MVP, sans certification.

> **Avertissement :** cette cartographie est indicative. Elle ne constitue ni une certification BIAN, ni une déclaration de conformité, ni une validation par BIAN ou par BANK OF AFRICA. Elle aide à lire les responsabilités ; le blueprint et les contrats API restent normatifs.

## Correspondances indicatives

| Contexte BOA | Service propriétaire | Capacité BIAN-inspired indicative | Données possédées |
|---|---|---|---|
| Référentiel PME | `customer-service` | Party Reference Data Management | PME, secteurs, segments, affectations RM |
| Comptes et soldes | `account-service` | Current Account / Account Management | comptes, lignes, snapshots de soldes |
| Transactions | `transaction-service` | Payment / Payment Execution | mouvements normalisés, contreparties, lots |
| Intégration bancaire | `banking-integration-service` | Banking Integration | provenance, adapters, imports |
| Analyse financière | `analytics-service` | Financial Analysis | métriques, baselines, qualité |
| Détection de signaux | `signal-service` | Event Detection / Financial Analysis | signaux, règles, preuves |
| Catalogue produit | `product-service` | Product Directory / Product Management | catalogue, versions, détentions, gaps |
| Opportunités | `opportunity-service` | Sales Opportunity Management | décisions, confiance, priorité, explications |
| Actions RM | `action-service` | Customer Offer / Sales Action | actions, outcomes, feedback |
| Entrée et identité | `api-gateway` + Keycloak | API Gateway / Party Authentication | routage et identité technique ; pas de domaine métier |

## Règles de cohérence

Chaque service backend cible **Python 3.12, FastAPI, SQLAlchemy 2.x et Alembic** lorsqu’il persiste des données. Les appels interservices du MVP sont HTTP. Les événements sont écrits dans une outbox locale, dans la même transaction que le changement métier ; un broker futur pourra les transporter sans modifier les règles.

Chaque contexte possède son schéma et son utilisateur SQL. Les références interservices sont des identifiants opaques. Les clés étrangères inter-schémas et les lectures SQL d’un schéma tiers sont interdites. Le signal `FINANCIAL_STRESS_SIGNAL` est relationnel et ne constitue pas une décision de crédit.

## Références

[1]: ../docs/implementation-blueprint.md "Blueprint d’implémentation exécutable"
[2]: ../docs/api.md "Contrats API-first"
[3]: https://bian.org/ "BIAN — site officiel"
