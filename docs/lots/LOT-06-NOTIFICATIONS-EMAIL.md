# Lot 06 — Notifications email et synthèse quotidienne

**Date de validation :** 19 septembre 2026
**Branche :** `feat/pilot-readiness`
**Statut global :** **PASS pour le pilote local**

## 1. Objet

Ce lot ferme l’écart pilote relatif à la **notification quotidienne par courriel avec connecteur SMTP configurable**. Il ajoute un Notification Service et un worker résilient, des rappels liés aux actions commerciales planifiées, une synthèse quotidienne agrégée par chargé de clientèle, un écran administrateur, la traçabilité des livraisons et une preuve SMTP locale réelle.

Le produit reste un outil d’aide commerciale. Les emails ne contiennent pas de détail transactionnel, de nom de PME dans la synthèse quotidienne, ni de recommandation de crédit. Ils rappellent explicitement qu’aucune décision de crédit n’est produite.

## 2. Résultats

| Exigence | Statut | Preuve |
|---|---:|---|
| Connecteur SMTP configurable | **PASS** | Variables `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_STARTTLS`, `SMTP_SSL` et `SMTP_FROM` ; Mailpit `v1.21.8` pour la preuve locale. |
| Rappel après action planifiée | **PASS** | Action Service écrit `ACTION_NOTIFICATION_REQUESTED` dans l’outbox transactionnelle ; le parcours E2E CC reçoit le message dans Mailpit. |
| Synthèse quotidienne par CC | **PASS** | Abonnement avec fuseau IANA et heure locale ; worker autonome ; un message au plus par `(CC, date locale)`. |
| Paramétrage sans accès base | **PASS** | Page `/back-office/notifications`, endpoints administrateur et tests RBAC. |
| Agrégats sans données sensibles | **PASS** | Le worker consomme les KPI de Portfolio Service via OAuth2 ; aucun nom de PME ni détail de compte dans le corps quotidien. |
| Retry, issue incertaine et dead-letter | **PASS** | Délai exponentiel borné ; `DELIVERY_UNCERTAIN` sans réémission automatique après crash ; `DEAD_LETTER` après cinq échecs certains ; réarmement explicite. |
| Historique de livraison immuable | **PASS** | `notification.notification_delivery_attempts` et triggers refusant `UPDATE`, `DELETE` et `TRUNCATE`. |
| Migration existante et vierge | **PASS** | `0013→0014` et `0001→0014`, trois tables dans le schéma `notification`. |
| Livraison sur SMTP BOA de production | **BLOCKED** | Les hôtes, certificats, comptes, politiques anti-spam et destinataires réels doivent être fournis et homologués par BOA. Aucune livraison externe n’est revendiquée. |

## 3. Architecture livrée

Action Service persiste l’action et un événement d’outbox `BLOCKED` dans la même transaction que l’intention de saga, avant l’appel distant. La finalisation locale, l’outcome, l’audit et le passage de l’événement à `READY` sont ensuite commités ensemble. Le worker ignore strictement `BLOCKED`. Si le processus tombe après la réponse distante, l’action et son événement durable demeurent reprenables ; le rejeu de la même commande reprend idempotemment la transition et active le même événement. Notification Service revendique les événements `READY` non publiés avec `FOR UPDATE SKIP LOCKED`, construit un message dédupliqué, puis marque l’événement comme consommé. Un événement sans destinataire vérifié est mis en quarantaine après trois tentatives au lieu de boucler indéfiniment.

Pour la synthèse, le worker utilise son propre compte OIDC `notification-service`, doté uniquement du rôle `NOTIFICATION_DIGEST_READER`. Il appelle une route Portfolio dédiée, liée au CC par une signature HMAC avec un secret distinct et obligatoire au démarrage. Le rôle générique `SERVICE` reçoit `403` et ne peut pas davantage déclencher le dispatch ou la génération forcée. Le payload ne contient que les KPI agrégés nécessaires. Un advisory lock PostgreSQL et la clé unique `daily-digest:{relationshipManagerId}:{date}` empêchent les doubles générations concurrentes.

Chaque livraison utilise un `Message-ID` stable, persisté avant l’appel SMTP, puis expurge les adresses des messages d’erreur. Un succès passe à `SENT`. Un échec certain passe à `RETRY` avec une prochaine échéance ou à `DEAD_LETTER`. Un processus interrompu entre l’acceptation SMTP et le commit passe à `DELIVERY_UNCERTAIN` : aucune réémission automatique n’a lieu avant rapprochement du Message-ID. Une authentification SMTP sans `STARTTLS` ou TLS implicite est refusée.

## 4. Preuves exécutées

### 4.1 Porte complète

| Contrôle | Résultat mesuré |
|---|---:|
| Ruff format | **PASS — 130 fichiers** |
| Ruff | **PASS** |
| mypy | **PASS — 78 fichiers source** |
| pytest backend | **PASS — 220 tests, 6 avertissements existants** |
| ShellCheck | **PASS** |
| Validation Compose et Keycloak | **PASS** |
| TypeScript | **PASS** |
| Vitest | **PASS — 20 tests** |
| Build Vite | **PASS** |
| Playwright | **PASS — 12 parcours E2E** |
| Validation ML gouvernée | **PASS** |
| Preuve SMTP reproductible | **PASS** |

Commande principale :

```bash
PYTHONPATH=backend/src:. pytest tests/unit -q --disable-warnings
npm --prefix frontend test
npm --prefix frontend run test:e2e
./scripts/validate-ml-integration.sh
./scripts/validate-notifications.sh
```

La preuve `validate-notifications.sh` a produit :

```text
PASS notification=becde22f-b911-48bb-812f-6406181c43d6 status=SENT sentAttempts=1 smtpMessages=1 appendOnly=true leastPrivilege=true outboxRls=true
```

L’identifiant est propre à cette exécution ; le script génère une nouvelle preuve à chaque lancement.

### 4.2 Parcours Action → SMTP

Le scénario Playwright « une action planifiée par le CC produit un email SMTP audité » s’est authentifié comme CC, a ouvert une PME de son portefeuille, a planifié une action « À contacter », puis a attendu le message dans l’API Mailpit. Le rapprochement PostgreSQL a montré l’événement d’outbox consommé, la notification `SENT`, une tentative unique `SENT` et un Message-ID fournisseur.

### 4.3 Parcours autonome quotidien

Un abonnement dû pour `rm-02` a été inséré avec l’adresse synthétique `rm-02@synthetic.invalid`. Sans jeton utilisateur ni appel manuel de génération, le worker a obtenu son jeton `client_credentials`, lu les KPI du portefeuille, créé puis livré la synthèse. Les preuves observées sont :

```text
PORTFOLIO_DAILY_DIGEST | SENT | 1 | notification-worker | rm-02@synthetic.invalid
notification cycle materialized=0 digests=1 claimed=1 sent=1 failed=0
```

Mailpit a reçu un message dont le sujet était `BOA SME — synthèse quotidienne du 2026-09-19`. Cette preuve est locale et ne constitue pas une mesure de délivrabilité Internet ou du relais BOA.

### 4.4 Migrations

La base Docker existante a été migrée de `0013_label_catalog` vers `0014_email_notifications`. Une base PostgreSQL temporaire vide a ensuite exécuté toute la chaîne `0001→0014`. Dans les deux cas, la version finale était `0014_email_notifications` et le schéma `notification` contenait les trois tables attendues.

## 5. Revue indépendante et fermeture des constats

Deux revues indépendantes ont demandé des corrections avant commit, puis une troisième contre-revue a rendu le verdict **PASS** sans P0/P1 résiduel. Les constats ont été fermés : l’événement `BLOCKED` est durable avant l’appel distant puis activé transactionnellement avec la finalisation locale ; seules les adresses OIDC avec `email_verified=true` sont utilisées ; l’authentification SMTP exige TLS ; une issue ambiguë est mise en quarantaine ; le lecteur de synthèse dispose d’un rôle et d’une signature dédiés ; génération et dispatch sont réservés aux administrateurs ; le secret de portée n’a plus de fallback ; et `notification_service` n’est plus propriétaire du schéma. Le constat P2 sur les événements d’outbox invalides est également fermé par une quarantaine bornée et observable.

La preuve PostgreSQL finale confirme : propriétaire du schéma `boa_admin`, `USAGE=true`, `CREATE=false`, écriture minimale sur messages et abonnements, insertion seule dans l’historique, `DELETE=false`, `UPDATE=false` sur les tentatives. Sur l’outbox, RLS masque tous les événements étrangers et les droits de colonnes interdisent la modification de `payload_json`, `event_type`, `aggregate_id` ou du destinataire.

## 6. Limites et conditions de passage en production

Avant production, BOA doit fournir le relais SMTP, le mode TLS, les secrets via son coffre, les domaines autorisés, la liste des expéditeurs, les règles de conservation, les seuils d’alerte et la procédure de traitement des dead-letters. Les adresses `synthetic.invalid` et Mailpit sont strictement des moyens de test. La cadence du worker est configurable, mais le dimensionnement et la haute disponibilité doivent être validés dans l’environnement cible.

Ce lot ne modifie ni le modèle ML, ni le mode POC/shadow, ni les règles de crédit. Il ajoute uniquement un canal de communication commerciale gouverné et reproductible.
