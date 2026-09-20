# Note de positionnement — BOA SME Opportunity Intelligence

**Objet :** assister le chargé de clientèle PME dans la détection, la compréhension et le suivi d’opportunités commerciales.
**Statut de lecture :** cette note distingue **IMPLÉMENTÉ**, **PROUVÉ**, **NON IMPLÉMENTÉ** et **À VALIDER**. Les éléments de démonstration du dépôt utilisent des données synthétiques ; ils ne constituent pas des résultats BOA.

Tout élément métier, volume, seuil, KPI, coût, exigence de pilote ou autre résultat non démontré dans le dépôt est une **HYPOTHÈSE À VALIDER AVEC BOA**. Le statut **À VALIDER** renvoie à cette réserve explicite.

## Position en une phrase

BOA SME Opportunity Intelligence est un cockpit d’intelligence commerciale qui transforme des métriques bancaires observées en signaux et applique des règles métier versionnées pour classer les candidates éligibles. Une propension commerciale explicable est calculée et observée séparément en shadow, sans modifier ce classement. Le produit aide le chargé de clientèle à décider **qui contacter, pourquoi et pour quel besoin potentiel** ; il ne décide jamais d’un crédit, d’un octroi, d’un refus, d’une limite, d’un prix ou d’un montant.

Le dépôt établit un **POC technique gouverné**, exécutable sur CPU et fondé sur des données synthétiques. Le modèle ML classique reste en **POC/shadow**, faute de labels BOA réels et matures. **Aucun LLM ni GPU n’est requis** : le LLM est non implémenté par choix et l’inférence est locale, déterministe et CPU-only ([README](../../README.md), [rapport final](../finalization-status-2026-09-19.md)).

## 1. Le problème quotidien du chargé de clientèle PME

Le parcours décrit dans le dépôt part d’un besoin concret : le chargé de clientèle doit parcourir son portefeuille, repérer les PME à regarder aujourd’hui, comprendre le motif de cette sélection et engager une action traçable. L’interface est conçue pour présenter directement le portefeuille, les signaux, l’opportunité et la prochaine action, au lieu de faire rechercher ces éléments dans plusieurs écrans ([architecture UX](../ux-architecture.md)).

Le problème n’est donc pas l’absence d’une nouvelle décision automatisée. Il réside dans la fragmentation de l’évidence commerciale : activité, encaissements, paiements fournisseurs, flux internationaux, soldes, détention de produits, signaux et historique d’action doivent être rapprochés à une même date d’observation. Le dépôt prévoit des fenêtres `7D`, `30D`, `90D`, `180D` et `365D`, des comparaisons historiques et des contrôles de qualité. Ces fenêtres sont des choix du MVP ; leur pertinence métier, leur fraîcheur acceptable et tout niveau de service associé restent **HYPOTHÈSE À VALIDER AVEC BOA** ([règles métier](../business-rules.md)).

Le produit répond à ce besoin sans transformer une corrélation en vérité sur le client. Une variation détectée est une évidence à examiner, pas une cause établie. La décision de prise de contact et la qualification du besoin restent au chargé de clientèle.

## 2. Proposition produit

Le produit propose un cockpit « portefeuille PME » avec un dashboard chargé de clientèle, une fiche PME, une chaîne d’évidence, un panneau d’opportunité et une grille d’actions. Le code frontend est branché sur le Gateway et ne porte ni données métier codées en dur, ni règle, ni score simulé ([architecture exécutable](../../architecture/architecture.md), [dashboard et chaîne](../../frontend/src/features/customer/WhyChain.tsx)).

**IMPLÉMENTÉ et PROUVÉ :** le parcours couvre le dashboard limité au périmètre du chargé de clientèle, le drill-down vers la PME, les signaux et preuves, l’opportunité, la propension, puis l’enregistrement d’une action. Les tests E2E vérifient également le refus d’un accès hors portefeuille et la mise à jour du dashboard après action ([test E2E du parcours RM](../../tests/e2e/rm-opportunity.spec.ts)). Les actions sont envoyées par API, puis invalident les vues concernées ; aucun état local fictif ne simule leur succès ([panneau d’action](../../frontend/src/features/customer/ActionPanel.tsx)).

Les noms de produits, seuils, règles, périodes et dates de référence proviennent des services. Aucun produit commercial, montant, revenu ou gain ne doit être présenté comme observé si le dépôt ne le démontre pas. Toute cible de valeur, volumétrie BOA, économie de temps ou KPI d’adoption est **HYPOTHÈSE À VALIDER AVEC BOA**.

## 3. Chaîne de valeur : `Rules → Signals/Features → ML shadow + priorité Rules-only → Opportunity → Actions`

| Maillon | Ce que le produit fait | Statut et preuve | Limite explicite |
|---|---|---|---|
| `Rules` | Évalue des règles versionnées sur des métriques et signaux cohérents. Les règles du MVP couvrent `INVESTMENT_FINANCING`, `TRADE_FINANCE`, `CASH_INVESTMENT` et `FINANCIAL_STRESS_SIGNAL`. | **IMPLÉMENTÉ / PROUVÉ** dans `backend/src/boa_oi/opportunities/`, les tests d’opportunités et [business-rules.md](../business-rules.md). | Les seuils initiaux et leur traduction en politique BOA sont **HYPOTHÈSE À VALIDER AVEC BOA**. |
| `Signals/Features` | Produit des signaux atomiques avec valeur, seuil, période, qualité, sévérité et preuves. Le Feature Store matérialise des snapshots point-in-time avec versions, sources et checksum. | **IMPLÉMENTÉ / PROUVÉ** par le Feature Store, le Signal Service et les tests de lignée ([ml-engine.md](../ml-engine.md), [test ML](../../tests/unit/test_ml_engine.py)). | Les sources BOA, leurs contrats, la fraîcheur et les droits d’usage réels sont une **HYPOTHÈSE À VALIDER AVEC BOA** ; les adaptateurs actuels sont synthétiques ou mockés. |
| `ML shadow` | Calcule une propension commerciale avec un modèle logistique classique CPU-only, persiste lignée et contributions, sans modifier l’éligibilité ni la priorité. | **IMPLÉMENTÉ / PROUVÉ** techniquement sur données locales/synthétiques. `POC_SHADOW`, `RANKING_ONLY`, `NOT_VALIDATED`; promotion et policy hybride bloquées. | Historiques BOA matures, calibration, performance par segment, validation indépendante et valeur commerciale sont **NON IMPLÉMENTÉS**. |
| `Opportunity` | Applique les preuves déterministes, garde-fous, priorité, horizon, produits potentiels et explication ; le score shadow reste séparé. | **IMPLÉMENTÉ / PROUVÉ** : policy active règles `1`, ML `0`, contraintes SQL et tests E2E. | Tout reranking ML est hors mode actuel et **À VALIDER AVEC BOA** après franchissement des gates. |
| `Actions` | Permet `CONTACT_CUSTOMER`, `CREATE_FOLLOW_UP`, `SCHEDULE_MEETING`, conversion ou écart motivé, avec outcome séparé et audit. | **IMPLÉMENTÉ / PROUVÉ** par `ActionPanel.tsx`, les APIs et les tests E2E. | Aucun outcome synthétique ne doit être confondu avec un résultat BOA réel ; la maturité des labels utilisables pour l’apprentissage est une **HYPOTHÈSE À VALIDER AVEC BOA**. |

La chaîne ne doit pas être lue comme une autorité unique. `Analytics` possède les métriques ; `Signal Service` et `Rule Engine` les sorties déterministes ; `Feature Store` les snapshots ; `ML Engine` l’observation shadow ; `Opportunity Service` la priorité rules-only, les garde-fous et l’explication.

## 4. Explicabilité, périmètre et limites

L’explication est une sortie obligatoire. La chaîne affichée suit les signaux, la règle métier, la propension ML et l’opportunité. Elle expose des valeurs observées, seuils, périodes, versions, facteurs contributifs et références de lignée. Une contribution ML indique une association avec la sortie du modèle ; elle ne prouve pas une causalité du comportement de la PME. L’audit conserve les versions de règle, modèle, Feature Set, snapshot et politique de fusion ([WhyChain.tsx](../../frontend/src/features/customer/WhyChain.tsx), [modèle de données](../data-model.md)).

Le produit ne fait pas les choses suivantes :

- il ne prend **aucune décision de crédit** et ne calcule ni score de crédit, ni probabilité de défaut, ni décision d’acceptation ou de refus ; `FINANCIAL_STRESS_SIGNAL` reste un signal relationnel à examiner humainement ;
- il ne remplace pas le jugement du chargé de clientèle et ne transforme pas une propension en éligibilité bancaire ;
- il ne crée pas une opportunité à partir d’un score ML seul dans le périmètre initial ;
- il n’utilise ni LLM, ni GPU, ni appel IA externe ; une éventuelle extension narrative future serait hors du chemin de score et de décision ;
- il ne revendique aucune précision, AUC, calibration, uplift, conversion, revenu, gain de productivité ou autre performance commerciale de production ;
- il ne raccorde pas encore les systèmes CBS/CRM/Payments/Trade BOA réels, ne fournit pas de haute disponibilité de production et ne constitue pas une homologation DPO, sécurité ou architecture.

La readiness de production est explicitement `BLOCKED`. Les données BOA réelles, les labels, la validation indépendante, les adaptateurs SI, la gouvernance DPO/Sécurité, la haute disponibilité, la restauration, les secrets et le TLS de production restent à réaliser et à approuver ([rapport final](../finalization-status-2026-09-19.md), [gouvernance d’industrialisation](../industrialization-governance.md)).

## 5. Proposition de pilote contrôlé

La proposition est de commencer par un pilote **assistif et réversible**, sans impact sur une décision de crédit et sans modifier la responsabilité du chargé de clientèle. Le périmètre de population, la durée, les agences, les portefeuilles, les critères d’inclusion, la fréquence de calcul et les KPI de sortie sont **HYPOTHÈSE À VALIDER AVEC BOA** ; le dépôt ne fournit pas de mesure BOA permettant de les fixer.

Le pilote peut suivre quatre portes documentées :

1. **Préparation gouvernée — À VALIDER :** faire approuver la finalité commerciale, les données minimales, les accès, la conservation, les contrats CBS/CRM/Payments/Trade, la définition des outcomes et la base de traitement. Aucun raccordement réel ne doit précéder ces validations.
2. **Référence Rules-only — PROUVÉ techniquement, à rejouer sur données BOA :** exécuter les règles versionnées, vérifier la fraîcheur, la qualité, le périmètre du portefeuille, l’explication et l’audit. Les seuils et exclusions métier sont à confirmer par BOA.
3. **`ML_SHADOW` — À VALIDER avant activation :** calculer la propension en parallèle, la rendre auditable mais sans modifier le classement visible ni les actions proposées. Surveiller la qualité des données, le drift, les scores invalides et le fallback `RULES_ONLY`. Les labels BOA doivent atteindre une maturité approuvée ; l’absence d’outcome ne doit pas devenir un faux négatif.
4. **Décision de suite — À VALIDER par BOA :** comparer le challenger au champion règles, par segment autorisé, examiner la stabilité et les explications, puis décider séparément de poursuivre en shadow, de rester en `RULES_ONLY` ou d’autoriser un `HYBRID_RERANK` strictement limité aux candidates déjà éligibles par règle. Toute régression, dérive bloquante ou ambiguïté de gouvernance déclenche le retour `RULES_ONLY`.

La sortie attendue du pilote n’est pas une promesse de performance. C’est une décision documentée sur la qualité des données, la compréhension par les chargés de clientèle, la traçabilité, la sécurité du périmètre, la maturité des outcomes et l’acceptabilité d’un éventuel enrichissement du classement. **Aucun passage en production BOA ne peut être déduit des tests synthétiques du dépôt.**

## Références internes

[1]: ../../README.md "README du dépôt"
[2]: ../business-rules.md "Moteur déterministe d’intelligence d’opportunités"
[3]: ../ml-engine.md "ML Engine CPU-ready — architecture cible et contrats de gouvernance"
[4]: ../ml-acceptance.md "Acceptation de l’incrément ML"
[5]: ../finalization-status-2026-09-19.md "Rapport final de finalisation technique"
[6]: ../industrialization-governance.md "Gouvernance d’industrialisation et audit d’accès aux données"
[7]: ../ux-architecture.md "Architecture UX"
[8]: ../../architecture/architecture.md "Architecture exécutable"
[9]: ../data-model.md "Modèle relationnel PostgreSQL et pipeline de données synthétiques"
[10]: ../../frontend/src/features/customer/WhyChain.tsx "Chaîne d’explication frontend"
[11]: ../../frontend/src/features/customer/ActionPanel.tsx "Actions commerciales du chargé de clientèle"
[12]: ../../backend/src/boa_oi/resilience/ml_client.py "Client résilient ML et fallback RULES_ONLY"
[13]: ../../tests/e2e/rm-opportunity.spec.ts "Parcours E2E chargé de clientèle et agence"
[14]: ../../tests/unit/test_opportunities.py "Tests unitaires des opportunités"
[15]: ../../tests/unit/test_ml_engine.py "Tests unitaires du moteur ML"

> **Note de lecture :** les références ci-dessus sont des sources internes du dépôt. Les éléments marqués **PROUVÉ** décrivent des preuves techniques ou des tests sur données synthétiques ; ils ne constituent pas une mesure, une validation ou une autorisation BOA.

## Statut de conformité de la note

| Exigence | Vérification |
|---|---|
| Documentation métier en français | **PROUVÉ** à la relecture de ce fichier ; les identifiants techniques restent inchangés. |
| Périmètre documentaire | **PROUVÉ** : cette note décrit l’état technique du dépôt sans constituer une homologation ni une preuve de production bancaire. |
| Aucune donnée BOA ni résultat BOA inventé | **PROUVÉ** : les preuves sont explicitement synthétiques ou documentaires. |
| Hypothèses non démontrées signalées | **PROUVÉ** : mention exacte **HYPOTHÈSE À VALIDER AVEC BOA** utilisée pour seuils, paramètres de pilote et KPI non démontrés. |
| Crédit, ML CPU-only, POC/shadow, LLM/GPU | **PROUVÉ** : limites rappelées sans ambiguïté dans les sections 1 et 4. |
| Distinction de statuts | **PROUVÉ** : **IMPLÉMENTÉ**, **PROUVÉ**, **NON IMPLÉMENTÉ** et **À VALIDER** sont employés explicitement. |
| Proposition de pilote contrôlé en conclusion | **PROUVÉ** : section 5, avec portes réversibles et retour `RULES_ONLY`. |

> Les statuts de la présente note décrivent le contenu du dépôt au moment de la rédaction. Ils ne remplacent pas une validation BOA, une homologation ou un go/no-go de production.
