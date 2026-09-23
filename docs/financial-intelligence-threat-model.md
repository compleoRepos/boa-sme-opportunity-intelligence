# Modèle de menace — Financial Intelligence API

**Révision fonctionnelle Lot 16 :** `9c8edc1f09ce7e545c71856ce430b1e2d89dd73d`
## Objet et limites

Ce document couvre la surface B2B read-only du Lot 16. L’environnement validé est un **POC local sur données synthétiques, non destiné à la production**. Il ne couvre ni données BOA réelles, ni consentement juridiquement validé, ni exposition Internet de production. Les exigences IAM BOA, DPO, conformité, cryptographie, rétention et homologation restent **HYPOTHÈSE À VALIDER AVEC BOA**.

## Actifs et frontières de confiance

Les actifs protégés sont les agrégats financiers, signaux, opportunités existantes, memberships Consumer/Fund/Portfolio, grants, références d’autorisation et journaux d’accès. Le navigateur externe et le réseau public sont non fiables. Le Gateway valide OIDC puis relaie le bearer vers FI. FI résout les entitlements côté serveur et utilise ensuite son propre client OAuth2 `financial-intelligence-service` pour appeler les domaines propriétaires. Le bearer externe n’est jamais propagé aux services internes.

FI possède seulement le schéma `financial_intelligence`. Les domaines Customer, Analytics, Signal, Opportunity et Portfolio restent propriétaires de leurs données. Aucun accès SQL FI aux transactions, comptes ou tables métier n’est accordé.

## Menaces et contrôles

| Menace | Contrôle implémenté | Preuve attendue | Risque résiduel |
|---|---|---|---|
| Confusion de tenant Consumer/Fund | résolution serveur par `sub`, `client_id`, Consumer, Fund, Portfolio et grant | E2E Fonds A/B et tests unitaires | mapping IAM BOA à valider |
| Énumération d’une ressource tierce | réponse uniforme `404 RESOURCE_NOT_FOUND` pour inconnu et hors périmètre | API directe cross-Fund | analyse anti-enumération en charge à compléter |
| Injection de `consumerId` ou filtre caché | rejet `400 UNKNOWN_FILTER` ; aucun identifiant de Consumer accepté comme autorité | test API avec `consumerId` | normalisation WAF future à définir |
| Token sans scope ou scope excessif | intersection token ∩ Consumer ∩ grant, deny-by-default | tests scope manquant et OIDC | taxonomie finale des scopes à valider |
| Grant expiré, révoqué ou futur | contrôle temporel au moment de l’accès ; révocation prioritaire | tests unitaires et E2E grant expiré | propagation temps/révocation distribuée à industrialiser |
| Fuite de bearer vers les domaines internes | token client_credentials FI distinct via `service_request` | test unitaire de client sortant | rotation et coffre BOA non intégrés |
| Exposition de transactions brutes | DTO anti-corruption et garde récursive `no_raw_financial_fields` | tests de payload et contrat | dictionnaire DPO des champs interdits à approuver |
| Contournement SQL | rôle runtime limité au schéma FI ; aucune permission sur `transaction.transactions` | matrice PostgreSQL 0021 | revue indépendante DBA nécessaire |
| Altération du journal | triggers append-only refusant les `UPDATE`/`DELETE`/`TRUNCATE` directs au runtime et au propriétaire administratif | oracles SQL sur les trois mutations et l’ancien GUC | un propriétaire DBA peut altérer les triggers ; séparation de rôles et stockage WORM externe à définir |
| SSRF | URLs downstream lues uniquement depuis la configuration serveur | revue de code | durcissement egress de production à définir |
| Amplification/fan-out | pagination catalogue, maximum 500 PME, semaphore 1–25, timeout par dépendance | benchmark 10/50/100/500 | limites multi-utilisateur à valider en charge |
| Réponse partielle trompeuse | `partial=true` pour `UNAVAILABLE` ou `NOT_IMPLEMENTED`, `sourceStatus`, aucune valeur inventée | tests d’indisponibilité et de capacité non implémentée | politique contractuelle de partialité à approuver |
| Influence ML indue | vérification conjointe `RULES_ONLY`, `POC_SHADOW`, `rulesWeight=1`, `mlWeight=0`; métadonnées nulles si Portfolio est indisponible | tests de contrat/E2E | activation future explicitement hors lot |
| Décision de crédit implicite | aucun endpoint de crédit ; disclaimer `NO_CREDIT_DECISION`; route `credit-decision` refusée | OpenAPI et tests | validation juridique des libellés à obtenir |
| Secret ou token dans les logs | audit limité aux identifiants non sensibles, scope, décision, trace et référence | inspection de schéma et tests | politique centralisée de redaction à industrialiser |

## Modèle d’autorisation

L’autorisation est affirmative uniquement si toutes les conditions sont réunies : rôle `EXTERNAL_CONSUMER` sans présence de `ADMIN` ou `SERVICE`, Consumer actif, sujet reconnu, `client_id` OAuth non vide et identique au grant, scope explicite présent dans le token et dans `allowed_scopes`, portfolio du Consumer/Fund, société membre du portfolio à `asOf`, grant actif au moment de la requête, purpose exactement égal à `SYNTHETIC_PORTFOLIO_MONITORING` et référence d’autorisation présente. Le Gateway et FI refusent aussi les tokens mixtes externe + rôle privilégié. Le schéma SQL rend `client_id` non nullable et contraint la finalité. Toute absence ou incohérence produit un refus audité.

La fermeture opérationnelle d’un membership ne réécrit pas l’historique. Les lectures à `asOf` utilisent sa fenêtre `[valid_from, valid_until[` ; la contrainte SQL interdit `INACTIVE` sans date de fin. Les grants restent contrôlés à l’instant réel de l’accès et ne sont jamais ressuscités par un `asOf` passé.

La propension est sélectionnée avec `score.as_of_date <= asOf` et `score.valid_until IS NULL OR score.valid_until >= asOf`; les opportunités entrant dans sa priorité rules-only vérifient `generated_at < fin exclusive de journée asOf` et `expires_at IS NULL OR expires_at >= fin exclusive`. Un score futur ou expiré, une opportunité future ou une opportunité expirée est donc exclu par Portfolio Service avant composition. Une sélection de visibilité à date exclut aussi tout snapshot futur. FI réapplique localement la fenêtre `[asOf-364 jours, asOf]` aux lignes Signal/Opportunity reçues et la borne `expiresAt` aux opportunités, sans faire confiance au seul filtrage distant. À défaut d’historique de transitions Signal/Opportunity, FI omet leurs statuts courants (`status=null`), déclare `stateAsOfStatus=NOT_IMPLEMENTED` et marque la réponse partielle ; aucune apparence d’état historique n’est fabriquée.

Les mentions ML ne sont attestées que si Portfolio Service retourne un objet de contrat valide contenant simultanément `method=RULES_ONLY`, `mlObservationMode=POC_SHADOW`, `rulesWeight=1` et `mlWeight=0`. Une forme mal typée, un champ obligatoire absent, un mode non shadow ou une influence ML provoque un refus `502 DEPENDENCY_INVALID_RESPONSE`. Une source Portfolio absente produit `mlGovernanceStatus=UNAVAILABLE` avec les champs de mode et poids à `null`.

Le portfolio et la société restent des clés de ressource, jamais des preuves d’autorisation. La propriété économique d’une PME par un fonds ne vaut pas consentement bancaire. `DataAccessGrant` ne représente qu’une abstraction technique ; sa signification juridique est **HYPOTHÈSE À VALIDER AVEC BOA**.

## Audit et données minimales

Chaque décision `ALLOW` ou `DENY` écrit un événement append-only contenant le sujet, le client OAuth, le Consumer, le portfolio, la société lorsqu’elle est connue, l’endpoint, le scope, le résultat, le code motif, le `traceId`, le purpose et la référence d’autorisation. Aucun bearer, secret, payload financier, IBAN ou transaction brute n’est journalisé. Les triggers prouvent l’append-only contre les mutations DML directes, pas contre un DBA propriétaire capable d’altérer le DDL ; une garantie WORM exige une séparation de rôles et un stockage externe, **HYPOTHÈSE À VALIDER AVEC BOA**.

## Blocages production

La production reste **BLOCKED** jusqu’à validation IAM BOA, consentement/DPO, classification des données, réseau et mTLS interservices, coffre de secrets, rotation des clients OIDC, SIEM et monitoring, rétention, haute disponibilité, disaster recovery, tests d’intrusion, charge concurrente, correction des vulnérabilités d’image et homologation formelle.
