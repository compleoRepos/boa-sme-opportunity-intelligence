# Note RSSI et conformité — BOA SME Opportunity Intelligence

**Version de la note :** 1.0
**Date de référence du dépôt :** 19 septembre 2026
**Périmètre :** revue documentaire et technique du dépôt `boa-sme-opportunity-intelligence`
**Destinataires :** RSSI, conformité, DPO/juridique, architecture, production, data/IA et propriétaires BOA des systèmes sources
**Nature :** note de cadrage et d’écarts pour un pilote contrôlé ; **ce document n’est pas une homologation de production**.

## 1. Décision de lecture

Le dépôt constitue un **pilote local techniquement structuré** d’intelligence commerciale pour portefeuilles PME. Il combine des règles versionnées, des métriques, des signaux, des opportunités explicables, un modèle de propension commerciale exécuté sur CPU, des actions et des outcomes. La preuve disponible concerne des données synthétiques et un environnement local Docker Compose. Elle ne prouve ni la conformité d’un traitement BOA réel, ni la sécurité d’une plateforme de production bancaire, ni une performance métier BOA.

La décision prudente est donc la suivante : **pilote local contrôlé autorisable sous conditions ; production BOA : NO-GO à ce stade**. Le passage en production doit rester bloqué tant que BOA n’a pas décidé l’hébergement, la classification et les finalités des données, l’identité et les périmètres d’accès, le chiffrement, les secrets, l’audit fort, la sauvegarde-restauration, la continuité, l’observabilité et l’homologation de sécurité. Cette conclusion reprend l’état consolidé du dépôt dans [`docs/audit/ETAT-REEL-2026-09-19.md`](./audit/ETAT-REEL-2026-09-19.md) et [`docs/finalization-status-2026-09-19.md`](./finalization-status-2026-09-19.md).

Deux limites métier sont non négociables :

1. Le système **ne prend aucune décision de crédit**. Il ne produit ni score de crédit, ni score de risque, ni probabilité de défaut, ni décision d’octroi, de refus, de limite, de prix ou de montant. `FINANCIAL_STRESS_SIGNAL` est un signal relationnel à examiner par un humain ; il ne doit pas être présenté comme un risque ou une décision de crédit. Cette règle est documentée dans [`docs/data-model.md`](./data-model.md), [`docs/ml-engine.md`](./ml-engine.md) et [`docs/test-plan.md`](./test-plan.md).
2. Le POC utilise un **ML classique CPU-only**, en mode `POC_ASSISTIVE` et, pour l’usage prudent initial, en mode `ML_SHADOW` ou `RULES_ONLY`, faute de labels BOA matures. **Aucun LLM ni GPU n’est requis, appelé ou autorisé dans le chemin actuel.** La documentation précise qu’aucune performance BOA de production n’est revendiquée et qu’aucun entraînement sur des données réelles n’est autorisé avant les validations BOA nécessaires.

Aucune donnée BOA, aucun coût BOA, aucun KPI BOA, aucun seuil réglementaire BOA, aucun niveau de service BOA et aucune durée de conservation BOA ne sont inventés dans cette note. Lorsqu’une décision ne peut pas être prise à partir du dépôt, elle porte explicitement la mention **HYPOTHÈSE À VALIDER AVEC BOA**.

## 2. Légende des statuts et niveau de preuve

Les statuts sont employés strictement afin de séparer une capacité présente dans le code, une preuve d’exécution, une absence et une décision qui appartient à BOA.

| Statut | Signification dans cette note |
|---|---|
| **IMPLÉMENTÉ** | Une capacité ou un mécanisme est présent dans le code, la configuration ou la documentation technique. Sa présence ne vaut pas à elle seule sécurité de production. |
| **PROUVÉ** | Le dépôt apporte une inspection, un test ou un résultat local identifiable. La portée de la preuve est toujours précisée ; un résultat synthétique ou local n’est pas extrapolé à BOA. |
| **NON IMPLÉMENTÉ** | Aucun mécanisme ou aucune preuve suffisante n’a été trouvé dans le périmètre revu. |
| **À VALIDER** | Une décision d’architecture, de conformité, de sécurité, de métier ou de risque appartient à BOA. La mention **HYPOTHÈSE À VALIDER AVEC BOA** est utilisée pour toute donnée, volumétrie, coût, KPI, seuil, durée ou exigence non démontrée. |

## 3. Synthèse par domaine : état, limite et décision BOA

| Domaine | État prouvé dans le dépôt | Limite constatée | Décision BOA requise |
|---|---|---|---|
| Positionnement métier | **PROUVÉ** : outil d’aide commerciale ; absence de décision de crédit documentée et testée. | La frontière doit être maintenue dans les écrans, exports, emails, contrats et formations. | **À VALIDER** : usages interdits, propriétaire du risque et formulation réglementaire. |
| ML et IA générative | **PROUVÉ** : modèle logistique de propension sur CPU, données synthétiques, fallback `RULES_ONLY`, absence de dépendance LLM/GPU. | Labels BOA, calibration et performance réelle non démontrés ; le mode de production n’est pas autorisé. | **À VALIDER** : maintien en `ML_SHADOW`/`RULES_ONLY`, critères de sortie et revue indépendante. |
| Hébergement | **PROUVÉ** : Docker Compose local, PostgreSQL et Keycloak ; aucune ressource cloud créée. | Pas de cible BOA, HA, résidence ou séparation de zones démontrée. | **À VALIDER** : datacenter/cloud/hybride, opérateur, régions, résidence, flux et responsabilités. |
| Menaces | **IMPLÉMENTÉ** : frontières réseau, OIDC, rôles, comptes techniques et contrôles applicatifs décrits. | Aucun modèle de menace BOA formel, test d’intrusion ou acceptation de risque n’est produit. | **À VALIDER** : scénarios, criticité, propriétaires, risques résiduels et plan de traitement. |
| Données personnelles | **PROUVÉ** : seed et identités de démonstration annoncés synthétiques ; présence de champs identifiants dans le modèle. | Base légale, données BOA réelles, droits des personnes et ré-identification non traités. | **À VALIDER** : qualification DPO, finalités, base légale, droits, transferts et mesures. |
| Classification et minimisation | **IMPLÉMENTÉ** : séparation des domaines et intention de minimisation dans la documentation. | Classification BOA, registre de champs et règles de purge non approuvés. | **À VALIDER** : classes, champs autorisés, masquage, agrégations, accès et durée par classe. |
| Chiffrement | **IMPLÉMENTÉ** seulement comme cible documentaire ; SMTP exige TLS dans le lot local. | HTTP local, chiffrement PostgreSQL, chiffrement au repos, clés et rotation de production non démontrés. | **À VALIDER** : TLS/mTLS, chiffrement au repos et champ, KMS/coffre, algorithmes et rotation. |
| Identité et RBAC | **PROUVÉ** partiellement : OIDC/JWT, validation de signature/issuer/audience, rôles et scopes. | `BOA_AUTH_DISABLED` et secrets de développement restent activables ; matrice exhaustive route × objet non prouvée. | **À VALIDER** : fédération, MFA, recertification, scopes et interdiction absolue du mode local hors développement. |
| Séparation des tâches | **PROUVÉ** partiellement : auteur/approbateur distincts pour certaines règles et gouvernance ML. | Comptes SQL, rôle local global et frontières de migration/runtime ne sont pas entièrement séparés. | **À VALIDER** : rôles, approbations, urgence, recertification et preuves de non-auto-approbation. |
| Comptes de service et secrets | **IMPLÉMENTÉ** : `client_credentials`, clients distincts, rôle de notification dédié. | Secrets `DevOnly-*`, valeurs de repli et absence de coffre/rotation/révocation de production. | **À VALIDER** : coffre, propriétaires, rotation, durée, révocation, accès opérateur et urgence. |
| Réseaux et exposition | **PROUVÉ** : réseaux Docker `edge`, `app` et `data`, navigateur limité au Gateway, conteneurs durcis localement. | Pas de segmentation BOA, WAF/rate limit, certificats ni contrôle réseau de production. | **À VALIDER** : zones, flux autorisés, filtrage sortant, bastion, proxy, WAF et journalisation réseau. |
| Moindre privilège SQL | **IMPLÉMENTÉ** partiellement : schémas par service et grants ciblés sur certains chemins. | Bootstrap accorde `CREATE` au rôle propriétaire ; lectures SQL inter-domaines et comptes runtime restent à réduire. | **À VALIDER** : matrice effective table/colonne, rôle migration séparé et suppression des droits inutiles. |
| Audit et append-only | **PROUVÉ** partiellement : audit, corrélation, versions, hash de décision ; triggers forts sur les tentatives de notification. | Audit central sans trigger anti-`UPDATE`/`DELETE`, chaîne signée, WORM/SIEM, rétention et contrôle DBA démontrés. | **À VALIDER** : immutabilité, horodatage de confiance, conservation, accès et valeur probatoire. |
| Traçabilité | **PROUVÉ** : `correlationId`, `requestId`, versions, provenance, `decision_hash` et chaîne métier documentée. | Pas de backend centralisé de traces/logs ni preuve de bout en bout sur environnement BOA. | **À VALIDER** : identifiants de référence, exigences d’audit, corrélation inter-systèmes et export. |
| Rétention et purge | **NON IMPLÉMENTÉ** comme politique BOA approuvée. | Les propositions documentaires ne sont ni des durées BOA ni une preuve de purge. | **À VALIDER** : durée par catégorie, gel légal, purge, archivage, dérivés, sauvegardes et exports. |
| Notifications | **PROUVÉ** pour le pilote local : outbox, TLS SMTP, adresses vérifiées, retries bornés et historique d’envoi. | Mailpit et domaines synthétiques ; relais, certificats, destinataires et conservation BOA absents. | **À VALIDER** : relais, domaines, expéditeurs, contenu, consentement, anti-spam, alertes et dead-letter. |
| Exports | **PROUVÉ** localement : XLSX borné, scope backend, neutralisation des formules, hash et audit. | Pas de diffusion externe, stockage durable, DLP, classification ou politique d’export BOA. | **À VALIDER** : rôles, champs, destinataires, durée, chiffrement, watermark, révocation et incidents. |
| Sauvegarde/restauration | **NON IMPLÉMENTÉ** en preuve exploitable. | Pas de `pg_dump`/WAL/restauration testée, réplication, RPO/RTO ou runbook complet. | **À VALIDER** : stratégie, fréquence, chiffrement, site de reprise, tests, RPO/RTO et responsables. |
| Observabilité | **PROUVÉ** partiellement : `/health`, `/ready`, `/metrics`, logs JSON et corrélation. | Prometheus/Grafana/OTel, alertes, SLO, traces distribuées et runbooks ne sont pas déployés dans le Compose revu. | **À VALIDER** : indicateurs, seuils, alertes, astreinte, rétention des logs et accès SOC. |
| Vulnérabilités | **IMPLÉMENTÉ** : CI avec Gitleaks, audits de dépendances et Trivy ; certains contrôles locaux sont documentés. | Aucun résultat CI distant complet, DAST, pentest ou SBOM signé n’est fourni comme preuve BOA. | **À VALIDER** : politique CVE, délais de correction, exceptions, pentest, SBOM et promotion. |
| Continuité et réversibilité | **PROUVÉ** partiellement : fallback ML et rollback métier versionné. | Pas de continuité multi-service ni rollback complet des images, schémas, secrets et infrastructure. | **À VALIDER** : scénarios de crise, dépendances, bascule, retour arrière, exercices et critères d’arrêt. |

## 4. Périmètre, architecture et frontières de confiance

Le pilote assemble un frontend React/TypeScript, un API Gateway, des services FastAPI, PostgreSQL, Keycloak et des APIs bancaires simulées. Le navigateur ne doit accéder ni à PostgreSQL, ni aux APIs internes, ni aux APIs bancaires simulées. Les services communiquent par HTTP interne dans le Compose local. La topologie et les valeurs locales sont décrites dans [`infrastructure/docker-compose.yml`](../infrastructure/docker-compose.yml), tandis que le positionnement et le démarrage sont décrits dans [`README.md`](../README.md) et [`docs/deployment.md`](./deployment.md).

Les frontières de confiance identifiables sont les suivantes : navigateur vers Gateway ; Gateway vers services métier ; services vers PostgreSQL ; services vers Keycloak/JWKS ; intégration vers systèmes sources simulés ; workers vers outbox et relais SMTP ; opérateurs vers les plans de contrôle et bases. Ces frontières sont une base de revue et non un modèle de menace BOA approuvé.

Le cluster PostgreSQL unique et local est une simplification de pilote. La séparation logique par schéma et par service facilite une évolution future, mais ne constitue pas à elle seule une séparation physique ou une homologation. La cible d’industrialisation est cloud-agnostique et n’implique aucun déploiement AWS, comme le rappelle [`docs/industrialization-governance.md`](./industrialization-governance.md).

### Décision d’hébergement

**État : PROUVÉ** pour un hébergement local de développement ; **NON IMPLÉMENTÉ** pour un hébergement BOA. Le dépôt ne permet pas de décider si la cible doit être un datacenter BOA, un cloud approuvé, une plateforme hybride ou un autre environnement. Aucun fournisseur, compte, région, zone de disponibilité ou service managé ne doit être supposé.

BOA doit décider le lieu de traitement, la résidence des données, les flux transfrontaliers, l’opérateur de la plateforme, la séparation des environnements, la responsabilité de PostgreSQL/Keycloak, les certificats, le support et les conditions de sortie. Tout choix de localisation, de volumétrie, de coût, de disponibilité ou de niveau de service est **HYPOTHÈSE À VALIDER AVEC BOA** tant qu’il n’est pas approuvé et mesuré.

## 5. Modèle de menace pour la revue RSSI

Le modèle ci-dessous est un cadre de contrôle dérivé du dépôt ; il ne prétend pas mesurer une vraisemblance ou un impact BOA. Les niveaux de risque quantifiés, les scénarios prioritaires et les risques acceptés sont **HYPOTHÈSE À VALIDER AVEC BOA**.

| Acteur ou événement | Actif menacé | Scénario | Contrôles présents | Limite et traitement attendu |
|---|---|---|---|---|
| Utilisateur non authentifié | Données PME, opportunités et transactions | Appel direct d’une route ou devinette d’un identifiant. | Bearer OIDC, `401/403`, Gateway et contrôles de rôle. | La couverture exhaustive route × objet × périmètre reste à démontrer ; test BOA requis. |
| Utilisateur authentifié mal habilité | Périmètre portefeuille/agence | Accès horizontal à un client, une opportunité, un export ou une action d’un autre périmètre. | Scopes, `branch_ids`, `customer_scopes`, `relationship_manager_ids`, tests E2E ciblés. | L’audit constate des contrôles de périmètre incomplets sur certaines routes ; matrice et tests négatifs complets requis. |
| Compte de service compromis | Données inter-domaines et capacité d’écriture | Jeton interne réutilisé pour lire ou modifier au-delà de sa fonction. | Clients OIDC distincts, `client_credentials`, rôles internes et certains contrôles HTTP. | Les secrets ne sont pas gérés par un coffre et les privilèges SQL transverses persistent ; séparation et rotation requises. |
| Opérateur ou DBA privilégié | Audit, décisions et données | Modification ou suppression d’une preuve historique. | `decision_hash`, audit applicatif, append-only fort sur certaines tables de notification. | L’audit central n’est pas immuable au sens fort ; rôle propriétaire séparé, chaîne signée et stockage immuable à décider. |
| Attaquant réseau | Tokens, données et commandes | Écoute, altération ou rejeu entre composants. | Réseaux Docker internes dans le pilote ; validation JWT et corrélation. | HTTP local et absence de TLS/mTLS de production ; architecture réseau et chiffrement à valider. |
| Système source défaillant ou falsifié | Provenance et qualité des faits | Doublons, absence de données transformée en absence d’opportunité, réponse partielle. | Hash, `import_batch`, idempotence et statuts de qualité documentés. | Adapters BOA réels absents ; contrat, intégrité, fraîcheur, timeout et repli à valider. |
| Dépendance indisponible | Continuité du service | Panne ML, PostgreSQL, Keycloak, service source ou SMTP. | Fallback `RULES_ONLY` pour ML ; health/readiness et retries ciblés. | La continuité multi-service, la restauration et la bascule ne sont pas démontrées. |
| Fuite par journal, trace ou export | Données personnelles et financières | Inclusion d’un token, secret, détail transactionnel ou identifiant excessif. | Règles documentaires, notes `notes_redacted`, exports audités, métriques sans `customerId`. | Classification, DLP, tests anti-fuite, chiffrement et rétention ne sont pas approuvés. |
| Altération d’un artefact ML ou d’une règle | Recommandation et explicabilité | Chargement d’un artefact non approuvé ou d’une version non prévue. | Registre, statut, checksum, approbations distinctes et versions persistées. | Revue indépendante, signature de l’artefact, chaîne de livraison et rollback d’infrastructure à valider. |
| Usage détourné en crédit | Client, conformité et risque de modèle | Présentation de `FINANCIAL_STRESS_SIGNAL` ou d’un score de propension comme décision de crédit. | Vocabulaire interdit, tests et avertissements documentés. | Contrôles de contenu, formation, revue juridique et surveillance des usages BOA requis. |

## 6. Données personnelles, classification et minimisation

### 6.1 Données effectivement décrites

Le modèle contient notamment `legal_name`, `trade_name`, `customer_ref`, `tax_identifier_hash`, `email_hash`, sujet OIDC, affectation au chargé de clientèle, comptes, soldes, transactions, contreparties, actions et réponses. Les champs ne doivent pas être considérés anonymes du seul fait qu’un UUID ou un hash est utilisé. Un identifiant déterministe reste corrélable et peut constituer une donnée pseudonymisée.

Le dépôt indique que les données et identités de démonstration sont synthétiques et que les noms réels bancaires ne figurent pas dans le seed. Cela constitue une **preuve de pilote synthétique**, non une réponse à la question de savoir quelles données BOA seront importées. Le registre des traitements, la base légale, les droits des personnes, les transferts, les pays de traitement, les obligations de secret bancaire et la qualification de chaque champ ne sont pas fournis.

### 6.2 Classification proposée, à décider par BOA

La grille suivante est un support de décision. Elle ne constitue pas la classification BOA. Chaque classe, chaque champ et chaque usage sont **HYPOTHÈSE À VALIDER AVEC BOA**.

| Classe proposée | Exemples du modèle | Principe de minimisation |
|---|---|---|
| Identification relationnelle | `customer_ref`, nom légal, secteur, segment, agence, RM, sujet OIDC | Exposer seulement les champs nécessaires au périmètre et à la finalité de service. |
| Données financières détaillées | compte, solde, montant, devise, date de valeur, contrepartie | Préférer agrégats et identifiants techniques ; interdire la copie dans les logs, traces, emails et exports non nécessaires. |
| Données dérivées | métriques, signaux, scores de propension, explications, priorités | Conserver la version, la source et la date d’observation ; interdire toute interprétation crédit. |
| Données d’action et de relation | acteur, action, outcome, réponse, note expurgée | Structurer les valeurs ; exclure les notes libres et informations sensibles non nécessaires. |
| Configuration et gouvernance | règles, politiques, modèles, approbations, checksums | Séparer auteur, approbateur, opérateur et lecteur ; conserver l’historique nécessaire à la preuve. |
| Audit et exploitation | `correlationId`, `requestId`, résultat, horodatage, erreur technique | Ne jamais journaliser secret, token, payload complet ou donnée client inutile. |

La minimisation doit être appliquée à la collecte, aux snapshots, aux copies inter-domaines, aux logs, aux métriques, aux traces, aux emails, aux exports, aux sauvegardes et aux jeux dérivés. Le dépôt exprime cette intention mais ne fournit pas de registre de champs approuvé, de tests exhaustifs anti-fuite ni de procédure de purge. La classification, les finalités et la minimisation sont donc **À VALIDER** par DPO/juridique, sécurité, métiers et propriétaires des données BOA.

## 7. Chiffrement et protection des secrets

### 7.1 État constaté

L’environnement local utilise des URLs HTTP et contient des valeurs de développement `DevOnly-*` dans le Compose et les fichiers associés. Le lot de notifications exige TLS pour l’authentification SMTP et les messages locaux ne contiennent pas de détail transactionnel. Ces contrôles sont utiles dans le pilote mais ne démontrent pas le chiffrement d’un environnement BOA.

Le dépôt ne prouve pas le chiffrement en transit entre navigateur, Gateway, services, PostgreSQL, Keycloak et systèmes sources réels. Il ne prouve pas non plus le chiffrement au repos, le chiffrement de champ, la gestion de clés, le coffre, la rotation, la révocation, la séparation des administrateurs de clés et des administrateurs de données, ou la restauration d’une sauvegarde chiffrée.

### 7.2 Décisions BOA

BOA doit décider, avant toute donnée réelle, les exigences TLS/mTLS par frontière, la validation des certificats et noms, les versions cryptographiques autorisées, le chiffrement de PostgreSQL et des sauvegardes, les champs nécessitant une protection supplémentaire, le coffre ou KMS, la rotation et la procédure d’urgence. Les algorithmes, fréquences de rotation, coûts, performances, niveaux de chiffrement et obligations de certification sont **HYPOTHÈSE À VALIDER AVEC BOA** lorsqu’ils ne sont pas démontrés.

Les secrets doivent être retirés des littéraux versionnés et des valeurs de repli hors profil local. Ils doivent être injectés depuis un mécanisme approuvé, non copiés dans les images, les logs, les commandes, les exports ou les sauvegardes non chiffrées. Le passage hors développement doit échouer si un secret `DevOnly-*` ou `BOA_AUTH_DISABLED=true` est actif ; cette mesure est une décision de durcissement à faire valider et à prouver par test.

## 8. Identité, RBAC et séparation des tâches

### 8.1 Identité et autorisation

`platform.py` vérifie l’absence de bearer token, la signature JWT via JWKS, l’audience, l’issuer, l’expiration et les claims requis. Les rôles et scopes incluent notamment `RELATIONSHIP_MANAGER`, `BRANCH_MANAGER`, `DATA_ANALYST`, `BUSINESS_ANALYST`, `RULE_APPROVER`, `ADMIN` et `SERVICE` selon les routes. Le frontend est documenté avec Authorization Code et PKCE. Ces éléments sont **IMPLÉMENTÉS** et partiellement **PROUVÉS** par les tests et la revue de sécurité décrits dans [`docs/audit/workstreams/security-ops.md`](./audit/workstreams/security-ops.md).

La limite critique est `BOA_AUTH_DISABLED=true`. Dans ce mode local, le principal de secours cumule des rôles et un périmètre global ; `X-Dev-Principal` permet de rejouer une persona locale. Le README réserve ce mode aux données synthétiques et au développement, mais la configuration ne fournit pas à elle seule une preuve qu’il est impossible de l’activer dans un environnement exposé. La matrice exhaustive route × rôle × agence × portefeuille × objet, y compris tokens expirés, issuer/audience incorrects, révoqués ou malformés, n’est pas entièrement prouvée.

BOA doit approuver le fournisseur d’identité, la fédération, le MFA, la durée et la révocation des sessions, le mapping des rôles, les scopes d’agence et de portefeuille, la recertification périodique et le propriétaire de chaque habilitation. L’absence de décision sur ces points est **HYPOTHÈSE À VALIDER AVEC BOA**.

### 8.2 Séparation des tâches

Le Rule Studio et la gouvernance ML portent une séparation auteur/approbateur et des workflows versionnés. Le modèle et la politique ne s’auto-promouvent pas ; les versions et approbations sont auditées. Il s’agit d’un contrôle **PROUVÉ** sur le périmètre couvert par les tests et documents.

En revanche, le bootstrap PostgreSQL rend chaque rôle propriétaire de son schéma et lui accorde `CREATE`, le compte de migration n’est pas complètement séparé du runtime dans la preuve disponible, et plusieurs composants partagent encore des accès SQL ou des lectures inter-domaines. Le rôle local de secours cumule également des privilèges qui ne doivent jamais exister hors développement.

BOA doit décider la séparation entre administrateur IAM, auteur de règle, approbateur, release manager, opérateur, DBA, propriétaire de données, analyste et auditeur. Elle doit également décider la procédure d’urgence, le contrôle à quatre yeux, la recertification et la conservation des preuves. Aucun seuil de recertification, délai de révocation ou effectif d’équipe n’est inventé : toute valeur est **HYPOTHÈSE À VALIDER AVEC BOA**.

## 9. Comptes de service, réseaux et moindre privilège SQL

Les appels internes utilisent des jetons de service `client_credentials` et des clients distincts. Le worker de notification possède un lecteur dédié et les capacités de génération/dispatch sont réservées aux profils prévus. Le Gateway n’a pas de connexion SQL métier observée. Les conteneurs locaux utilisent `no-new-privileges`, `cap_drop: ALL`, un système de fichiers en lecture seule pour les services backend et des limites de ressources. Ces contrôles sont **IMPLÉMENTÉS** et **PROUVÉS** dans le périmètre local documenté.

La séparation SQL reste incomplète. Le bootstrap [`infrastructure/postgres/00-init-service-schemas.sh`](../infrastructure/postgres/00-init-service-schemas.sh) accorde `USAGE, CREATE` au rôle de schéma. Le script de migration et l’audit d’industrialisation indiquent des droits larges et des lectures inter-domaines encore nécessaires pour Analytics, Opportunity, Action et Portfolio. La cible documentée recommande un compte de migration séparé, des comptes runtime sans `CREATE`, et des vues/API limitées aux colonnes nécessaires. Cette cible n’est pas une preuve de configuration effective.

La décision BOA doit porter sur la matrice effective `service × rôle SQL × schéma × table × colonne × opération`, les propriétaires de schéma, le compte de migration, les accès de support, la surveillance des privilèges et l’expiration des exceptions. Les droits minimaux, la liste des tables autorisées et les éventuels accès temporaires sont **HYPOTHÈSE À VALIDER AVEC BOA** jusqu’à exécution d’une batterie SQL de refus et d’autorisation sur l’environnement cible.

Les réseaux de production doivent limiter les flux au Gateway, aux APIs internes, à l’identité, à la base, aux systèmes sources, au relais SMTP et à l’observabilité nécessaires. La segmentation, le filtrage sortant, le proxy, le WAF, la limitation de débit, le DNS, le bastion et la journalisation réseau ne sont pas fournis par le pilote local et sont **À VALIDER**.

## 10. Audit append-only, traçabilité et preuve

### 10.1 Ce qui est présent

Les entités d’audit et de décision conservent acteur ou service, action, ressource, résultat, horodatage, `correlation_id`, `request_id`, versions, références d’entrée et métadonnées. `DecisionAudit` et le service d’audit calculent un hash canonique SHA-256 ; les versions de moteur, de règles, de policy, de features et les watermarks contribuent à la reconstitution. La chaîne fonctionnelle documentée est notamment : opportunité → run moteur → règle → signal → snapshot analytique → transactions/soldes → source record → import batch → système source. Ces éléments sont **PROUVÉS** comme mécanismes applicatifs et comme preuves de pilote.

Le lot de notifications apporte une garantie plus forte sur `notification_delivery_attempts`, avec refus SQL de `UPDATE`, `DELETE` et `TRUNCATE`, et des droits minimaux documentés. Cette garantie est limitée à ce périmètre et ne doit pas être généralisée à `audit.audit_logs` ou `decision_audit`.

### 10.2 Limites de l’append-only

Pour l’audit central, le dépôt ne démontre pas de trigger SQL anti-`UPDATE`/`DELETE`, de rôle propriétaire indépendant, de chaîne de hash entre événements, de signature indépendante, de stockage WORM, d’export vers SIEM, de rétention ou de contrôle d’un DBA. Un `decision_hash` permet une détection partielle d’altération du contenu mais ne prouve pas qu’une ligne supprimée sera détectée, ni que l’identité de la clé de hash est protégée.

L’exigence d’audit réglementaire fort, la source de temps de confiance, la conservation, les accès d’audit, la séparation DBA/audit, la chaîne de hash ou signature, le WORM/SIEM et les tests d’altération sont **À VALIDER AVEC BOA**. Le passage en production ne doit pas qualifier l’audit d’« immuable » sur la seule présence d’un hash applicatif.

## 11. Rétention, notifications et exports

### 11.1 Rétention et purge

Le modèle distingue données sources, données dérivées, opportunités, actions, règles, features, modèles, labels, logs, imports, outbox et audits. Il conserve les versions utiles à la reconstitution et privilégie la désactivation ou le statut terminal plutôt que la suppression destructive. Il ne fournit cependant aucune politique BOA approuvée de durée, de purge, d’archivage, de gel légal, d’effacement, de purge des dérivés ou de purge des sauvegardes.

Pour chaque catégorie, BOA doit décider la durée active, l’archivage, le gel lié à un litige, la purge contrôlée, les copies de secours, les exports, les datasets dérivés et la preuve de destruction. Toute durée ou fréquence non fournie par BOA est **HYPOTHÈSE À VALIDER AVEC BOA**. La rétention ne doit pas être déduite de la durée du pilote, d’une fenêtre analytique ou d’un défaut de configuration.

### 11.2 Notifications

Le lot [`docs/lots/LOT-06-NOTIFICATIONS-EMAIL.md`](./lots/LOT-06-NOTIFICATIONS-EMAIL.md) fournit une preuve locale d’un worker, d’une outbox durable, d’un compte `notification-service`, d’un rôle de lecture de synthèse, d’adresses OIDC vérifiées, de TLS SMTP, de retries bornés, de dead-letter et d’un historique de livraison protégé. Le contenu de synthèse n’inclut pas de nom de PME ni de détail transactionnel dans la preuve locale.

La livraison SMTP BOA est **NON IMPLÉMENTÉE / BLOQUÉE**. Mailpit, `synthetic.invalid`, les certificats, le relais, les domaines expéditeurs, les destinataires réels, les politiques anti-spam, la supervision, les dead-letters, la conservation des messages et les procédures d’incident ne sont pas disponibles. BOA doit décider les canaux, la finalité, les destinataires autorisés, la vérification d’adresse, le contenu maximal, le chiffrement, les journaux et la purge. Toute cadence, tout volume, tout seuil d’alerte ou tout délai de retry qui ne résulte pas d’une preuve BOA est **HYPOTHÈSE À VALIDER AVEC BOA**.

### 11.3 Exports

Le lot [`docs/lots/LOT-04-EXPORTS-EXCEL.md`](./lots/LOT-04-EXPORTS-EXCEL.md) documente une génération XLSX côté backend, un contrôle de périmètre côté serveur, la neutralisation des formules, un hash de fichier dans l’audit et l’absence de stockage durable par le produit. Le plafond de 10 000 lignes est un contrôle du pilote local documenté ; **ce n’est pas un seuil BOA ni un engagement de capacité**.

L’export BOA doit faire l’objet d’une décision sur les rôles, les champs, la classification, les destinataires, la justification, le téléchargement, le chiffrement, le watermark, la durée de vie, la révocation, les partages et la réponse à une fuite. DLP, stockage de fichiers, export massif asynchrone, rétention et diffusion externe ne sont pas démontrés. Tout volume, délai de disponibilité, fréquence ou seuil d’export non validé est **HYPOTHÈSE À VALIDER AVEC BOA**.

## 12. Sauvegarde, restauration, continuité et réversibilité

### 12.1 Sauvegarde et restauration

La présence d’un volume PostgreSQL dans Docker Compose n’est pas une sauvegarde. Le dépôt ne fournit pas de preuve exploitable de sauvegarde complète, WAL ou réplication, stockage chiffré, verrouillage contre l’effacement, restauration PostgreSQL, restauration Keycloak, restauration des secrets/certificats, rejeu d’outbox/imports, contrôle de cohérence ou exercice périodique. La documentation classe donc HA, backup et secrets de production **NON IMPLÉMENTÉS**.

BOA doit décider la stratégie de sauvegarde, la séparation du domaine de panne, la protection contre suppression anticipée, la localisation, le chiffrement, la fréquence, les responsables, les contrôles d’intégrité et les exercices. Les valeurs RPO/RTO sont absentes du dépôt ; tout chiffre, toute fréquence et tout objectif de reprise sont **HYPOTHÈSE À VALIDER AVEC BOA**. La sortie attendue est une restauration observée sur un environnement équivalent, avec mesure réelle et rapport rattaché à une version.

### 12.2 Continuité

Le fallback ML vers `RULES_ONLY` est **PROUVÉ** pour les scénarios locaux de panne ML. Il protège le chemin déterministe contre l’indisponibilité du score, mais ne constitue pas un plan de continuité global. Les pannes de PostgreSQL, Keycloak, Gateway, services sources, outbox, SMTP, stockage de sauvegarde ou réseau ne sont pas couvertes par une reprise multi-service démontrée.

BOA doit définir les services critiques, le mode dégradé acceptable, la communication d’incident, l’ordre de redémarrage, les dépendances, la bascule, le retour au nominal, les critères d’arrêt du pilote et les exercices. Les niveaux de criticité, délais, effectifs d’astreinte et fréquences d’exercice sont **HYPOTHÈSE À VALIDER AVEC BOA**.

### 12.3 Réversibilité

Les versions de règles, scoring policies et modèles peuvent être retirées ou restaurées dans les périmètres testés. Un recalcul versionné ne doit pas réécrire les décisions historiques. Cette réversibilité métier est **PROUVÉE** localement.

Elle ne couvre pas de manière démontrée les images, la configuration, les secrets, Keycloak, les migrations SQL, le frontend, les volumes, les certificats, l’infrastructure ou les adaptateurs réels. BOA doit décider le plan de sortie, la portabilité des données, les formats d’export, la restitution aux systèmes sources, la destruction des copies, la compatibilité N/N-1, le fournisseur de remplacement et les conditions de retour. Tout délai ou coût de réversibilité est **HYPOTHÈSE À VALIDER AVEC BOA**.

## 13. Observabilité, vulnérabilités et exploitation

### 13.1 Observabilité

Les services exposent `/health`, `/ready` et `/metrics`. Le middleware produit des logs JSON avec service, méthode, chemin, statut, durée et corrélation. Les appels internes propagent `X-Correlation-ID`. Ces capacités sont **IMPLÉMENTÉES** et partiellement **PROUVÉES** sur le pilote.

Le Compose revu ne déclare pas de Prometheus, Grafana ou `otel-collector`; la variable OTLP est vide par défaut. Aucun dashboard, canal d’alerte, trace distribuée, SLO, runbook d’incident ou backend centralisé de logs n’est fourni comme preuve de production. Les métriques actuelles ne démontrent pas la latence par route, la saturation, le pool SQL, les retries, les dépendances, les refus RBAC, le taux de fallback ou le retard d’import de façon opérable.

BOA doit décider les signaux de sécurité et d’exploitation, les seuils, la rétention, les accès SOC, les alertes, l’astreinte, les runbooks et la gestion d’une panne de l’observabilité. Tout seuil, KPI, SLO, budget de latence, volume d’alerte ou durée de conservation non mesuré dans un environnement représentatif est **HYPOTHÈSE À VALIDER AVEC BOA**.

### 13.2 Vulnérabilités et chaîne de livraison

Le workflow CI contient lint, typage, tests, Gitleaks, `pip-audit`, `npm audit`, construction d’images et Trivy sur les niveaux élevés/critiques. Les conteneurs locaux sont durcis sur plusieurs aspects. Cela est **IMPLÉMENTÉ** comme chaîne de contrôle et **PROUVÉ** seulement dans la portée des exécutions locales ou des documents explicitement rattachés à un run.

L’audit ne fournit pas de résultat CI distant complet rattaché à une release BOA, de DAST, de pentest formel, de SBOM signé, de provenance SLSA, de scan IaC spécialisé, de procédure d’exception CVE ou de délai de correction approuvé. Les niveaux de sévérité, délais de patch, taux acceptable d’exception et conditions de promotion sont **HYPOTHÈSE À VALIDER AVEC BOA**.

La commande `pytest` exécutée directement à la racine est également documentée comme non reproductible sans préparation du chemin d’import, tandis que la CI prépare un autre environnement. Cette divergence concerne la fiabilité de la preuve de livraison ; elle ne doit pas être masquée par le seul succès de tests ciblés.

## 14. Absence de décision automatique de crédit et absence de LLM

Le contrôle de non-détournement est une exigence de sécurité, de conformité et de modèle. Les règles, signaux, scores et explications doivent rester dans le vocabulaire d’une **opportunité commerciale**. Une sortie ne doit jamais décider automatiquement d’un octroi, refus, montant, limite, tarif, risque ou défaut.

Le score ML est une propension commerciale relative, non une probabilité de crédit. Le premier incrément reste sur données synthétiques, sans labels BOA matures, et doit rester en `POC_ASSISTIVE`, `ML_SHADOW` ou `RULES_ONLY` selon la décision de gouvernance. Les métriques de production BOA sont absentes ; aucune précision, AUC, calibration, lift, uplift, confusion matrix ou KPI commercial BOA ne doit être fabriqué.

Aucun LLM, SDK, modèle, secret, endpoint, appel externe ou dépendance GPU n’est présent dans le chemin actuel. Les explications sont structurées et déterministes. Une future narration éventuelle ne pourrait pas modifier le score, l’éligibilité, la priorité, le signal relationnel ou une décision. Toute extension LLM serait un nouveau périmètre à analyser par BOA ; elle n’est ni requise ni autorisée implicitement par le pilote.

## 15. Conditions minimales avant une décision de production

Avant toute connexion à des données BOA ou à un système source réel, les éléments suivants doivent être produits et approuvés :

1. une décision d’hébergement, de résidence, de réseau et de responsabilité opérationnelle ;
2. un registre des traitements et une classification champ par champ, avec finalités, minimisation, base légale et droits ;
3. une matrice d’habilitation et de périmètre testée sur toutes les routes sensibles, avec séparation des tâches ;
4. un coffre de secrets, une politique de rotation et un contrôle interdisant les valeurs de développement hors local ;
5. une configuration TLS/mTLS, chiffrement au repos, gestion de clés et certificats ;
6. une matrice SQL effective, des comptes runtime sans droit de migration et une réduction des accès transverses ;
7. un audit append-only fort avec contrôle indépendant, rétention et export vers un stockage immuable ou un SIEM approuvé ;
8. une politique de rétention et de purge couvrant données sources, dérivés, logs, exports, sauvegardes et labels ;
9. des règles BOA pour notifications et exports, incluant destinataires, contenu, chiffrement et incidents ;
10. une sauvegarde chiffrée, une restauration complète testée et des objectifs de continuité approuvés ;
11. une observabilité opérable avec alertes, dashboards, traces, accès SOC et runbooks ;
12. une campagne de vulnérabilités, pentest, DAST, SBOM/provenance et gestion des exceptions ;
13. une validation indépendante du ML ou une décision documentée de rester durablement en `RULES_ONLY`/`ML_SHADOW` ;
14. un plan de réversibilité et de rollback couvrant code, schéma, configuration, identité, secrets, données et infrastructure ;
15. une décision formelle RSSI/conformité/DPO et un go/no-go BOA fondés sur des preuves rattachées à la version promue.

Ces éléments sont des **conditions de gouvernance proposées**, non des résultats déjà obtenus. Leur contenu détaillé, leur ordre, leur responsable, leur délai, leur coût et leurs critères de sortie sont **HYPOTHÈSE À VALIDER AVEC BOA**.

## 16. Conclusion RSSI

Le dépôt est exploitable comme **pilote local synthétique** et démontre un socle applicatif utile : identité OIDC, rôles, séparation de domaines, audit applicatif, outbox, explication déterministe, fallback `RULES_ONLY`, modèle ML CPU-only et contrôles de livraison. Les documents de référence décrivent aussi des lots locaux de notifications et d’exports avec des protections ciblées.

Ce socle ne doit pas être présenté comme une homologation, une certification, une architecture BOA de production ou une mesure de performance réelle. Les secrets de développement, le mode d’authentification désactivable, le chiffrement de production, les privilèges SQL, l’audit fort, la rétention, les sauvegardes/restaurations, l’observabilité opérable, la continuité, les vulnérabilités et les données BOA réelles restent des décisions ou travaux ouverts.

La position recommandée est donc **GO limité pour un pilote local contrôlé, avec données synthétiques et sans raccordement bancaire réel ; NO-GO pour production BOA**. Aucune décision de crédit n’est prise. Le ML classique reste CPU-only et en POC/shadow faute de labels BOA matures. Aucun LLM ni GPU n’est requis. La prochaine décision appartient aux fonctions BOA compétentes sur la base d’artefacts de preuve et non de la seule réussite d’un Compose local.

## Références internes

[1]: ../README.md "README et périmètre du pilote local"
[2]: ./audit/ETAT-REEL-2026-09-19.md "État réel et audit consolidé du dépôt"
[3]: ./finalization-status-2026-09-19.md "Rapport final de finalisation technique"
[4]: ./security.md "Exigences et contrôles de sécurité du MVP"
[5]: ./deployment.md "Déploiement local et trajectoire"
[6]: ./data-model.md "Modèle relationnel et pipeline de données synthétiques"
[7]: ./ml-engine.md "Architecture ML CPU et gouvernance du score"
[8]: ./industrialization-governance.md "Gouvernance d’industrialisation et audit d’accès aux données"
[9]: ./audit/workstreams/security-ops.md "Audit sécurité et opérations"
[10]: ./lots/LOT-04-EXPORTS-EXCEL.md "Exports Excel sécurisés du pilote local"
[11]: ./lots/LOT-06-NOTIFICATIONS-EMAIL.md "Notifications email et synthèse quotidienne"
[12]: ./test-plan.md "Plan de tests et limites de preuve"
[13]: ../infrastructure/docker-compose.yml "Composition Docker locale et réseaux"
[14]: ../infrastructure/postgres/00-init-service-schemas.sh "Bootstrap des rôles et schémas PostgreSQL"
[15]: ../backend/src/boa_oi/platform.py "Authentification, rôles, corrélation et endpoints opérationnels"
[16]: ../backend/src/boa_oi/audit/service.py "Service d’audit et hash canonique"
[17]: ../backend/src/boa_oi/export_xlsx.py "Génération des exports XLSX"
[18]: ../.github/workflows/ci.yml "Workflow CI et scans de sécurité"
[19]: ../tests/e2e/governance.spec.ts "Tests E2E de gouvernance, RBAC et rollback"
[20]: ../scripts/validate-notifications.sh "Validation locale des notifications"
[21]: ../scripts/validate-ml-integration.sh "Validation locale de l’intégration ML"

> **Note de preuve.** Les références internes sont des liens relatifs au dépôt. Les statuts et constats sont limités aux fichiers et exécutions décrits dans ces sources ; ils ne remplacent ni un audit BOA, ni un test d’intrusion, ni une homologation, ni une validation DPO ou conformité.

## Points ouverts soumis à BOA

- Choisir l’hébergement, la résidence, les zones, les flux, l’opérateur et le modèle de responsabilité.
- Approuver la classification des données, les finalités, la minimisation, la base légale, les droits et les transferts.
- Décider l’usage autorisé du signal commercial et interdire formellement toute décision automatique de crédit.
- Décider le maintien en `RULES_ONLY` ou `ML_SHADOW` tant que les labels BOA ne sont pas matures, ainsi que les critères de revue indépendante.
- Approuver la fédération d’identité, le MFA, les rôles, les scopes, la recertification et le contrôle d’activation de `BOA_AUTH_DISABLED`.
- Séparer les tâches IAM, métier, data/IA, release, DBA, exploitation, sécurité et audit.
- Fournir le coffre de secrets, la rotation, la révocation, les certificats et les clés de chiffrement.
- Valider TLS/mTLS, chiffrement au repos, gestion de clés, filtrage réseau, WAF et exposition externe.
- Produire la matrice SQL effective et supprimer les droits runtime de migration et les accès transverses non nécessaires.
- Décider l’append-only fort, la chaîne de preuve, le WORM/SIEM, les accès DBA et la rétention d’audit.
- Fixer la rétention, la purge, l’archivage et le gel légal pour les sources, dérivés, logs, exports, sauvegardes et labels.
- Homologuer le relais SMTP, les domaines, les destinataires, le contenu, les règles anti-spam et les dead-letters.
- Encadrer les exports : champs, rôles, chiffrement, watermark, durée de vie, partage et réponse à incident.
- Définir et tester sauvegarde, restauration, HA, continuité, RPO/RTO et exercices périodiques.
- Déployer l’observabilité centralisée, les alertes, les SLO, les runbooks et l’accès SOC.
- Fixer la politique vulnérabilités, pentest, DAST, SBOM, provenance, exceptions et délais de correction.
- Définir la réversibilité complète, le rollback d’infrastructure et la sortie des données.
- Prononcer le go/no-go de chaque étape sur des preuves rattachées à une version, sans transformer le pilote local en homologation production.

Tous les éléments de cette liste qui ne sont pas démontrés par les sources internes restent **HYPOTHÈSE À VALIDER AVEC BOA**.

**Auteur par défaut :** Manus AI

**Statut de la note :** document livré ; décision de production non accordée.
