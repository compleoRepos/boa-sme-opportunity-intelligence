# Runbook — Financial Intelligence API

**Révision fonctionnelle Lot 16 :** `9c8edc1f09ce7e545c71856ce430b1e2d89dd73d`
## Qualification

Ce runbook s’applique au POC synthétique du Lot 16. Les procédures BOA de production, les responsabilités de garde, RTO/RPO, SIEM et canaux d’escalade sont une **HYPOTHÈSE À VALIDER AVEC BOA**.

## Contrôles de santé

Le service FI répond sur `/health`; le Gateway sur son propre `/health`. Une validation minimale contrôle PostgreSQL, Keycloak, Gateway, FI et les cinq domaines propriétaires. Les journaux doivent être recherchés par `X-Correlation-ID`/`traceId`, jamais par bearer ou payload financier.

## Dépendance indisponible

Lorsqu’un domaine propriétaire retourne une erreur normalisée, FI marque la capability `UNAVAILABLE` et l’enveloppe `partial=true`. L’opérateur vérifie le statut du service, le timeout et les logs corrélés. Il ne remplace jamais la valeur absente par une fixture, un cache non gouverné ou une valeur calculée dans React. Une réponse partielle doit rester visible jusqu’au rétablissement de la source.

## Révocation urgente

La révocation s’effectue dans `financial_intelligence.data_access_grants` par un processus d’administration séparé, non exposé par l’API B2B du Lot 16. Après révocation, le contrôle `revoked_at` est prioritaire sur les dates et l’accès doit être refusé. L’opérateur vérifie ensuite un événement `DENY` corrélé dans `access_audit`. La procédure, les habilitations et le délai contractuel de révocation sont **HYPOTHÈSE À VALIDER AVEC BOA**.

## Suspicion de fuite ou d’énumération

Suspendre le Consumer ou révoquer ses grants, préserver les logs append-only, relever les `traceId`, sujets, clients, portfolios et reason codes, puis isoler l’exposition. Ne jamais exporter les bearers ni les données bancaires. Les accès hors périmètre doivent rester indistinguables des ressources inconnues (`404`).

## Rotation OIDC

Le secret `financial-intelligence-service` est injecté par variable d’environnement. Une rotation exige de mettre à jour le coffre cible et Keycloak, de recréer le service FI puis de confirmer ses appels internes. Les secrets de démonstration présents dans `.env.example` ne sont pas utilisables hors local.

## Migration et rollback

La migration `0021_financial_intelligence` est additive. Son downgrade supprime entitlements et audit ; il est donc refusé sans `SET boa.allow_fi_destructive_downgrade='true'`. Avant toute autorisation explicite, sauvegarder le schéma et les journaux, faire approuver la perte attendue, puis vérifier le cycle upgrade/downgrade/re-upgrade sur une base isolée.

## Dépassement de capacité

Une composition de plus de 500 PME renvoie `FI_PORTFOLIO_LIMIT_EXCEEDED`. Une latence élevée doit conduire à réduire la concurrence, inspecter les cinq dépendances et mesurer CPU/mémoire. Il est interdit d’augmenter silencieusement la limite ou de désactiver les timeouts. Toute valeur cible reste une **HYPOTHÈSE À VALIDER AVEC BOA**.

## Vérifications de clôture

Après incident, confirmer : santé des services, isolation Funds A/B, refus scope/grant, absence de champ financier brut, cohérence `asOf`, `rulesWeight=1`, `mlWeight=0`, audit append-only et absence de secret dans les logs. La reprise n’est déclarée qu’après un scénario E2E OIDC et une vérification de l’artefact associé.

Avant un cycle de preuve final, figer le commit fonctionnel, vérifier la propreté de `.github`, `backend`, `database`, `frontend`, `infrastructure`, `scripts` et `tests`, puis exécuter `scripts/generate-financial-intelligence-source-manifest.sh`. Les preuves E2E, migration, performance, ressources et sécurité doivent référencer le scope correspondant de `SOURCE-MANIFEST-FI.json`. La consolidation doit refuser tout SHA ou digest divergent ; un hash copié manuellement sans liste de fichiers et algorithme n’est pas une preuve reproductible.
