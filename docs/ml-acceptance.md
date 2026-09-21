# Acceptation de l’incrément ML

**Produit :** BOA SME Opportunity Intelligence  
**Statut :** G1 technique démontré localement ; G2/G3 bloqués faute d’historiques BOA et de validation indépendante
**Auteur :** Manus AI  
**Périmètre :** preuve d’acceptation du Feature Store, du ML Engine CPU-ready, de la fusion, des dashboards et de la gouvernance

> Ce document reste la checklist normative jusqu’à une éventuelle activation séparée. L’implémentation actuelle impose `POC_SHADOW` et une priorité opérationnelle `RULES_ONLY`. Les résultats locaux/synthétiques sont descriptifs ; aucun résultat ne vaut validation de performance, calibration, training-readiness ou gouvernance de production. Les blockers restent persistés tant que les historiques BOA observés, matures et approuvés ne sont pas disponibles.

## État de l’aperçu Studio ML au 21 septembre 2026

La branche `feat/ml-studio-parallel` implémente l’entraînement CPU gouverné, la progression persistée, l’annulation, l’idempotence, la comparaison, la séparation auteur/approbateur/admin et une interface en six onglets. Les portes locales passent avec 266 tests backend, 31 tests frontend et une migration PostgreSQL combinée jusqu’à `0019_ml_studio_catalog_merge`.[6]

Ce résultat ne franchit pas G2 ou G3. L’E2E Karim et la capture 1440 px ne sont pas exécutés, les historiques BOA sont absents et la simulation d’impact avant/après retourne explicitement `501 NOT_IMPLEMENTED` faute de dataset point-in-time serveur réunissant scores règles et ML. Aucune promotion, activation ou influence commerciale n’est autorisée.

## 1. Statuts et preuve attendue

Chaque contrôle reçoit un statut parmi `NOT_RUN`, `PASS`, `FAIL`, `BLOCKED` et `NOT_APPLICABLE`. `NOT_APPLICABLE` exige une justification approuvée et n’est pas autorisé pour un contrôle marqué **bloquant**.

Une preuve comporte : identifiant du contrôle, commit, image ou artefact, versions de contrats, environnement, dataset et manifeste, date, exécutant, commande ou scénario, résultat brut et lien vers les logs/audits. Une capture seule ne prouve ni la persistance, ni l’autorisation, ni la reproductibilité.

## 2. Portes d’activation

| Porte | Mode maximal autorisé | Conditions |
|---|---|---|
| G0 — architecture | `RULES_ONLY` | contrats revus, aucune implémentation revendiquée |
| G1 — technique | `ML_SHADOW` en test | moteur CPU, snapshots, registres, audit et sécurité validés |
| G2 — shadow | `ML_SHADOW` en environnement cible | données gouvernées, monitoring et rollback opérationnels |
| G3 — métier | `HYBRID_RERANK` | performance shadow, stabilité, segments et explications approuvés |
| G4 — candidate | `HYBRID_CANDIDATE` | hors MVP ; décision d’architecture et acceptation spécifiques |

Le passage d’une porte est enregistré avec l’approbateur, les versions exactes et la date d’effet. Une nouvelle version majeure de feature set, score contract, modèle ou fusion repasse par les contrôles concernés.

## 3. Checklist d’architecture et de dépendances

| ID | Contrôle | Critère de réussite | Blocage |
|---|---|---|---:|
| MLA-ARCH-001 | Chaîne de responsabilités | Analytics, Rule Engine, Feature Store, ML Engine et Opportunity Engine ont des contrats et ownership distincts | Oui |
| MLA-ARCH-002 | Stack | service cible Python 3.12/FastAPI, PostgreSQL, Keycloak et Docker Compose ; aucune base partagée sans ownership | Oui |
| MLA-ARCH-003 | CPU-only | inférence réussie sur Linux amd64 sans GPU/CUDA ; threads et mémoire bornés | Oui |
| MLA-ARCH-004 | Dépendances réseau | l’inférence fonctionne sans Internet et sans service cloud | Oui |
| MLA-ARCH-005 | LLM absent | aucun package, SDK, endpoint, secret, variable, modèle ou appel LLM dans build, SBOM, configuration et traces | Oui |
| MLA-ARCH-006 | Isolation SQL | aucun service ne lit un schéma tiers ; accès par API/événement uniquement | Oui |
| MLA-ARCH-007 | Fallback | indisponibilité ML retourne le chemin configuré `RULES_ONLY` ou suspend le lot sans score inventé | Oui |

## 4. Checklist Feature Registry et snapshots

| ID | Contrôle | Critère de réussite | Blocage |
|---|---|---|---:|
| MLA-FEAT-001 | Définition complète | chaque feature a sens métier, owner, source, type, unité, fenêtre, fraîcheur, qualité et usage autorisé | Oui |
| MLA-FEAT-002 | Usage interdit | chaque feature porte explicitement l’interdiction crédit/défaut/octroi/prix/limite | Oui |
| MLA-FEAT-003 | Version immuable | changer source, transformation, fenêtre, imputation ou qualité crée une nouvelle version | Oui |
| MLA-FEAT-004 | Point-in-time | un test prouve qu’aucune donnée postérieure à `asOf` n’entre dans le snapshot | Oui |
| MLA-FEAT-005 | Leakage outcome | actions et outcomes futurs sont absents des features d’entraînement et d’inférence | Oui |
| MLA-FEAT-006 | Offline/serving parity | le même cas produit les mêmes valeurs normalisées dans export offline et snapshot d’inférence | Oui |
| MLA-FEAT-007 | Qualité | missing, bornes, catégories inconnues, couverture et fraîcheur produisent le statut attendu | Oui |
| MLA-FEAT-008 | Lineage | le snapshot remonte aux métriques/signaux, versions, watermark et checksum | Oui |
| MLA-FEAT-009 | Idempotence | même client, `asOf`, feature set et watermark donnent un snapshot équivalent sans doublon | Oui |

## 5. Checklist Model Registry et artefact

| ID | Contrôle | Critère de réussite | Blocage |
|---|---|---|---:|
| MLA-MOD-001 | Métadonnées | registre complet : cible, horizon, population, features, dataset, cutoff, code, métriques, limites et approbations | Oui |
| MLA-MOD-002 | Intégrité | checksum de l’artefact validé avant readiness et chaque activation | Oui |
| MLA-MOD-003 | Compatibilité | feature set, runtime contract et score contract incompatibles sont refusés explicitement | Oui |
| MLA-MOD-004 | Self-test | vecteur de référence et sortie attendue réussissent au chargement | Oui |
| MLA-MOD-005 | Cycle de vie | seules versions `CHALLENGER`/`CHAMPION` approuvées sont servies selon mode ; aucune auto-promotion | Oui |
| MLA-MOD-006 | Séparation des tâches | auteur, validateur et approbateur respectent la politique ; aucune auto-approbation admin | Oui |
| MLA-MOD-007 | Reproductibilité | la version d’entraînement est reconstruisible depuis manifestes, code, features et dataset | Oui |
| MLA-MOD-008 | Rollback | retour au champion précédent ou à `RULES_ONLY` testé avec audit | Oui |
| MLA-MOD-009 | Sécurité artefact | SBOM et scan sans vulnérabilité critique ; aucun chargement arbitraire non maîtrisé | Oui |
| MLA-MOD-010 | Preuves persistées | la promotion résout manifest, snapshots labels/features et évaluation persistés ; une déclaration dans le payload ne suffit jamais | Oui |

## 6. Checklist du contrat de score

| ID | Contrôle | Critère de réussite | Blocage |
|---|---|---|---:|
| MLA-SCORE-001 | Bornes | `propensityScore` est numérique dans `[0,1]` ou absent lorsque le statut est invalide | Oui |
| MLA-SCORE-002 | Sémantique | `targetOutcome`, `horizon`, `opportunityType` et `scoreInterpretation` sont obligatoires | Oui |
| MLA-SCORE-003 | Versions | modèle, feature set, snapshot et contrat sont présents et résolubles | Oui |
| MLA-SCORE-004 | Fraîcheur | score expiré/stale ne participe pas à la fusion | Oui |
| MLA-SCORE-005 | Défaut interdit | feature manquante ou erreur ne devient jamais silencieusement `0`, `0.5` ou dernière valeur | Oui |
| MLA-SCORE-006 | Déterminisme d’inférence | même artefact, même snapshot et même configuration produisent la même sortie normalisée | Oui |
| MLA-SCORE-007 | Vocabulaire | réponses, logs et UI ne contiennent aucun champ `creditScore`, `riskScore`, `defaultProbability` ou équivalent | Oui |
| MLA-SCORE-008 | Non-crédit | un test négatif prouve que le score n’entraîne ni octroi, refus, limite, prix ni montant | Oui |

## 7. Checklist de fusion règles + ML

| ID | Contrôle | Critère de réussite | Blocage |
|---|---|---|---:|
| MLA-FUS-001 | Modes | `RULES_ONLY`, `ML_SHADOW`, `HYBRID_RERANK` ont une sémantique distincte et testée | Oui |
| MLA-FUS-002 | Shadow | en `ML_SHADOW`, opportunités, priorités et ordre visible sont identiques à `RULES_ONLY` | Oui |
| MLA-FUS-003 | Rerank borné | seules candidates éligibles par règles sont réordonnées ; formule et poids sont versionnés | Oui |
| MLA-FUS-004 | Garde-fous | qualité, fraîcheur, scope, produit actif, exclusions et finalité s’appliquent avant/après fusion | Oui |
| MLA-FUS-005 | Explication séparée | règle, propension et résultat de fusion sont affichés séparément | Oui |
| MLA-FUS-006 | Fallback audité | panne, incompatibilité ou drift bloquant basculent selon politique avec cause persistée | Oui |
| MLA-FUS-007 | Historique | changer de politique ne réécrit aucune décision passée | Oui |
| MLA-FUS-008 | Candidate ML | mode `HYBRID_CANDIDATE` absent ou désactivé dans le MVP initial | Oui |

## 8. Checklist explicabilité et audit

| ID | Contrôle | Critère de réussite | Blocage |
|---|---|---|---:|
| MLA-EXP-001 | Contributions | principaux facteurs positifs/négatifs, baseline, missing/imputations et méthode sont présents | Oui |
| MLA-EXP-002 | Sens métier | labels des features sont compréhensibles et ne prétendent pas expliquer une causalité | Oui |
| MLA-EXP-003 | Reconstruction | une prédiction et sa fusion sont reconstruites à partir des références persistées, sans recalcul divergent | Oui |
| MLA-EXP-004 | Append-only | prédictions, décisions, promotions, fallback et accès sensibles sont immuables/audités | Oui |
| MLA-EXP-005 | Corrélation | un `correlationId` relie snapshot, inférence, fusion, opportunité et outcome | Oui |
| MLA-EXP-006 | Accès audit | lecture d’une explication ou d’un audit respecte le scope client et est journalisée | Oui |

## 9. Checklist monitoring et drift

| ID | Contrôle | Critère de réussite | Blocage |
|---|---|---|---:|
| MLA-MON-001 | Service | latence, erreurs, débit, CPU, mémoire, chargement modèle et readiness sont mesurés | Oui |
| MLA-MON-002 | Data quality | fraîcheur, nulls, couverture, bornes et catégories inconnues ont seuils/version/réaction | Oui |
| MLA-MON-003 | Drift features | référence, méthode, seuils `WARNING/BLOCKING` et segments sont versionnés | Oui |
| MLA-MON-004 | Drift score | distribution et taux par bande sont suivis sans label `customerId` | Oui |
| MLA-MON-005 | Performance différée | outcomes observés par cible et horizon sont mesurés lorsque matures | Oui |
| MLA-MON-006 | Réaction | drift bloquant empêche activation et déclenche fallback/revue, jamais auto-retrain | Oui |
| MLA-MON-007 | Alertes | une alerte injectée est visible, corrélée et clôturable avec motif | Non pour G1, oui pour G2 |

## 10. Checklist outcomes, consentement et gouvernance

| ID | Contrôle | Critère de réussite | Blocage |
|---|---|---|---:|
| MLA-GOV-001 | Finalité | dataset limité à `COMMERCIAL_OPPORTUNITY_PROPENSITY` et approuvé | Oui |
| MLA-GOV-002 | Consentement/base | chaque population est couverte par consentement ou base de traitement approuvée, versionnée et vérifiable | Oui |
| MLA-GOV-003 | Révocation/exclusion | opt-out, révocation ou exclusion sont propagés aux futurs exports selon politique | Oui |
| MLA-GOV-004 | Minimisation | identifiants directs et notes libres absents ; pseudonymisation vérifiée | Oui |
| MLA-GOV-005 | Origine outcome | `OBSERVED`, `SIMULATED`, `NOT_REPORTED` distingués ; seul `OBSERVED` est utilisé par défaut | Oui |
| MLA-GOV-006 | Label | outcome, horizon, fenêtre de maturité et traitement de l’absence sont définis | Oui |
| MLA-GOV-007 | Pas de faux négatif | absence d’outcome n’est pas automatiquement une non-conversion | Oui |
| MLA-GOV-008 | Manifeste | population, exclusions, période, versions, hashes, qualité et approbations sont persistés | Oui |
| MLA-GOV-009 | Rétention | purge et rétention du dataset et de ses dérivés sont testées | Oui |
| MLA-GOV-010 | Données réelles | aucune donnée réelle utilisée avant validations juridique, DPO, sécurité et data governance | Oui |

## 11. Checklist agence, CC et portefeuille

| ID | Contrôle | Critère de réussite | Blocage |
|---|---|---|---:|
| MLA-SCP-001 | Dashboard CC | le CC ne voit que son affectation active ; filtre forcé côté serveur | Oui |
| MLA-SCP-002 | Dashboard agence | le responsable ne voit que ses branches et peut drill-down vers leurs CC | Oui |
| MLA-SCP-003 | Action agence | lecture branche n’accorde pas l’écriture ; `actions:write:branch` testé séparément | Oui |
| MLA-SCP-004 | Accès horizontal | deviner `customerId`, `portfolioId`, `relationshipManagerId` ou `branchId` ne contourne pas le scope | Oui |
| MLA-SCP-005 | Admin minimal | rôle admin sans scope client ne voit pas le détail PME | Oui |
| MLA-SCP-006 | Réaffectation | droits changent à `validFrom/validTo` sans réécrire l’historique | Oui |
| MLA-SCP-007 | Totaux cohérents | agrégats, pages et exports appliquent exactement le même périmètre | Oui |
| MLA-SCP-008 | Projection stale | une projection périmée ne donne jamais un accès global et bloque les écritures | Oui |

## 12. Checklist performance CPU et exploitation

| ID | Contrôle | Critère de réussite | Blocage |
|---|---|---|---:|
| MLA-PERF-001 | Batch de référence | 500 PME scorées sans erreur, OOM, GPU ni appel réseau externe | Oui |
| MLA-PERF-002 | Budget | p95 et throughput respectent le budget approuvé et consigné avec CPU/RAM | Oui |
| MLA-PERF-003 | Démarrage | chargement et self-test du champion respectent le délai de readiness | Oui |
| MLA-PERF-004 | Concurrence | deux lots idempotents ne créent ni double score ni double opportunité | Oui |
| MLA-PERF-005 | Endurance | exécution répétée sans croissance anormale de mémoire, connexions ou files | Oui pour G2 |
| MLA-PERF-006 | Compose | démarrage, health, ready, arrêt et recréation fonctionnent dans le profil prévu | Oui |

Les budgets chiffrés doivent être décidés après mesure sur l’environnement BOA cible. Ils ne peuvent pas être validés par une machine plus puissante sans consigner l’écart.

## 13. Scénarios bout en bout obligatoires

| ID | Scénario | Résultat attendu |
|---|---|---|
| MLA-E2E-001 | même lot en `RULES_ONLY` puis `ML_SHADOW` | mêmes opportunités visibles ; scores shadow auditables |
| MLA-E2E-002 | modèle indisponible | fallback règles, cause visible et aucun score inventé |
| MLA-E2E-003 | feature obligatoire stale | score invalide, exclusion de fusion, audit qualité |
| MLA-E2E-004 | champion remplacé puis rollback | nouvelles décisions portent nouvelle version ; anciennes intactes ; rollback réussi |
| MLA-E2E-005 | CC ouvre une explication | règles, score, fusion et versions visibles pour son client uniquement |
| MLA-E2E-006 | responsable ouvre dashboard agence | agrégats limités à sa branche ; pas d’action sans scope dédié |
| MLA-E2E-007 | outcome mature | rattachement à la prédiction correcte sans fuite temporelle dans un dataset futur |
| MLA-E2E-008 | `FINANCIAL_STRESS_SIGNAL` | signal relationnel seulement ; aucun score de crédit, défaut ou décision |
| MLA-E2E-009 | recherche de dépendances interdites | zéro LLM, zéro GPU obligatoire, zéro accès SQL interschéma |

## 14. Critères de sortie par mode

### 14.1 Acceptation `ML_SHADOW`

Tous les contrôles bloquants des sections 3 à 11 sont `PASS`. Les tests E2E-001 à E2E-009 sont verts. Le modèle et le feature set sont approuvés. Le monitoring et le fallback sont opérationnels. Le dashboard opérationnel reste piloté par les règles.

### 14.2 Acceptation `HYBRID_RERANK`

En plus de l’acceptation shadow, la période d’observation convenue est terminée. Les métriques du challenger, la stabilité, la calibration éventuelle, les écarts par segment, le volume de données et les limites sont revus. La formule de fusion et ses seuils sont simulés puis approuvés. Un test prouve qu’aucun client non éligible par règles n’entre dans le classement. Le rollback `RULES_ONLY` est testé.

### 14.3 Refus obligatoire

L’activation est refusée si un score peut être interprété ou consommé comme crédit, si l’autorisation portefeuille est contournable, si le dataset n’a pas de gouvernance vérifiable, si l’explication ou l’audit manque, si une feature fuit un outcome futur, si le runtime nécessite un LLM/GPU/cloud, ou si un échec est masqué par une valeur de score par défaut.

## 15. Limites reconnues du MVP

Le MVP exécute un modèle logistique déterministe en batch CPU et persiste une propension commerciale avec ses versions. Il reste un POC sur données synthétiques. Il ne couvre pas la calibration de production, le monitoring de drift opérationnel, le temps réel, l’apprentissage en ligne, l’auto-réentraînement, l’auto-promotion, l’inférence causale, les modèles de crédit, les notes libres, le LLM ou `HYBRID_CANDIDATE`.

## Références

[1]: ./ml-engine.md "ML Engine CPU-ready — architecture cible et contrats"
[2]: ./portfolio-scoping.md "Périmètres agence, chargé de clientèle et portefeuille"
[3]: ./test-plan.md "Plan de tests — BOA SME Opportunity Intelligence"
[4]: ./business-rules.md "Moteur déterministe d’intelligence d’opportunités"
[5]: ../architecture/architecture.md "Architecture exécutable"
[6]: ./lots/LOT-14-STUDIO-ML-APERÇU.md "Lot 14 — aperçu gouverné du Studio ML"
