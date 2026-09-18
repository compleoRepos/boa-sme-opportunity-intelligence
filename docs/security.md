# Sécurité — BOA SME Opportunity Intelligence

**Statut :** exigences et contrôles cibles du MVP ; aucune certification de sécurité n’est revendiquée.

## Identité et autorisation

Keycloak fournit OIDC/OAuth2. Le frontend utilise Authorization Code avec PKCE. Le Gateway et chaque service valident la signature, l’émetteur, l’audience, l’expiration et les rôles du JWT. Les appels internes utilisent des jetons de service `client_credentials`. Un header libre du navigateur ne constitue jamais une preuve d’identité.

Les rôles sont `RELATIONSHIP_MANAGER`, `BRANCH_MANAGER`, `DATA_ANALYST` et `ADMIN`. L’autorisation combine rôle, périmètre et ownership. Un RM ne lit que son portefeuille ; un analyste ne réalise pas d’action commerciale par défaut ; un administrateur gère les règles et le catalogue. Un service doit appliquer son propre contrôle, sans faire confiance au seul Gateway.

## Données, secrets et propriété

Le MVP utilise exclusivement des données synthétiques. Les secrets, mots de passe, tokens et chaînes de connexion viennent de variables d’environnement ou d’un gestionnaire de secrets. Ils ne sont ni versionnés ni journalisés. Les notes d’action sont bornées et redigées avant écriture dans les logs.

Chaque service possède son schéma PostgreSQL, son utilisateur SQL, ses modèles SQLAlchemy et ses migrations Alembic. Les références interservices sont opaques ; aucune lecture SQL ou clé étrangère inter-schémas n’est admise dans les migrations métier.

## Réseau, API et audit

Le navigateur n’accède ni à PostgreSQL, ni aux APIs internes, ni aux APIs bancaires simulées. Les routes publiques sont sous `/api/v1`, les routes internes sous `/internal/v1`. Les erreurs ne divulguent pas de stack trace. Les limites de débit, la validation des payloads, la pagination, la corrélation et l’idempotence sont obligatoires.

Les décisions, changements de règles, accès sensibles et actions RM sont journalisés en append-only avec sujet, ressource, résultat, horodatage, versions et `correlationId`. Les événements sortants sont écrits dans une outbox locale et les métriques ne contiennent pas de donnée client inutile.

## Contrôles de livraison

Avant release, exécuter les tests OIDC/RBAC, les tests d’accès horizontal et vertical, les scans de secrets et dépendances, la vérification de configuration, les tests d’erreur et la non-divulgation. Toute présentation de `FINANCIAL_STRESS_SIGNAL` comme risque ou décision de crédit est bloquante.

## Références

[1]: ../docs/implementation-blueprint.md "Blueprint d’implémentation exécutable"
[2]: ../docs/api.md "Contrats API-first"
[3]: https://openid.net/specs/openid-connect-core-1_0.html "OpenID Connect Core 1.0"
[4]: https://www.keycloak.org/documentation "Documentation Keycloak"
[5]: https://owasp.org/www-project-application-security-verification-standard/ "OWASP Application Security Verification Standard"
