# Feuille de route — BOA SME Opportunity Intelligence

**Statut :** trajectoire cible ; elle ne vaut pas constat d’implémentation  
**Principe :** préserver le moteur déterministe, ajouter le ML par portes réversibles et ne jamais effectuer de décision/scoring de crédit

## 1. Chaîne cible

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

Le chemin actuel reste `RULES_ONLY`. Chaque phase produit un incrément utilisable ou observable et possède une porte de sortie. Une phase n’est pas déclarée terminée sur la seule base d’un document ou d’une capture.

## 2. Phases et portes de passage

| Phase | Objectif | Livrables cibles | Porte de passage |
|---:|---|---|---|
| 0 | Consolider l’existant | Python 3.12/FastAPI, SQLAlchemy/Alembic, PostgreSQL, Keycloak, HTTP/outbox, cinq règles, explication et audit | MVP déterministe conforme ; zéro ML requis |
| 1 | Formaliser agence, CC et portefeuille | entités `Branch`, `Portfolio`, affectations temporelles, scopes Keycloak et contrats dashboards | tests d’accès horizontal/vertical, réaffectation et agrégats cohérents |
| 2 | Construire le Feature Registry | définitions, versions, finalités, qualité, lineage et usages interdits | chaque feature approuvée, point-in-time et non crédit |
| 3 | Matérialiser le Feature Store batch | snapshots PostgreSQL, parity offline/serving, fraîcheur, idempotence et exports gouvernés | zéro leakage, lineage complet et invalidation testée |
| 4 | Établir la gouvernance des outcomes | définition de labels, maturité, consentement/base approuvée, pseudonymisation, manifeste et rétention | dataset accepté par gouvernance ; données réelles toujours interdites sans validations |
| 5 | Ajouter Model Registry et ML Engine | modèle challenger, artefact/checksum, runtime FastAPI CPU-only, explication et audit | porte G1 de `ml-acceptance.md` ; inférence hors ligne sans LLM/GPU/cloud |
| 6 | Exécuter en shadow | `ML_SHADOW`, monitoring qualité/drift, comparaison aux règles, fallback | aucun impact opérationnel ; stabilité et alertes validées |
| 7 | Activer un reranking contrôlé | politique `HYBRID_RERANK`, simulations d’impact, poids/seuils approuvés, rollback | outcomes matures, revue par segment et porte G3 acceptée |
| 8 | Livrer dashboards agence et CC enrichis | read models, drill-down agence → CC → portefeuille → PME, explications règle/ML séparées | E2E de périmètre, performance et audit verts |
| 9 | Durcir l’exploitation | SLO, capacité, sauvegarde, reprise, sécurité, rétention, scans et gestion d’incident | revue production BOA et tests d’endurance |

Les phases 1 et 2 peuvent être préparées en parallèle sur le plan documentaire, mais la construction des snapshots exige un registre approuvé. Un modèle ne passe jamais en shadow sans Feature Store et Model Registry. Un rerank n’est jamais activé sans période shadow.

## 3. Décisions par phase

### Phase 0 — moteur déterministe comme socle et fallback

Analytics, Rule Engine, Signal Service et Opportunity Service conservent leurs responsabilités. `confidence` reste une mesure de preuve des règles et `priorityScore` une priorité commerciale. `FINANCIAL_STRESS_SIGNAL` demeure un signal relationnel. Il ne devient jamais une cible de défaut ou une décision de crédit.

### Phases 1 à 3 — périmètre et données avant modèle

Customer Service devient la source de vérité des agences, CC, portefeuilles et affectations temporelles. Le Feature Registry refuse une feature sans propriétaire, point de coupure, finalité et interdictions d’usage. Le Feature Store commence en batch PostgreSQL afin de préserver la stack existante et la reproductibilité ; aucun produit spécialisé n’est imposé.

### Phase 4 — outcomes comme actif gouverné

Action Service conserve les outcomes. L’apprentissage futur utilise un export versionné, pseudonymisé et point-in-time. `OBSERVED`, `SIMULATED` et `NOT_REPORTED` sont distincts. L’absence d’outcome ne vaut pas outcome négatif. Aucun dataset réel n’est constitué avant validation juridique, sécurité, DPO et data governance.

### Phases 5 et 6 — CPU et shadow d’abord

Le ML Engine est Python/FastAPI, Linux amd64, CPU-only et sans accès Internet. Le premier modèle est `CHALLENGER`. En `ML_SHADOW`, son score et son explication sont persistés et monitorés, mais les opportunités visibles restent identiques à `RULES_ONLY`. Une erreur revient au moteur déterministe et est auditée.

### Phase 7 — fusion limitée au reranking

`HYBRID_RERANK` peut seulement ordonner des opportunités déjà éligibles par règles. La formule, les poids, seuils et garde-fous sont versionnés. `HYBRID_CANDIDATE`, où le ML créerait une candidate, reste hors MVP et nécessite une nouvelle décision d’architecture.

### Phases 8 et 9 — vues opérationnelles et exploitation

Le dashboard CC ne montre que le portefeuille actif du sujet. Le dashboard agence agrège les CC de la branche et autorise un drill-down contrôlé. Le responsable d’agence n’agit pas au nom du CC sans scope dédié. Le monitoring couvre latence, CPU/mémoire, qualité, distributions, drift et performance différée ; il n’entraîne ou ne promeut jamais automatiquement.

## 4. Évolutions explicitement différées

Sont différés : streaming de features, GPU, online learning, auto-ML, auto-réentraînement, auto-promotion, causalité, optimisation de crédit, notes libres, `HYBRID_CANDIDATE`, multi-agence matricielle et moteur ABAC externe. Un broker peut être ajouté derrière l’outbox si la charge le justifie.

Un futur `OpportunityNarrativePort` pourra résumer une décision déjà persistée et expurgée. **Aucun appel, package, modèle, secret ou dépendance LLM n’est autorisé dans les phases présentes.** Cette possibilité future ne doit pas apparaître dans le chemin de score, de fusion, d’éligibilité ou de priorité.

## 5. Indicateurs de progression

Les indicateurs de phase sont des preuves techniques et métier : couverture des features, taux de snapshots valides, parity offline/serving, latence CPU, drift, proportion de fallback, outcomes matures, stabilité par segment, respect du scope, reconstructibilité de l’audit et absence de dépendances interdites. Une amélioration d’une métrique de modèle ne compense jamais un échec de sécurité, gouvernance ou non-crédit.

## Références

[1]: ./implementation-blueprint.md "Blueprint d’implémentation exécutable"
[2]: ./ml-engine.md "ML Engine CPU-ready — architecture cible et contrats"
[3]: ./portfolio-scoping.md "Périmètres agence, chargé de clientèle et portefeuille"
[4]: ./ml-acceptance.md "Acceptation de l’incrément ML"
[5]: ./final-status.md "Statut final et gabarit de validation"
