# ML Engine CPU-ready — architecture cible et contrats de gouvernance

**Produit :** BOA SME Opportunity Intelligence  
**Statut :** architecture implémentée en `POC_SHADOW` sur données locales/synthétiques ; priorité opérationnelle `RULES_ONLY` ; aucune performance de production revendiquée
**Auteur :** Manus AI  
**Périmètre :** propension commerciale, fusion avec les règles, explicabilité, audit et gouvernance

> Le ML Engine estime une **propension commerciale** afin d’ordonner ou d’enrichir des opportunités destinées à un chargé de clientèle. Il ne produit ni score de crédit, ni risque de défaut, ni décision d’octroi, de refus, de limite, de prix ou de montant. `FINANCIAL_STRESS_SIGNAL` reste un signal relationnel à examiner.

## 1. Décision d’architecture

L’évolution conserve le pipeline existant et ajoute des frontières remplaçables :

```text
Analytics + Rule Engine
  → Feature Store / Signals
  → ML Engine CPU-ready
  → Propensity Score
  → Opportunity Engine
  → dashboard agence / dashboard CC
  → portefeuille
  → client PME
```

Cette chaîne n’est pas une fusion de responsabilités. **Analytics** reste propriétaire des métriques. **Signal Service** et **Rule Engine** restent propriétaires des signaux et évaluations déterministes. Le **Feature Store** matérialise des snapshots point-in-time à partir de ces sorties. Le **ML Engine** produit un score contractuel observé en shadow. **Opportunity Service** applique les garde-fous, la déduplication, l’explication et la recommandation issue des règles ; le score ML est conservé pour l’audit et l’évaluation mais ne modifie pas la priorité.

Le runtime local sert un modèle logistique déterministe `sales-propensity-logit-poc-v1` sur CPU. Il consomme le Feature Set `sales-features-v2`, qui intègre les sorties Analytics, Signal Service et Rule Studio. Chaque score porte `POC_SHADOW`, `RANKING_ONLY`, `NOT_VALIDATED`, le modèle, le feature set, le dataset déclaré, le snapshot et son checksum. Opportunity Service conserve l’observation mais persiste une priorité `RULES_ONLY` avec poids règles `1` et ML `0`. Ce mode démontre l’intégration technique ; il ne constitue pas une activation de production et ne satisfait pas les portes G2/G3 de [`ml-acceptance.md`](./ml-acceptance.md).

## 2. Invariants non négociables

1. Le score est une propension à un **outcome commercial défini**, sur un horizon défini et pour un type d’opportunité défini.
2. Le mot « propension » ne doit jamais être remplacé par « risque », « solvabilité », « défaut », « crédit » ou une formulation équivalente.
3. Le modèle ne lit ni transactions brutes, ni texte libre, ni tables d’un autre service. Il reçoit un `FeatureSnapshot` versionné.
4. Une prédiction sans versions de modèle, features, snapshot, dataset déclaré, contrat de score et audit est invalide.
5. Un modèle ne s’auto-promeut pas, ne s’auto-réentraîne pas et ne modifie pas une règle.
6. L’indisponibilité du ML ne bloque pas le chemin déterministe. La politique configurée revient à `RULES_ONLY` ou suspend le lot ; elle ne fabrique jamais un score.
7. Le runtime est **CPU-only**. Une image, un artefact ou une configuration qui exige CUDA, un GPU ou un service cloud d’inférence est hors périmètre.
8. Aucun appel, SDK, modèle, secret, endpoint ou dépendance LLM n’est présent. Seul un port d’extension inactif est documenté.
9. Le modèle n’effectue aucune décision de crédit. Les features dont la finalité est exclusivement crédit ou défaut sont interdites dans le registre de ce produit.
10. La décision finale de contact et la qualification du besoin appartiennent au CC.

## 3. Composants et responsabilités

| Composant | Responsabilité cible | Possède | Ne doit pas faire |
|---|---|---|---|
| Analytics Service | Calcul des métriques, fenêtres, baselines et qualité | définitions et snapshots analytiques | entraîner ou servir un modèle |
| Signal Service / Rule Engine | Signaux et évaluations déterministes versionnés | signaux, règles actives, traces | transformer une propension en décision finale |
| Feature Store | Matérialisation point-in-time, fraîcheur et export gouverné | `FeatureSnapshot`, valeurs et watermarks | recalculer une transaction brute pendant l’inférence |
| Feature Registry | Contrat sémantique et usage autorisé de chaque feature | définitions, versions, statut et lineage | accepter une feature sans propriétaire ni finalité |
| ML Engine | Validation du contrat, chargement CPU et inférence | exécutions et prédictions techniques | persister l’opportunité ou appliquer les permissions utilisateur |
| Model Registry | Cycle de vie, artefacts, approbations et métriques | métadonnées et checksums des modèles | promotion automatique selon une seule métrique |
| Opportunity Service | Garde-fous, priorité `RULES_ONLY`, explication et audit du score shadow séparé | opportunités et décisions de priorité | appliquer un poids ML avant franchissement des gates ou interpréter le score comme risque |
| Customer Service | Agence, CC, portefeuille et affectations temporelles | périmètre organisationnel | déléguer l’autorisation au seul frontend |
| Action Service | Actions et outcomes commerciaux | feedback observé | réécrire la prédiction historique |

Pour rester cohérent avec l’existant, les composants cibles sont des services **Python 3.12/FastAPI**, protégés par Keycloak et déployables dans Docker Compose. PostgreSQL reste le stockage de métadonnées et de snapshots du premier incrément. Un produit spécialisé de feature store ou de model registry n’est pas requis avant qu’un besoin mesuré le justifie.

## 4. Contrat du score de propension

### 4.1 Sémantique

Le score répond à la question :

> « Parmi les clients éligibles à l’analyse commerciale pour le type `opportunityType`, quelle est la propension relative à observer l’`targetOutcome` pendant `horizon`, compte tenu du snapshot de features et du modèle indiqués ? »

Le score est borné entre `0` et `1`. Il peut être calibré comme estimation d’un outcome seulement si la méthode et la population de calibration sont approuvées. Sans calibration approuvée, `scoreInterpretation` vaut `RANKING_ONLY`. Aucun seuil universel n’est déduit de la valeur.

### 4.2 Représentation canonique

```json
{
  "scoreId": "psc_01J...",
  "customerId": "SME-00125",
  "opportunityType": "TRADE_FINANCE",
  "targetOutcome": "MEETING_SCHEDULED_WITHIN_90D",
  "horizon": "90D",
  "propensityScore": 0.78,
  "scoreInterpretation": "RANKING_ONLY",
  "scoreBand": "HIGH",
  "modelId": "trade-propensity",
  "modelVersion": "1.2.0",
  "modelStage": "CHALLENGER",
  "featureSetId": "sme-commercial-v1",
  "featureSetVersion": "1.4.0",
  "featureSnapshotId": "fs_01J...",
  "featureWatermark": "2026-09-17T23:59:59Z",
  "generatedAt": "2026-09-18T08:00:00Z",
  "validUntil": "2026-09-25T08:00:00Z",
  "qualityStatus": "VALID",
  "explanation": {
    "method": "MODEL_NATIVE_CONTRIBUTIONS",
    "baseline": 0.42,
    "topContributors": [
      {"featureCode": "INTERNATIONAL_FLOW_GROWTH_90D", "direction": "INCREASES_PROPENSITY", "contribution": 0.18},
      {"featureCode": "INTERNATIONAL_TRANSACTION_COUNT_30D", "direction": "INCREASES_PROPENSITY", "contribution": 0.11}
    ],
    "missingFeatures": []
  },
  "contractVersion": "1.0",
  "correlationId": "corr_01J..."
}
```

Les champs `customerId`, `opportunityType`, `targetOutcome`, `horizon`, `propensityScore`, `scoreInterpretation`, `modelId`, `modelVersion`, `featureSetVersion`, `featureSnapshotId`, `generatedAt`, `qualityStatus`, `contractVersion` et `correlationId` sont obligatoires. `scoreBand` est issu de seuils versionnés avec le modèle ; il ne change pas la sémantique du score.

Une réponse porte `qualityStatus = INVALID` et aucun `propensityScore` exploitable lorsqu’une feature obligatoire manque, que le snapshot est trop ancien, que le modèle et le feature set sont incompatibles, ou que le checksum de l’artefact échoue. Une valeur par défaut, `0`, `0.5` ou la dernière valeur connue ne doit pas masquer ce cas.

## 5. Feature Registry et Feature Store

### 5.1 Contrat d’une feature

Chaque version de feature possède les métadonnées suivantes :

| Champ | Règle |
|---|---|
| `featureCode`, `version` | identifiant stable et version sémantique immuable |
| `description`, `businessMeaning` | définition compréhensible sans lire le code |
| `ownerService`, `sourceContract` | propriétaire et API/événement source |
| `entityType`, `entityKey` | `CUSTOMER` et `customerId` pour le premier incrément |
| `dataType`, `unit`, `allowedValues` | type et domaine contrôlés |
| `window`, `asOfPolicy`, `freshnessSla` | point de coupure, fenêtre et âge maximal |
| `transformationVersion` | version de calcul reproductible |
| `qualityRules` | nullabilité, bornes, couverture et statut minimum |
| `allowedPurpose` | uniquement `COMMERCIAL_OPPORTUNITY_PROPENSITY` |
| `prohibitedUses` | au minimum crédit, défaut, octroi, tarification et limite |
| `sensitivityClass` | classification et règle de minimisation |
| `leakagePolicy` | date à partir de laquelle la valeur est observable et exclusions post-outcome |
| `explainabilityLabel` | libellé utilisable dans l’explication |
| `status` | `DRAFT`, `APPROVED`, `ACTIVE`, `DEPRECATED`, `RETIRED` |
| `createdBy`, `approvedBy`, `checksum` | gouvernance et intégrité |

Une feature active est immuable. Une modification de source, fenêtre, transformation, unité, imputation ou qualité crée une nouvelle version. Une feature supprimée du set reste résoluble pour reconstruire les prédictions historiques.

### 5.2 Snapshots point-in-time

Un `FeatureSnapshot` est identifié par `(customerId, asOf, featureSetVersion, sourceWatermark)`. Toutes ses valeurs doivent avoir été observables à `asOf`. Les actions et outcomes postérieurs sont exclus. La construction stocke le lineage vers les snapshots Analytics, les signaux, la version de règles éventuellement consommée et les statuts de qualité.

Le premier stockage est **batch dans PostgreSQL**. Il fournit :

- une vue de service pour l’inférence, limitée aux features approuvées ;
- un export offline gouverné pour l’expérimentation et l’entraînement futur ;
- la même sémantique de transformation entre offline et inference ;
- une rétention et une purge par politique ;
- un checksum du vecteur normalisé.

Le MVP ML n’inclut ni streaming de features, ni cache temps réel, ni jointure à la volée sur les transactions brutes.

## 6. Model Registry et exécution CPU

### 6.1 Enregistrement d’un modèle

Le registre conserve au minimum : `modelId`, `modelVersion`, `opportunityType`, `targetOutcome`, `horizon`, `algorithmFamily`, `artifactUri`, `artifactChecksum`, `runtimeContract`, `featureSetVersion`, `trainingDatasetId`, `trainingCutoff`, `codeRevision`, `hyperparameters`, métriques d’entraînement/validation/test, métriques par segment autorisé, méthode de calibration, limites connues, approbations, date d’effet et statut.

Les statuts sont :

```text
DRAFT → VALIDATED → CHALLENGER → CHAMPION → RETIRED
```

`REJECTED` peut terminer une revue. Une promotion exige un sujet différent de l’auteur, les critères de [`ml-acceptance.md`](./ml-acceptance.md), un checksum valide et un plan de rollback. Il n’existe qu’un `CHAMPION` actif par `(opportunityType, targetOutcome, horizon, populationPolicy)`.

### 6.2 CPU-ready

Le contrat d’artefact doit fonctionner sur Linux `amd64`, sans GPU, avec un nombre de threads borné et des limites de mémoire documentées. Le serveur FastAPI charge l’artefact en lecture seule au démarrage ou lors d’un rechargement gouverné. La readiness reste fausse si l’artefact actif, son checksum, son contrat d’entrée ou son self-test échoue.

La technologie de sérialisation n’est pas figée par ce document. Elle doit toutefois être locale, déterministe, scannée, compatible avec le runtime Python approuvé et dépourvue d’exécution arbitraire non maîtrisée. Le registre refuse un artefact qui embarque une dépendance réseau ou LLM.

## 7. Fusion configurable entre ML et règles

La politique de fusion appartient à Opportunity Service et possède `fusionPolicyId`, `version`, `status`, `effectiveFrom`, `opportunityType`, `mode`, `weights`, `gates`, `fallback`, `createdBy`, `approvedBy` et `checksum`.

| Mode | Effet sur la production | Usage autorisé |
|---|---|---|
| `RULES_ONLY` | le ML n’est pas appelé | mode actuel et fallback sûr |
| `ML_SHADOW` | score calculé et monitoré, jamais visible dans le classement opérationnel | premier incrément ML |
| `HYBRID_RERANK` | seules les opportunités éligibles par règle sont réordonnées selon une formule versionnée | après acceptation complète |
| `HYBRID_CANDIDATE` | une propension peut créer une candidate `TO_REVIEW`, après tous les garde-fous déterministes | hors MVP initial, approbation spécifique |

Dans `HYBRID_RERANK`, un exemple de formule est :

```text
commercialRank = 100 × (ruleWeight × ruleConfidence + mlWeight × propensityScore)
```

avec `ruleWeight + mlWeight = 1`. Les poids et seuils sont décimaux versionnés. `priorityScore` reste une sortie d’Opportunity Service et peut aussi intégrer récence, urgence et gap produit selon la configuration existante. L’explication conserve séparément `ruleConfidence`, `propensityScore`, `fusionPolicyVersion` et le calcul final ; elle ne présente jamais le score fusionné comme une probabilité.

Les garde-fous s’exécutent avant et après la fusion : périmètre client, qualité, fraîcheur, produit actif, règles d’exclusion, déduplication, consentement/usage autorisé, type de modèle et vocabulaire non crédit. Si le modèle est indisponible, stale ou en drift bloquant, `fallback = RULES_ONLY` s’applique lorsque configuré. Le fallback et sa cause sont audités.

## 8. Explicabilité et audit

Chaque prédiction exploitable expose une explication stable produite au moment de l’inférence. Elle contient la baseline du modèle, les principaux contributeurs positifs et négatifs, les features absentes ou imputées, les avertissements de qualité et la méthode d’explication. Une contribution décrit une association avec la sortie du modèle, pas une cause du comportement du client.

La décision de fusion conserve :

- l’identifiant et la version de la règle, du modèle, du feature set et de la politique de fusion ;
- le snapshot et son watermark ;
- le score brut, son interprétation et sa bande ;
- la sortie déterministe et ses preuves ;
- chaque garde-fou évalué ;
- le résultat de fusion et le fallback éventuel ;
- l’acteur technique, le `correlationId`, les checksums et les timestamps ;
- la version finale de l’opportunité présentée au CC.

Les audits sont append-only. Une nouvelle version ne réécrit ni score ni explication historiques. Les accès aux prédictions, explications et modèles sont eux-mêmes auditables.

## 9. Monitoring, qualité et drift

Le monitoring distingue quatre familles :

| Famille | Mesures minimales | Réaction |
|---|---|---|
| Service | latence, erreurs, saturation CPU/mémoire, débit, readiness | alerte et fallback selon SLO |
| Données | fraîcheur, couverture, nulls, bornes, catégories inconnues | invalidation du snapshot si règle dure |
| Distribution | distribution de chaque feature et du score par période et segment autorisé | statut `OK`, `WARNING` ou `BLOCKING` selon seuils versionnés |
| Performance différée | contact, rendez-vous, offre, conversion, non pertinent, calibration lorsque possible | revue humaine ; aucune promotion automatique |

Les métriques de drift peuvent inclure PSI, distance de distribution ou taux de catégories inconnues, à condition que leur méthode et leur population de référence soient versionnées. Les seuils initiaux sont proposés puis validés sur données représentatives ; ils ne sont pas inventés dans le frontend.

Un drift `WARNING` ouvre une revue et peut maintenir le shadow. Un drift `BLOCKING` interdit une nouvelle activation et fait revenir le chemin opérationnel à `RULES_ONLY` selon la politique. Il ne déclenche jamais un réentraînement automatique. Les métriques Prometheus n’utilisent pas `customerId` comme label.

## 10. Outcomes et futur dataset d’apprentissage

Les outcomes observés restent possédés par Action Service. Un dataset d’apprentissage futur est une **vue gouvernée et versionnée**, pas une lecture libre des tables d’action. Sa construction exige :

1. une finalité approuvée `COMMERCIAL_OPPORTUNITY_PROPENSITY` ;
2. un enregistrement de consentement ou de base de traitement approuvée par la gouvernance BOA, avec version de politique et possibilité d’exclusion lorsque requise ;
3. la minimisation, la pseudonymisation et la séparation des identifiants directs ;
4. une définition exacte du label, de l’horizon et de la date d’observation ;
5. un cutoff point-in-time qui empêche toute fuite d’outcome dans les features ;
6. la distinction `OBSERVED`, `SIMULATED` et `NOT_REPORTED` ; seul `OBSERVED` est éligible par défaut ;
7. une rétention, une purge et une révocation propagées aux exports dérivés selon la politique ;
8. un manifeste avec population, exclusions, période, versions, hashes, qualité et approbations.

Les outcomes `CONTACTED`, `MEETING_SCHEDULED`, `OFFER_CREATED`, `CONVERTED`, `REJECTED` et `NOT_RELEVANT` ne sont pas interchangeables. Chaque modèle choisit un seul label principal ou une définition multi-label explicitement revue. L’absence d’outcome ne vaut pas outcome négatif. Les notes libres du CC sont exclues du premier dataset.

Le MVP actuel utilise des données synthétiques. Aucun entraînement sur données réelles ou outcomes réels n’est autorisé avant validation juridique, sécurité, gouvernance des données et consentement/base de traitement.

## 11. Port d’extension LLM, strictement inactif

Une future interface conceptuelle `OpportunityNarrativePort` pourra recevoir une **décision déjà persistée et expurgée** afin de produire un résumé non décisionnel. Cette interface ne fait pas partie du chemin de score, de fusion ou de création d’opportunité.

Pour l’état présent :

- aucune route LLM n’est exposée ;
- aucun package, SDK, modèle ou client LLM n’est ajouté ;
- aucune variable d’environnement, clé ou URL LLM n’existe ;
- aucun fallback LLM n’est autorisé ;
- les explications sont structurées et déterministes.

Toute activation future exige une décision d’architecture séparée et ne peut modifier le score, l’éligibilité, la priorité ou le signal relationnel.

## 12. Limites de l’incrément ML MVP

Le premier incrément est limité à un modèle logistique de démonstration alimenté par un dataset synthétique déclaré, servi en batch CPU et exécuté en `POC_SHADOW`. Il réutilise PostgreSQL pour les snapshots, manifests, évaluations descriptives et registres. Les outcomes locaux sont des **labels candidats uniquement** ; ils ne rendent pas le dataset training-ready. Il ne fournit ni entraînement BOA démontré, ni calibration validée, ni streaming, ni GPU, ni entraînement en ligne, ni auto-ML, ni auto-réentraînement, ni promotion automatique, ni causalité, ni optimisation de crédit, ni génération de texte.

`HYBRID_RERANK` n’est pas activable par l’implémentation courante. Le gate de promotion ne fait pas confiance aux seuls champs de la requête : il résout en base le manifest, tous ses snapshots de features et labels, ainsi qu’une évaluation du même modèle et du même hash. Il exige une source `BOA_HISTORICAL_OBSERVED`, des labels binaires matures non candidats, un manifest et une évaluation `VALIDATED` sans blocker, des critères d’acceptation, Brier/ECE bornés, une calibration validée et un checksum d’artefact. Les endpoints actuels ne produisent volontairement aucun statut `VALIDATED`; une future activation demanderait donc une évolution et une approbation séparées. `HYBRID_CANDIDATE` est hors MVP. Le système déterministe reste la seule source de priorité pendant toute la phase shadow.

## Références

[1]: ../architecture/architecture.md "Architecture exécutable — BOA SME Opportunity Intelligence"
[2]: ./business-rules.md "Moteur déterministe d’intelligence d’opportunités"
[3]: ./data-model.md "Modèle relationnel PostgreSQL et pipeline de données"
[4]: ./portfolio-scoping.md "Périmètres agence, chargé de clientèle et portefeuille"
[5]: ./ml-acceptance.md "Acceptation de l’incrément ML"
[6]: ./api.md "Contrats API-first"
