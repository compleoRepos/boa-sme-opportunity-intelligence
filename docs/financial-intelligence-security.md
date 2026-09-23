# Financial Intelligence — sécurité, autorisation et audit

**Révision fonctionnelle Lot 16 :** `9c8edc1f09ce7e545c71856ce430b1e2d89dd73d`
## Principes

La surface est read-only, deny-by-default et limitée aux données synthétiques. L’autorisation frontend n’est jamais suffisante. Le Gateway et FI valident l’identité ; FI prend la décision de périmètre à partir des enregistrements persistés et journalise le résultat.

## Identité et scopes

Le token OIDC doit être signé par l’issuer configuré, destiné à l’audience attendue, non expiré et porter un sujet ainsi qu’un identifiant de client OAuth. Seul le rôle `EXTERNAL_CONSUMER` ouvre l’accès à la couche d’autorisation ; `ADMIN`, `SERVICE` et toute combinaison du rôle externe avec l’un de ces rôles privilégiés sont refusés au Gateway et au service. Ce rôle n’accorde encore aucune donnée. Les scopes FI sont `financial.read`, `signals.read`, `opportunities.read` et `portfolio.read`. Ils doivent être explicites : aucun joker et aucun `admin.all` ne sont acceptés.

La décision effective est l’intersection suivante :

> **scopes du token ∩ scopes maximaux du Consumer ∩ scopes des grants actifs**

L’identité technique `financial-intelligence-service` est distincte de l’utilisateur externe. Elle appelle les contrats `/internal/v1` avec client_credentials ; le bearer externe n’est pas propagé.

## Modèle d’entitlements

| Objet | Rôle |
|---|---|
| `ExternalConsumer` | organisation B2B, type, statut, scopes maximaux |
| `ExternalPortfolio` | portfolio rattaché à un Consumer et un Fund |
| `ExternalPortfolioCompany` | membership temporel `validFrom`/`validUntil` |
| `DataAccessGrant` | autorisation technique par sujet, client non nullable, scope explicite, finalité fixe et fenêtre |
| `FinancialIntelligenceAccessAudit` | décision d’accès append-only et corrélée |

La possession économique d’une PME ne vaut pas consentement. `authorizationReference` représente une référence technique synthétique ; la base juridique et le processus d’octroi/révocation sont une **HYPOTHÈSE À VALIDER AVEC BOA**.

## Ordre des contrôles

1. Validation OIDC et rôle externe exclusif.
2. Présence du `client_id`, puis résolution serveur du Consumer par `subject` et ce client.
3. Vérification du statut Consumer.
4. Vérification du scope token et du scope maximal Consumer.
5. Résolution Portfolio/Fund et membership société à `asOf`.
6. Recherche d’un grant actif pour le sujet, le client, le portfolio, le scope et la finalité exacte `SYNTHETIC_PORTFOLIO_MONITORING`.
7. Refus uniforme ou composition.
8. Écriture de l’audit `ALLOW`/`DENY` avec le même `traceId`.

Le paramètre `consumerId` est rejeté. Les IDs de portfolio et société ne deviennent jamais des preuves d’accès. La base refuse un grant sans client, une autre finalité et une association Consumer–Portfolio incohérente.

## Privilèges PostgreSQL

Le rôle `financial_intelligence_service` reçoit `USAGE` sur le schéma FI, `SELECT` sur les entitlements et memberships, et `INSERT`/`SELECT` sur l’audit. Il n’a aucun accès aux tables de transactions. Les migrations Alembic ne dépendent pas de l’existence des rôles runtime ; les grants sont appliqués par le bootstrap d’infrastructure.

L’audit refuse les `UPDATE`, `DELETE` et `TRUNCATE` directs par triggers, y compris lorsqu’ils sont exécutés par le propriétaire administratif. Aucune variable de session ne désactive cet invariant ; la matrice vérifie également que l’ancien nom de GUC ne permet aucun contournement DML direct. Un propriétaire DBA conserve cependant la capacité PostgreSQL d’altérer ou supprimer un trigger : l’immutabilité face à un administrateur privilégié n’est donc **pas prouvée**. Le teardown contrôlé passe par le downgrade destructif de `0021`, lequel exige un opt-in de session séparé après sauvegarde et supprime le schéma plutôt que de tronquer l’audit. Une cible BOA exige séparation de rôles et journal WORM externe.

## Audit

Un événement contient sujet, client, Consumer, Fund/Portfolio, société lorsqu’elle est connue, endpoint, scope, résultat, motif, référence d’autorisation, purpose, timestamp et `traceId`. Il exclut token, secret, IBAN, compte, transaction, contrepartie et payload financier.

Les réponses à la question « qui a accédé à quoi, quand et sous quelle autorisation ? » sont possibles via ce journal. La rétention, le chiffrement, l’export SIEM et la valeur probatoire restent **HYPOTHÈSE À VALIDER AVEC BOA**.

## Statut de production

Le modèle est **implémenté et testable pour le POC synthétique**, mais **non production-ready**. L’IAM BOA, la fédération, mTLS, gestion des certificats, secrets, consentement, DPO, contrôle d’accès administratif, alerting, tests d’intrusion et homologation sont bloquants.
