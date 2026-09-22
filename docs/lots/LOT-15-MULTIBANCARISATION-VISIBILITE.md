# Lot 15 — Multibancarisation et visibilité des flux

**Date :** 22 septembre 2026

## 1. Verdict

Le lot introduit une **visibilité explicable des flux domiciliés chez BANK OF AFRICA** sans accès à des comptes d’autres banques. Il ajoute les niveaux `HIGH`, `PARTIAL`, `LOW` et `UNKNOWN`, une déclaration autorisée de relation bancaire, la règle gouvernée `FLOW_DOMICILIATION`, la requalification prudente `ABSENT_OR_ELSEWHERE`, ainsi que les vues CC et agence associées.

| Périmètre | Statut | Preuve |
|---|---|---|
| Modèle, migration 0020 et rollback | **PROUVÉ — PASS** | [`RESULTATS-MIGRATION-VISIBILITE.json`](../evidence/visibility/RESULTATS-MIGRATION-VISIBILITE.json) |
| Analytics et calcul de visibilité | **PROUVÉ — PASS synthétique** | [`RESULTATS-VISIBILITE.json`](../evidence/visibility/RESULTATS-VISIBILITE.json) |
| Rule Studio `FLOW_DOMICILIATION_001` | **PROUVÉ — PASS** | cycle `DRAFT → VALIDATED → SIMULATED → SUBMITTED → APPROVED → PUBLISHED → ACTIVE` |
| Opportunity, Product Gaps et dashboards | **PROUVÉ — PASS synthétique** | 500 PME, règles `1`, ML `0`, `RULES_ONLY` |
| Isolation CC/agence | **PROUVÉ — PASS** | refus `403 CUSTOMER_OUTSIDE_PORTFOLIO` et E2E Ahmed/Salma |
| Interface React et captures | **PROUVÉ — PASS** | trois captures 1440 × 900 et rapport Playwright |
| Données BOA réelles ou externes | **NON IMPLÉMENTÉ** | aucune source CBS/CRM/paiements réelle ni compte tiers |
| Validation commerciale BOA | **À VALIDER** | seuils, pénalités, cooldown, wording et produits |
| Production bancaire | **BLOCKED** | mêmes bloqueurs sécurité, DPO, SI, HA, sauvegarde et images que la clôture pilote |

> **Important.** Le lot ne prend aucune décision de crédit. Il ne produit ni score de défaut, ni montant, ni prix, ni acceptation ou refus. Le ML reste `POC_SHADOW`, CPU-only, sans influence opérationnelle ; aucun LLM ni GPU n’est utilisé.

## 2. Données et modèle

La migration [`0020_multibank_visibility.py`](../../database/migrations/versions/0020_multibank_visibility.py) ajoute les attributs de relation bancaire sur `customer.customers`, les snapshots `analytics.flow_visibility_snapshots`, la règle et les signaux associés, ainsi que les contraintes et index nécessaires. La migration initiale metadata-driven exclut explicitement les objets 0020 afin que la création sur base vierge soit réelle.

La matrice PostgreSQL couvre :

| Cycle | Résultat |
|---|---|
| graphe Alembic à tête unique | **PASS** — `0020_multibank_visibility` |
| base vierge → 0020 | **PASS** |
| base existante 0019 → 0020 | **PASS** |
| 0020 → 0019 | **PASS** |
| 0019 → 0020 | **PASS** |
| conservation des sentinelles utilisateur | **PASS** |
| refus du downgrade si une donnée métier 0020 serait perdue | **PASS** |
| grants explicites, refus d’accès excessifs et revokes au downgrade | **PASS** |

Le rôle PostgreSQL partagé par Rule Management et Rule Simulation reçoit `SELECT` sur les snapshots de visibilité et les actions, puis `SELECT/UPDATE` sur les politiques pour l’activation gouvernée ; il ne reçoit ni écriture Action, ni insertion ou suppression de politique. Le downgrade est **fail-closed** sur les tables 0020 et sur les valeurs portées par les colonnes ajoutées aux tables historiques.

## 3. Calcul de visibilité

L’ordre de résolution est déterministe :

1. `DECLARED` lorsqu’une relation bancaire est déclarée par un acteur autorisé ;
2. `TURNOVER_RATIO` lorsque les encaissements BOA sur douze mois et le chiffre d’affaires déclaré sont exploitables ;
3. `TRANSACTION_FINGERPRINTS` lorsque des indices structurés sont suffisants ;
4. `UNKNOWN` dans les autres cas.

Pour une date de coupe, la relation bancaire et le chiffre d’affaires sont résolus indépendamment dans l’historique append-only. Une déclaration de relation récente sans chiffre d’affaires exploitable ne masque donc pas un chiffre d’affaires antérieur encore valide. Les transactions dont le statut n’est pas `BOOKED` sont exclues de la somme, de la couverture et des empreintes.

La preuve synthétique sur 500 PME produit :

| Niveau | Nombre |
|---|---:|
| `HIGH` | 0 |
| `PARTIAL` | 50 |
| `LOW` | 50 |
| `UNKNOWN` | 400 |

Les trois méthodes actives sont exercées : 33 `DECLARED`, 34 `TURNOVER_RATIO`, 33 `TRANSACTION_FINGERPRINTS` et 400 `NONE`. Les scénarios synthétiques comprennent 50 `MULTIBANK_PRIMARY` et 50 `MULTIBANK_SECONDARY`. L’absence de niveau `HIGH` dans ce jeu n’est ni un constat clientèle ni une cible métier : elle résulte uniquement des scénarios synthétiques de ce run.

Ces distributions sont des **données de démonstration générées**, pas des estimations de la clientèle BOA.

## 4. Règles et opportunités

### 4.1 Règle gouvernée

`FLOW_DOMICILIATION_001` est seedée en `DRAFT` et la règle technique homonyme reste inactive. Le protocole :

- valide puis simule la règle sur 500 PME synthétiques côté serveur ;
- refuse l’auto-approbation de l’analyste ;
- soumet avec `business.analyst.demo` ;
- approuve et publie avec `rule.approver.demo` ;
- vérifie l’audit ordonné `CREATED`, `VALIDATED`, `SIMULATED`, `SUBMITTED`, `APPROVED`, `PUBLISHED`, `ACTIVATED`.

Une édition justifiée des seuils crée d’abord une politique de visibilité inactive. La publication Rule Studio `FLOW_DOMICILIATION` bascule ensuite atomiquement la dernière version en attente et désactive l’ancienne ; aucun brouillon de seuil n’affecte Analytics ou Opportunity avant cette étape.

La simulation a analysé 500 PME et trouvé 100 correspondances. Les textes français et les produits précis sont transportés depuis la version Rule Studio publiée jusqu’à Opportunity.

### 4.2 Ajustements déterministes

Pour une visibilité `PARTIAL` ou `LOW`, `FLOW_DOMICILIATION` est une recommandation `WIN_BACK`. Une visibilité `LOW` retire `CASH_INVESTMENT`; une visibilité `PARTIAL` applique une pénalité de confiance et de priorité ; les règles sensibles sont désactivées si la visibilité ne permet pas une interprétation prudente. Product Service renvoie `ABSENT_OR_ELSEWHERE` au lieu d’affirmer une absence totale.

La preuve finale observe 100 opportunités `FLOW_DOMICILIATION`, toutes les 100 en recommandation `WIN_BACK`, ainsi que 194 recommandations `WIN_BACK` au total sur les types d’opportunités concernés. Elle mesure zéro violation de l’invariant `fallback_mode=RULES_ONLY`, `rules_weight=1`, `ml_weight=0`.

## 5. Habilitations et interface

Le backend réapplique le scope client sur la déclaration de relation bancaire, la lecture du client et les lacunes produit. Ahmed Mansouri (`rm-01`) peut consulter et déclarer uniquement ses PME ; une tentative sur `SME-00009`, hors portefeuille, retourne `403 CUSTOMER_OUTSIDE_PORTFOLIO`. Salma Berrada voit la consolidation de l’agence `BR-01`, sans élargissement arbitraire par paramètre d’URL.

Les vues React ajoutent :

- un badge et un panneau « Visibilité des flux » dans la fiche PME ;
- la méthode, la part estimée, la date, les faits structurés et l’audit déclaratif ;
- le filtre de visibilité dans la liste CC déjà bornée par le backend ;
- la répartition `HIGH/PARTIAL/LOW/UNKNOWN` et `FLOW_DOMICILIATION` dans le dashboard agence ;
- le badge « Reconquête » et les produits de domiciliation dans l’opportunité.

Les trois preuves visuelles sont [`VISIBILITE-FLUX-AHMED-1440x900.png`](../evidence/visibility/VISIBILITE-FLUX-AHMED-1440x900.png), [`OPPORTUNITE-DOMICILIATION-AHMED-1440x900.png`](../evidence/visibility/OPPORTUNITE-DOMICILIATION-AHMED-1440x900.png) et [`DASHBOARD-AGENCE-VISIBILITE-1440x900.png`](../evidence/visibility/DASHBOARD-AGENCE-VISIBILITE-1440x900.png).

## 6. Portes exécutées

| Porte | Résultat mesuré |
|---|---|
| Ruff format/check | **PASS** |
| mypy backend | **PASS** |
| pytest unitaire | **PASS — 283 tests** |
| TypeScript | **PASS** |
| Vitest | **PASS — 35 tests** |
| build Vite | **PASS** |
| Bash + ShellCheck | **PASS** |
| migration 0020 isolée | **PASS** |
| stack Compose isolée, pipeline 500 PME et oracles | **PASS** |
| Playwright complet | **PASS — 24/24, 0 échec, 0 ignoré, 0 flaky, 107,7 s** |

Les scripts reproductibles sont [`validate-visibility-migration.sh`](../../scripts/validate-visibility-migration.sh) et [`validate-visibility.sh`](../../scripts/validate-visibility.sh). Un script n’est pas considéré comme une preuve sans son JSON de run ; les preuves versionnées se trouvent sous [`docs/evidence/visibility/`](../evidence/visibility/).

Le run fonctionnel `visibility-20260922T004151Z` et le run migration `visibility-migration-20260922T003912Z` sont rattachés au commit fonctionnel `78429027c960dfe91a1d41adac3bcdf3df7807c9`. La stack a été créée sur un volume nommé vierge ; le runner sandbox ayant atteint sa fenêtre d’exécution pendant le cinquième lot, la reprise a été effectuée à la coupe mesurée Analytics `SME-00125`, Signals `SME-00100`, Opportunity `SME-00100`, puis achevée jusqu’à `SME-00500`. Après la revue indépendante, le filtre a été resserré à `BOOKED` exclusivement et les vingt lots de 25 PME ont été **recalculés intégralement** sur le commit final. L’interruption n’est pas comptée comme un PASS ; la preuve JSON expose la reprise historique, le recalcul complet post-correctif et le run Playwright rejoué sur la révision exacte.

Le Playwright attesté utilise le mode `DEV_PERSONA`, avec périmètres et rôles transmis au backend ; il ne couvre pas le login navigateur Keycloak. Cette limite est explicite dans le JSON et interdit d’interpréter le run comme une homologation IAM de production.

## 7. Hypothèses et limites

Les seuils `HIGH >= 0,70`, `LOW < 0,30`, les pénalités `-10/-25/-5`, le minimum de deux empreintes sur 90 jours et le cooldown de 180 jours sont **HYPOTHÈSE À VALIDER AVEC BOA**. Les textes de recommandation, les quatre produits Cash Management et les volumes synthétiques doivent également être validés par les métiers BOA.

La validation ne démontre aucune donnée BOA réelle, aucun accès à une banque tierce, aucun gain commercial, aucune capacité de production, aucune homologation sécurité et aucune conformité réglementaire. Le signal décrit seulement la visibilité observée chez BOA et l’incertitude associée.

## 8. Conclusion

Le lot est **GO pour une démonstration synthétique gouvernée** sur la révision fonctionnelle figée `7842902`, avec preuves JSON et visuelles contrôlées. Il reste **NO-GO pour la production bancaire**, pour une affirmation sur la multibancarisation réelle d’un client, pour une influence ML et pour toute décision de crédit.
