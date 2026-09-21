# Scénario de démonstration — 15 minutes, cinq actes

**Produit :** BOA SME Opportunity Intelligence
**Objet :** script de démonstration technique et métier du POC
**Date de référence :** 19 septembre 2026
**Statut du document :** scénario réécrit à partir du mode démo, des parcours E2E et de la documentation du dépôt

## 1. Cadre de lecture et limites de la démonstration

Cette démonstration présente un **POC d’intelligence commerciale pour portefeuilles PME**. Elle montre comment des règles versionnées, des signaux et une propension commerciale peuvent aider un chargé de clientèle à organiser ses contacts. Elle ne montre ni une décision de crédit, ni une probabilité de défaut, ni une notation de risque, ni une autorisation de financement. **Aucune décision de crédit n’est prise par le produit.** Le signal `FINANCIAL_STRESS_SIGNAL` reste un signal relationnel à examiner par un humain.

Toutes les données du mode démo sont synthétiques. Elles ne sont pas des données BOA et ne permettent pas d’annoncer une performance bancaire réelle. Les volumes, KPI, coûts, seuils, durées et critères d’acceptation propres à BOA qui ne sont pas établis par une preuve interne portent la mention **HYPOTHÈSE À VALIDER AVEC BOA**. Les identifiants techniques, noms de routes, statuts et noms de fichiers sont conservés tels quels.

Le ML est un **modèle classique CPU-only**, verrouillé en `POC_SHADOW`. Son score est visible pour l’explication et l’audit, mais la priorité affichée reste `RULES_ONLY`. Le dépôt ne démontre ni entraînement sur historique BOA, ni calibration BOA, ni performance prédictive BOA. **Aucun LLM et aucun GPU ne sont requis**.

La lecture des capacités suit quatre statuts :

| Statut | Sens dans ce scénario |
|---|---|
| **IMPLÉMENTÉ** | La capacité est présente dans le code ou dans le parcours applicatif inspecté. |
| **PROUVÉ** | La capacité est étayée par un test, une validation ou un artefact interne identifiable. |
| **NON IMPLÉMENTÉ** | La capacité, la preuve ou le raccordement attendu n’est pas disponible dans le dépôt. |
| **À VALIDER** | Le dépôt ne peut pas décider seul d’une règle métier, d’un seuil, d’un périmètre, d’une exigence de gouvernance ou d’un résultat BOA. La formulation opérationnelle est **HYPOTHÈSE À VALIDER AVEC BOA**. |

## 2. Préparation et règles de parole

La préparation recommandée est le mode local prévu par [`README.md`](../README.md) : `scripts/local-stack.sh up`, puis `scripts/local-stack.sh rules` si les règles Rule Studio ne sont pas présentes. Le mode local utilise `BOA_AUTH_DISABLED=true` et `VITE_AUTH_DISABLED=true`, des personas de démonstration et des données synthétiques. Il ne faut pas le présenter comme un environnement bancaire ou comme une configuration de production.

Avant l’ouverture du scénario, vérifier que l’interface affiche l’environnement de démonstration et la mention « Données synthétiques · aucune décision de crédit ». Le bouton de guidage porte actuellement le libellé « Démo 5 min » dans [`DemoGuide.tsx`](../frontend/src/features/demo/DemoGuide.tsx). Le présent document transforme le contenu de ce guide en une narration de quinze minutes ; il ne prétend pas que le bouton a été modifié pour afficher quinze minutes.

Les preuves techniques citées ci-dessous sont des preuves de dépôt. Elles ne remplacent pas une validation BOA. En particulier, les données synthétiques, les résultats de simulation et les compteurs du POC ne doivent jamais être verbalisés comme des résultats de portefeuille BOA. Si un résultat n’apparaît pas dans l’interface pendant la session, dire simplement : « Ce résultat n’est pas disponible dans cette exécution ; je ne l’invente pas. »

## Acte 1 — CC et dashboard

**Durée : 3 minutes.**

| Élément | Script de démonstration |
|---|---|
| **Persona** | Ahmed Mansouri, persona `cc`, rôle technique `RELATIONSHIP_MANAGER`. |
| **Écran / route** | Dashboard CC, route `/`. La navigation de la persona est définie dans [`AppShell.tsx`](../frontend/src/layout/AppShell.tsx) et dans [`ux-architecture.md`](./ux-architecture.md). |
| **Gestes** | 1. Ouvrir le mode démo et sélectionner Ahmed. 2. Vérifier l’en-tête et les quatre KPI affichés par le dashboard. 3. Parcourir la file « À regarder aujourd’hui ». 4. Sélectionner une ligne qui n’est pas « Suivi standard ». 5. Ne pas annoncer de valeur de KPI qui n’apparaît pas dans cette exécution. |
| **Phrase à dire** | « Ahmed voit uniquement son cockpit commercial. Le dashboard met en avant les PME à examiner, les signaux disponibles et la prochaine action. Cette vue aide à prioriser un contact ; elle ne décide ni d’un crédit ni d’une limite. » |
| **Preuve technique** | **IMPLÉMENTÉ / PROUVÉ :** `tests/e2e/rm-opportunity.spec.ts` vérifie la connexion de la persona `cc`, la présence de quatre éléments `.kpi`, la file `.priority-row`, le périmètre du dashboard et le refus de certaines lectures hors périmètre. Le test vérifie aussi qu’un paramètre `relationshipManagerId=rm-02` ne permet pas de changer le périmètre effectif du dashboard. **À ne pas extrapoler :** ce test ne mesure aucune performance bancaire BOA. |
| **Question difficile probable** | « Les KPI affichés sont-ils déjà les KPI du portefeuille BOA ? » |
| **Réponse courte** | « Non. Ils proviennent du jeu synthétique du POC. Les définitions, la population et les KPI BOA restent **HYPOTHÈSE À VALIDER AVEC BOA**. » |
| **Plan de repli** | Si le dashboard est vide ou si un service n’est pas prêt, ouvrir la fiche d’une PME synthétique depuis `/clients` si elle est disponible, puis montrer la chaîne d’évidence. Sinon, afficher [`finalization-status-2026-09-19.md`](./finalization-status-2026-09-19.md) et rappeler que la readiness production est `BLOCKED`, sans inventer de KPI. |
| **Statut** | Périmètre et navigation : **IMPLÉMENTÉ / PROUVÉ** par le parcours E2E. Volumes et KPI BOA : **NON IMPLÉMENTÉ / À VALIDER** — **HYPOTHÈSE À VALIDER AVEC BOA**. |

## Acte 2 — Fiche PME et explication

**Durée : 3 minutes 30 secondes.**

| Élément | Script de démonstration |
|---|---|
| **Persona** | Ahmed Mansouri, `RELATIONSHIP_MANAGER`. |
| **Écran / route** | Fiche PME `/clients/:id`, avec rail de portefeuille. La route et les panneaux adressables sont décrits dans [`CustomerSheetPage.tsx`](../frontend/src/features/customer/CustomerSheetPage.tsx) et [`ux-architecture.md`](./ux-architecture.md). |
| **Gestes** | 1. Cliquer sur la première PME priorisée. 2. Vérifier les sections « Santé de la relation », « Activité » et « Pourquoi cette opportunité ? ». 3. Changer la période, par exemple de `12 mois` à `6 mois`, sans annoncer une valeur avant de la lire à l’écran. 4. Ouvrir « Voir l’opportunité ». 5. Ouvrir l’onglet « Signaux & évidence ». 6. Cliquer sur le nœud de propension pour afficher le détail du modèle et des contributions. |
| **Phrase à dire** | « La fiche rassemble l’identité, l’activité observée, les signaux, la règle déclenchée, la propension et l’opportunité. Chaque élément est daté et versionné quand le service le fournit. Nous parlons de propension commerciale, pas de risque de crédit. » |
| **Preuve technique** | **IMPLÉMENTÉ / PROUVÉ :** `tests/e2e/rm-opportunity.spec.ts` vérifie la navigation vers `/clients/SME-…`, les blocs `#health` et `#why`, le changement de période, l’absence de tri par propension, le libellé « Priorité règles », le drawer d’opportunité, l’onglet « Signaux & évidence » et le drawer de propension contenant `POC shadow`, `Priorité RULES_ONLY` et « Aucune décision de crédit ». [`CustomerSheetPage.tsx`](../frontend/src/features/customer/CustomerSheetPage.tsx) montre que les graphiques et les données de fiche sont lus par hooks API ; le commentaire de code précise que la date de référence vient de la dernière observation analytique et non d’une date codée en dur. |
| **Question difficile probable** | « Le pourcentage de propension est-il une probabilité de remboursement ou une décision d’octroi ? » |
| **Réponse courte** | « Non. C’est une observation shadow de propension commerciale, affichée séparément et sans effet sur la priorité issue des règles. Il n’y a aucune décision de crédit. Les performances BOA et la calibration BOA ne sont pas démontrées. » |
| **Plan de repli** | Si aucune opportunité n’est ouverte pour la PME choisie, montrer la section « Aucune opportunité ouverte » et expliquer qu’une absence est un résultat explicable. Ouvrir ensuite une PME de la file qui possède une opportunité. Si le drawer échoue, conserver la fiche et citer la chaîne `signals → rules → opportunity`, avec inférence ML shadow persistée en parallèle, documentée dans [`ml-engine.md`](./ml-engine.md). |
| **Statut** | Fiche, explication, signaux et propension : **IMPLÉMENTÉ / PROUVÉ** par le code et l’E2E. Qualité prédictive, calibration et valeur commerciale BOA : **NON IMPLÉMENTÉ / À VALIDER** — **HYPOTHÈSE À VALIDER AVEC BOA**. |

## Acte 3 — Action, outcome et cooldown

**Durée : 3 minutes.**

| Élément | Script de démonstration |
|---|---|
| **Persona** | Ahmed Mansouri, `RELATIONSHIP_MANAGER`. |
| **Écran / route** | Fiche PME `/clients/:id`, panneau « Action commerciale » et drawer d’opportunité. |
| **Gestes** | 1. Ouvrir l’action commerciale de l’opportunité. 2. Choisir « Contacté » pour illustrer un `outcome` structuré. 3. Saisir une note strictement synthétique, non sensible, par exemple « Contact réalisé dans le parcours E2E ». 4. Cliquer sur « Enregistrer ». 5. Vérifier le toast « Action enregistrée » et l’entrée dans l’onglet « Historique des actions ». 6. Montrer, sans nécessairement l’enregistrer une seconde fois, le choix « À revoir » et son échéance technique de 30 jours. 7. Revenir au dashboard pour constater seulement ce que l’API renvoie après invalidation des requêtes. |
| **Phrase à dire** | « Le CC décide de l’action. L’interface enregistre l’action et, si le choix le prévoit, l’outcome associé. Le choix “À revoir” matérialise un cooldown technique afin d’éviter de réémettre immédiatement la même opportunité ; sa durée métier n’est pas une règle BOA arrêtée. » |
| **Preuve technique** | **IMPLÉMENTÉ / PROUVÉ :** [`ActionPanel.tsx`](../frontend/src/features/customer/ActionPanel.tsx) envoie `POST /api/v1/opportunities/{opportunityId}/actions`, puis `PATCH /api/v1/actions/{actionId}` pour l’outcome. Les choix disponibles incluent `À contacter`, `Contacté`, `Intéressé`, `Offre créée`, `Converti`, `Non intéressé` et `À revoir`. `tests/e2e/rm-opportunity.spec.ts` vérifie l’enregistrement, le toast, l’historique et la présence du texte saisi. Les tests unitaires de [`test_opportunity_lifecycle.py`](../tests/unit/test_opportunity_lifecycle.py) vérifient les transitions, la déduplication de génération et des cooldowns. La configuration de démonstration contient `deferred_cooldown_days: 30` dans [`database/seed/rules.yaml`](../database/seed/rules.yaml). |
| **Question difficile probable** | « Les outcomes du POC sont-ils déjà des labels BOA suffisamment mûrs pour entraîner le modèle ? » |
| **Réponse courte** | « Non. Le mécanisme de collecte est implémenté, mais les labels BOA matures et leur maturité d’observation ne le sont pas. Le dépôt indique `automaticTraining=false` et `trainingReady=false` pour les outcomes synthétiques. » |
| **Plan de repli** | Si l’enregistrement échoue, ne pas simuler le succès. Montrer l’erreur et sa corrélation, puis lire le code de [`ActionPanel.tsx`](../frontend/src/features/customer/ActionPanel.tsx) ou le test E2E. Si l’on ne peut pas revenir au dashboard, rester sur l’historique et expliquer le contrat API. |
| **Statut** | Création d’action, outcome et audit applicatif : **IMPLÉMENTÉ / PROUVÉ**. Cooldown de 30 jours : **IMPLÉMENTÉ / PROUVÉ** comme configuration et comportement technique du POC, mais sa pertinence métier et sa durée BOA sont **À VALIDER** — **HYPOTHÈSE À VALIDER AVEC BOA**. Labels BOA d’entraînement : **NON IMPLÉMENTÉ**. |

## Acte 4 — Responsable agence

**Durée : 2 minutes 30 secondes.**

| Élément | Script de démonstration |
|---|---|
| **Persona** | Salma Berrada, persona `agence`, rôle technique `BRANCH_MANAGER`. |
| **Écran / route** | Dashboard agence `/`, puis `/agence/cc/:rmId`, puis `/clients/:id?cc=…`. Les routes sont listées dans [`ux-architecture.md`](./ux-architecture.md). |
| **Gestes** | 1. Changer de persona vers Salma. 2. Vérifier le titre « Agence … ». 3. Sélectionner un chargé de clientèle dans le tableau. 4. Vérifier le drill-down vers `/agence/cc/:rmId`. 5. Ouvrir une PME puis son opportunité. 6. Ne pas présenter de classement ou de résultat agrégé qui n’est pas visible dans cette session. |
| **Phrase à dire** | « Salma ne remplace pas le jugement du CC : elle suit le périmètre agence et descend jusqu’au portefeuille, à la PME et à l’opportunité. La frontière d’accès est une propriété technique à vérifier par service, pas une promesse fondée sur le seul écran. » |
| **Preuve technique** | **IMPLÉMENTÉ / PROUVÉ :** `tests/e2e/rm-opportunity.spec.ts` ouvre la persona `agence`, vérifie `/api/v1/dashboards/branch` et le périmètre `BR-01`, refuse un responsable hors périmètre, puis vérifie les routes `/agence/cc/…` et `/clients/SME-…?cc=…`. [`finalization-status-2026-09-19.md`](./finalization-status-2026-09-19.md) classe la sécurité et les périmètres comme preuves du POC, tout en rappelant que l’homologation de production n’est pas réalisée. |
| **Question difficile probable** | « La vue agence prouve-t-elle un filtrage objet par objet dans une future installation BOA ? » |
| **Réponse courte** | « Elle prouve le comportement du POC testé. La matrice exhaustive route × rôle × agence × portefeuille × objet et son homologation BOA restent **HYPOTHÈSE À VALIDER AVEC BOA**. » |
| **Plan de repli** | Si le tableau agence n’est pas disponible, revenir au dashboard CC et montrer le refus d’un accès hors périmètre dans le parcours E2E. Ne pas utiliser une vue back office pour remplacer artificiellement la vue agence. |
| **Statut** | Navigation agence et contrôles testés : **IMPLÉMENTÉ / PROUVÉ** pour le POC. Homologation sécurité, périmètre BOA et exigences d’accès de production : **NON IMPLÉMENTÉ / À VALIDER** — **HYPOTHÈSE À VALIDER AVEC BOA**. |

## Acte 5 — Rule Studio et gouvernance ML

**Durée : 3 minutes.**

| Élément | Script de démonstration |
|---|---|
| **Persona** | Youssef Tazi, persona `backoffice`, puis Nadia Ouazzani, persona `approbateur`. Les rôles techniques sont respectivement `BUSINESS_ANALYST` et `RULE_APPROVER`. Pour la lecture du registre, utiliser le back office autorisé. |
| **Écran / route** | Rule Studio : `/back-office/regles`, puis `/back-office/regles/SME_INVESTMENT_001` ou la règle effectivement présente. Gouvernance ML : `/back-office/modeles`. Le catalogue et les routes sont présents dans [`RuleStudioPage.tsx`](../frontend/src/features/rules/RuleStudioPage.tsx) et [`AppShell.tsx`](../frontend/src/layout/AppShell.tsx). |
| **Gestes** | 1. Ouvrir Rule Studio et sélectionner une règle réellement retournée par l’API. 2. Lire les blocs `SI`, `ET`, `ALORS` et la version affichée. 3. Ouvrir « Modifier » ou une règle de démonstration, sans affirmer qu’un seuil précis est présent si l’écran ne le montre pas. 4. Valider la configuration et lancer la simulation si le bouton et la période sont disponibles. 5. Lire uniquement les résultats de simulation réellement renvoyés par l’API ; ne pas annoncer une population ou un nombre de correspondances à l’avance. 6. Soumettre à approbation. 7. Passer à Nadia, approuver puis publier si l’état du workflow le permet. 8. Ouvrir « Versions & audit ». 9. Ouvrir `/back-office/modeles`, consulter le registre, le seuil, les coefficients, le mode et `productionPerformanceClaim`. |
| **Phrase à dire** | « Le métier configure une règle sans code ; le workflow sépare l’auteur et l’approbateur. Le registre montre un score shadow versionné. La priorité reste entièrement issue des règles ; aucune promotion ML n’est permise sans preuves BOA. Aucun LLM ni GPU n’est requis. » |
| **Preuve technique** | **IMPLÉMENTÉ / PROUVÉ :** `tests/e2e/rule-studio.spec.ts` couvre le workflow des règles. `tests/e2e/governance.spec.ts` vérifie une policy active règles `1`/ML `0`, `POC_SHADOW`, `productionPerformanceClaim=false`, le rejet d’une activation hybride et le blocage d’une promotion synthétique. Le lot 10 relie ces assertions à une preuve Docker JSON. |
| **Question difficile probable** | « Pourquoi montrer un modèle si vous n’avez pas de labels BOA matures, et le modèle est-il déjà en production ? » |
| **Réponse courte** | « Nous montrons le socle de gouvernance et le chemin CPU shadow, pas une homologation. L’entraînement BOA, la calibration et les performances BOA sont **NON IMPLÉMENTÉS**. Le score ne change pas la priorité ; la readiness production est `BLOCKED`. » |
| **Plan de repli** | Si la règle ciblée n’existe pas, ouvrir `/back-office/regles` et choisir une règle retournée par l’API. Si la simulation n’aboutit pas, montrer l’état du job sans annoncer de résultat. Si le back office ou le registre est indisponible, afficher les E2E et [`finalization-status-2026-09-19.md`](./finalization-status-2026-09-19.md), puis rappeler explicitement que l’absence de preuve ne doit pas être remplacée par une valeur inventée. |
| **Statut** | Rule Studio, workflow et registre : **IMPLÉMENTÉ / PROUVÉ** pour le POC. Entraînement, labels, calibration et performance BOA : **NON IMPLÉMENTÉ**. Passage en production, seuils d’acceptation, modèle champion et critères d’arrêt BOA : **À VALIDER** — **HYPOTHÈSE À VALIDER AVEC BOA**. LLM/GPU : **NON REQUIS** par choix d’architecture ; aucun appel runtime n’est nécessaire. |

## 3. Conclusion à prononcer après quinze minutes

« Ce que nous venons de voir est un parcours POC de bout en bout : périmètre CC et agence, fiche PME explicable, action et outcome, règles versionnées et gouvernance ML. Le socle est démontrable sur données synthétiques et CPU. Il ne constitue pas une performance bancaire BOA, une homologation de sécurité, une décision de crédit ou une autorisation de production.

Les prochaines décisions ne peuvent pas être inventées par le dépôt : données BOA autorisées, labels matures, définition des outcomes, seuils, périmètres, exigences DPO et sécurité, intégrations SI, sauvegarde-restauration, SLO et critères d’arrêt. Chacun de ces points est **HYPOTHÈSE À VALIDER AVEC BOA**. »

## 4. Matrice de non-affirmation

| Sujet | Ce que la démonstration peut dire | Ce qu’elle ne doit pas dire |
|---|---|---|
| Données | « Les données affichées sont synthétiques et servies par le Gateway du POC. » | « Voici les données réelles BOA » ou « le portefeuille BOA obtient ce résultat ». |
| Opportunité | « Le moteur expose une opportunité commerciale explicable avec des preuves et des versions. » | « Le moteur accorde, refuse, chiffre ou tarifie un crédit ». |
| `FINANCIAL_STRESS_SIGNAL` | « C’est un signal relationnel à examiner avec le client. » | « C’est un score de risque, de défaut ou de crédit ». |
| ML | « Le modèle classique CPU-only est observé en `POC_SHADOW`; la priorité reste `RULES_ONLY`. » | « Le modèle change le classement, est calibré, validé ou performant sur BOA ». |
| LLM / GPU | « Aucun LLM ni GPU n’est requis par le runtime. » | « Un LLM explique ou décide l’opportunité ». |
| KPI, volumétrie, coûts, seuils | « Nous lisons la valeur effectivement retournée par cette exécution. » | Toute valeur générique non affichée ou non prouvée ; elle serait **HYPOTHÈSE À VALIDER AVEC BOA**. |
| Simulation | « Le résultat vient de l’API de simulation si le job aboutit. » | Un nombre de correspondances ou un gain annoncé avant exécution. |
| Production | « La readiness du POC est gouvernée mais reste `BLOCKED` pour la production. » | « Le produit est prêt pour la production bancaire ». |

## 5. Enregistrement vidéo optionnel

[`scripts/record-demo.cjs`](../scripts/record-demo.cjs) automatise la navigation dans la stack locale et produit plusieurs séquences WebM ainsi qu'un fichier de marques temporelles. Ces séquences techniques peuvent servir au montage des cinq actes ci-dessus, mais ne remplacent ni le scénario, ni les tests E2E, ni les artefacts de preuve.

```bash
node scripts/record-demo.cjs
```

Le script doit être exécuté uniquement sur le jeu de données synthétique local. Une vidéo produite ne démontre pas une capacité de production, une performance ML, une intégration AWS ou une validation BOA.

## Références internes

[1]: ../README.md "README du dépôt et mode local"
[2]: ./finalization-status-2026-09-19.md "Rapport final de finalisation technique"
[3]: ./ux-architecture.md "Architecture UX et mode démonstration"
[4]: ../frontend/src/features/demo/DemoGuide.tsx "Guide de démonstration implémenté"
[5]: ../frontend/src/layout/AppShell.tsx "Shell applicatif, personas et navigation"
[6]: ../frontend/src/features/customer/CustomerSheetPage.tsx "Fiche PME et chaîne d’évidence"
[7]: ../frontend/src/features/customer/ActionPanel.tsx "Actions commerciales, outcomes et cooldown technique"
[8]: ../frontend/src/features/rules/RuleStudioPage.tsx "Catalogue Rule Studio et routes frontend"
[9]: ../tests/e2e/rm-opportunity.spec.ts "Parcours E2E CC, fiche PME, action et agence"
[10]: ../tests/e2e/rule-studio.spec.ts "Parcours E2E Rule Studio et Model Registry"
[11]: ../tests/e2e/governance.spec.ts "Parcours E2E gouvernance, RBAC et MLOps"
[12]: ../tests/unit/test_opportunity_lifecycle.py "Tests unitaires du cycle de vie et des cooldowns"
[13]: ../database/seed/rules.yaml "Configuration seed des règles et durées techniques"
[14]: ./business-rules.md "Règles métier et limites d’usage"
[15]: ./rule-studio.md "Spécification Rule Studio et invariants de gouvernance"
[16]: ./industrialization-governance.md "Gouvernance d’industrialisation et sujets à valider"
[17]: ../tests/e2e/auth.ts "Personas et authentification E2E"
[18]: ../scripts/record-demo.cjs "Automatisation optionnelle de l'enregistrement local"

[1] [2] [3] [4] [5] [6] [7] [8] [9] [10] [11] [12] [13] [14] [15] [16] [17] [18]

> **Rappel final :** aucune décision de crédit ; ML classique CPU-only en POC/shadow faute de labels BOA matures ; aucun LLM/GPU requis ; aucune performance bancaire réelle annoncée.
