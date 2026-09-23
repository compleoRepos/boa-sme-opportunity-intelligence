# Mapping BIAN candidat — Financial Intelligence

**Révision fonctionnelle Lot 16 :** `9c8edc1f09ce7e545c71856ce430b1e2d89dd73d`
## Qualification

Ce mapping sert uniquement à maintenir un découplage compatible avec une future architecture d’entreprise. Il ne constitue pas une implémentation BIAN ni une certification. Les Service Domains, Business Objects, qualifiers et opérations définitifs sont une **HYPOTHÈSE À VALIDER AVEC BOA**.

| Capacité BOA SME | Rapprochement BIAN candidat | Responsabilité actuelle |
|---|---|---|
| Customer | Party Reference Data Directory / Customer Profile | identité PME et relation |
| Account | Current Account / Account Management | comptes et soldes propriétaires |
| Transaction | Payment Execution / Position Keeping | faits transactionnels `BOOKED` |
| Analytics | Financial Analytics | agrégats point-in-time et qualité |
| Signal / Rules | Customer Behavioral Insights | détections déterministes et preuves |
| Feature Store | Data Analysis / Information Provider | features versionnées et lineage |
| Opportunity | Customer Opportunity | opportunités commerciales existantes |
| Portfolio | Customer Portfolio | affectations commerciales BOA |
| Financial Intelligence | Information Provider / Financial Market Analysis, à confirmer | projection B2B gouvernée, read-only |
| Authorization / Audit FI | Party Authentication / Access Control, à confirmer | scopes, grants et journal d’accès |

La chaîne cible reste : Gateway → couche de services alignable BIAN → adapters BOA → CBS/CRM/Payments/Data Platform. FI dépend de contrats HTTP versionnés et non de tables métier partagées. Cette séparation permet de remplacer ultérieurement un domaine interne par un adapter BOA sans modifier le contrat externe `fi.v1`.
