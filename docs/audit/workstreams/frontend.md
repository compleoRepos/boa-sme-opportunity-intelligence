# Audit frontend premium — BOA SME Opportunity Intelligence

**Périmètre.** Audit en lecture seule du frontend React situé dans `frontend/`, complété par la lecture des tests et de la documentation existants. Aucun fichier de code applicatif n’a été modifié. Le rendu navigateur dynamique n’a pas pu être validé de bout en bout dans cette session : la navigation MCP vers le serveur Vite local a expiré. Les constats ci-dessous distinguent donc les éléments vérifiés par le code, les tests exécutés et les parcours seulement décrits dans les tests E2E.

## Synthèse

Le frontend présente une base premium cohérente et déjà substantielle : shell applicatif, séparation des personas, dashboards CC/agence, drill-down vers la PME, chaîne d’évidence, Rule Studio versionné, simulations, approbation/publication, audit, Model Registry et démo guidée sont effectivement représentés dans le code. Le typecheck, le build de production et les 15 tests unitaires frontend passent.

Les fragilités principales concernent l’accessibilité avancée des modales/drawers, la vérification visuelle réelle aux trois largeurs demandées, et la couverture E2E non exécutée dans cet audit. Les manques les plus nets sont les exports (aucune capacité UI identifiée), un centre de notifications métier, et un véritable paramétrage administrable des libellés : la traduction actuelle est un dictionnaire statique côté frontend, avec quelques noms de produits provenant de l’API.

## Ce qui marche

### Dashboards CC et agence

Le shell expose les entrées distinctes « Cockpit CC » et « Agence », puis les pages Rule Studio, Simulations, ML Governance et Audit selon les rôles (`frontend/src/layout/AppShell.tsx:40-60`). Le dashboard CC consomme un hook de portefeuille/dashboards et permet le filtrage des priorités ; le parcours de test prévoit les KPI, les signaux chiffrés et le lien vers la fiche PME (`frontend/src/features/dashboard/CcDashboardPage.tsx`, `frontend/src/features/dashboard/dashboard.test.tsx`).

Le dashboard agence est prévu pour le drill-down agence → chargé de clientèle → portefeuille → PME → opportunité. Le test E2E vérifie notamment le scope `BR-01`, l’accès refusé à un RM hors périmètre, puis les URL agence/CC et fiche client (`tests/e2e/rm-opportunity.spec.ts:77-116`). Le code affiche également une notice explicite de pilotage commercial et de non-décision de crédit (`frontend/src/features/branch/BranchDashboardPage.tsx:69`).

### Fiche PME et chaîne d’évidence

La fiche PME regroupe profil, santé/activité, propension, opportunités, actions, comptes/produits, transactions et signaux dans des onglets ; elle ouvre des drawers pour l’opportunité et la propension (`frontend/src/features/customer/CustomerSheetPage.tsx:134-162`). Les actions commerciales passent par confirmation, POST/PATCH et invalidation des requêtes concernées (`frontend/src/api/hooks.ts:130-165`).

Le test E2E couvre l’ouverture de la fiche, la chaîne d’évidence, l’activité 6 mois, l’ouverture de l’opportunité, l’enregistrement d’un contact, l’historique et la drawer de propension (`tests/e2e/rm-opportunity.spec.ts:41-75`). La chaîne rend les signaux, la règle métier versionnée, le moteur, la propension ML et l’opportunité sous forme de nœuds navigables (`frontend/src/features/customer/WhyChain.tsx`). La notice de la fiche rappelle explicitement qu’il ne s’agit ni d’une notation de risque ni d’une décision de crédit (`frontend/src/features/customer/CustomerSheetPage.tsx:156`).

### Rule Studio

Le parcours métier est bien matérialisé : lecture SI/ET/ALORS, ajout de conditions/groupes sans code, validation, simulation, soumission, approbation distincte, publication/désactivation et historique des versions. Les actions disponibles dépendent de l’état et du rôle (`frontend/src/features/rules/RuleStudioPage.tsx:45-67`). Les onglets couvrent simulation/impact, test sur une PME et versions/audit (`frontend/src/features/rules/RuleStudioPage.tsx:90-101`).

Les tests unitaires vérifient la lecture et l’édition visuelle de la règle (`frontend/src/features/rules/ruleBlocks.test.tsx`). Le test E2E décrit et automatise le cycle création → validation → simulation → soumission → approbation par un autre contexte → publication, ainsi que la présence du motif dans l’audit (`tests/e2e/rule-studio.spec.ts:15-66`). Le Rule Tester expose une PME, lance le test et affiche la preuve condition par condition (`frontend/src/features/rules/RuleStudioPage.tsx:96-101`).

### Back office, audit et Model Registry

Le back office est structuré en quatre écrans : Rule Studio, historique des simulations, ML Governance/Model Registry et Audit (`frontend/src/layout/AppShell.tsx:56-60`). La page Simulations annonce que les résultats sont persistés et non recalculés côté navigateur (`frontend/src/features/backoffice/BackOfficePages.tsx:128-132`).

La page Audit affiche le journal Rule Studio avec action, version, horodatage, utilisateur et motif, ainsi que les dernières actions commerciales avec client, auteur, résultat et date (`frontend/src/features/backoffice/BackOfficePages.tsx:136-153`). Le test E2E vérifie aussi l’accès au Model Registry, la sélection d’un modèle et la présence du seuil de décision et des coefficients (`tests/e2e/rule-studio.spec.ts:68-75`). Les hooks dédiés consomment bien `/api/v1/ml/models` et `/api/v1/ml/models/active` (`frontend/src/api/hooks.ts:109-116`).

### Mode démo

Le mode démo est visible en environnement de développement via « Démo 5 min » dans le topbar (`frontend/src/layout/AppShell.tsx:99-100`). Le guide orchestre des étapes ciblées pour dashboard CC, agence, fiche PME, Rule Studio, simulation, approbation/publication et ML Governance, en changeant de persona et de route (`frontend/src/features/demo/DemoGuide.tsx`). Le panneau de démo est identifié comme complémentaire, possède un libellé ARIA, une progression et des boutons précédent/suivant/terminer. Les cibles sont mises en évidence par `data-demo-target` et une outline dédiée (`frontend/src/styles/screens.css:1163-1176`).

### États d’interface et libellés visibles

Les chargements, états vides, erreurs avec corrélation et retry sont factorisés (`frontend/src/ui/States.tsx:6-31`). La recherche globale, la navigation principale, les fils d’Ariane, les personas de développement et les messages de démonstration sont présents (`frontend/src/layout/AppShell.tsx:78-117`). Les libellés métier sont utilisés largement via `label(...)` dans les tableaux et cartes, ce qui évite d’afficher systématiquement les enums bruts.

### Tests et qualité de build

Vérifications exécutées dans cette session :

- `npm test -- --reporter=verbose` : **5 fichiers, 15 tests passés**.
- `npm run typecheck` : **succès**.
- `npm run build` : **succès**, Vite produit les bundles de production (dont charts ~390 kB non compressé et bundle principal ~414 kB).
- `git status` après audit : seul le nouveau chemin documentaire `docs/audit/` est non suivi ; aucune modification sous `frontend/src`.

## Fragilités

### Validation visuelle et responsive incomplète

Le code prévoit une adaptation à 1280 px, 1080 px et 860 px (`frontend/src/styles/layout.css:567-665`, `frontend/src/styles/screens.css:1188-1259`). À 1280 px, les grilles et lignes de priorité se resserrent ; sous 1080 px, les colonnes principales passent en une colonne et le panneau de démo s’élargit ; sous 860 px, le menu latéral devient mobile et la recherche globale est masquée. Cela donne une bonne intention de couverture pour 1440/1280/1024, mais **aucune capture ou inspection navigateur effective à 1440 et 1280 n’a été obtenue pendant cet audit**. Le test E2E existant couvre uniquement 1024 px et vérifie l’absence de débordement horizontal (`tests/e2e/rm-opportunity.spec.ts:118-126`).

À 1024 px, le seuil `max-width:1080px` s’applique déjà : dashboard, hero PME et combinaisons passent en colonne. Le tableau est encapsulé dans `table-wrap`, ce qui limite le risque de casser la page, mais le confort de lecture des tableaux larges reste à vérifier visuellement. Il manque des tests systématiques par écran et par largeur, notamment pour Rule Studio, audit, simulation et Model Registry.

### Accessibilité clavier et lecteur d’écran : bonne base, garanties incomplètes

Points positifs : navigation et recherche ont des landmarks/labels, les boutons icône ont un `aria-label`, les lignes clients sont activables au clavier avec Enter (`frontend/src/pages/CustomersPage.tsx`), les onglets utilisent `role=tablist`/`role=tab`, et les états d’erreur/chargement utilisent `role=alert` ou `role=status`.

Fragilités constatées dans les primitives :

- `Modal` et `Drawer` gèrent Escape, mais ne mettent pas en place de **focus trap**, de déplacement initial du focus, ni de restitution du focus à l’élément déclencheur (`frontend/src/ui/Modal.tsx:6-18`, `frontend/src/ui/Drawer.tsx:6-25`). Un lecteur d’écran ou un utilisateur clavier peut donc sortir du dialogue vers l’arrière-plan.
- Les onglets ont `aria-selected`, mais pas de `aria-controls`, d’identifiant de panneau, ni de comportement flèches/Home/End (`frontend/src/ui/Tabs.tsx:5-10`). Ils restent techniquement utilisables comme boutons, mais ne suivent pas complètement le modèle ARIA tablist.
- Le menu profil annonce `role=menu`/`menuitem`, sans gestion explicite des flèches, Escape, focus initial et retour focus (`frontend/src/layout/AppShell.tsx:101-114`).
- La zone de toasts est `aria-live="polite"` et les erreurs sont aussi `role="status"`; une notification d’erreur urgente pourrait ne pas être annoncée assez vite (`frontend/src/ui/Toast.tsx`).
- Aucun test axe/pa11y, test de lecteur d’écran ou parcours clavier complet n’est présent dans les tests repérés. Le focus visuel existe côté styles, ainsi qu’une préférence `prefers-reduced-motion`, mais cela ne remplace pas une validation comportementale.

### Démo guidée dépendante du mode développement

La démo est conditionnée à `auth.devMode` (`frontend/src/layout/AppShell.tsx:99-100`) et les changements de persona sont des personas de démonstration. C’est approprié pour un POC synthétique, mais il faut éviter de la considérer comme une preuve de fonctionnement production : aucun test E2E de l’ensemble des étapes guidées n’a été exécuté ici, et le panneau ne semble pas gérer un focus dédié lorsqu’il apparaît.

### Performance de chargement

Le build passe, mais les bundles charts et application sont volumineux : environ 390 kB et 414 kB avant gzip. Cela peut dégrader le premier chargement sur poste ou réseau contraint. Aucun budget de performance, test Lighthouse, découpage de routes ou mesure Web Vitals n’a été trouvé dans le périmètre audité.

## Manques

### Exports

Aucune action ou hook d’export CSV/XLSX/PDF, aucun bouton « Exporter », aucun téléchargement et aucune route d’export n’a été identifié dans `frontend/src` par recherche des termes `export`, `download`, `csv` et `xlsx`. Les pages affichent des tableaux et paginent certaines listes, mais il n’existe pas de sortie exploitable pour un reporting agence, audit ou portefeuille. **Manque bloquant si les exports font partie du périmètre premium attendu.**

### Notifications

Le frontend possède uniquement des toasts locaux de succès/erreur/info avec expiration automatique (`frontend/src/ui/Toast.tsx`). Aucun centre de notifications, aucune cloche, aucun endpoint de notifications, aucune préférence de canal et aucun marquage lu/non lu n’a été identifié. Les toasts confirment une action dans la session, mais ne couvrent pas les alertes métier persistantes, les échecs de simulation ou les événements d’approbation hors session.

### Paramétrage des libellés

`frontend/src/api/format.ts` contient un dictionnaire statique `labels` et une fonction de repli qui transforme les enums ; il n’existe ni écran d’administration des libellés, ni chargement de catalogue de traduction, ni gestion de locale/tenant. Les noms de produits peuvent venir du Product Service, mais les libellés d’états, signaux, périodes, rôles et actions restent codés côté frontend. **Le besoin « paramétrage des libellés » n’est donc pas couvert comme capacité administrable.**

### Responsive et accessibilité testés automatiquement

La couverture E2E identifiée cible le workflow commercial, l’agence, Rule Studio, Model Registry et une largeur tablette 1024 px. Aucun test dédié 1440 px/1280 px, aucun test de zoom, contraste, lecteur d’écran, tab order, focus trap ou navigation par flèches des menus/onglets n’a été trouvé. Les tests existants sont une preuve de contrat et de parcours, pas une validation exhaustive de qualité UX premium.

## Preuves et recommandations de clôture

| Domaine | Preuve disponible | Conclusion d’audit |
|---|---|---|
| Build/typecheck | Sortie `npm run typecheck && npm run build` : succès | Base technique saine |
| Unit frontend | Sortie Vitest : 5 fichiers / 15 tests passés | Couverture logique ciblée, pas exhaustive |
| Dashboard CC | `frontend/src/features/dashboard/CcDashboardPage.tsx`, `dashboard.test.tsx` | Fonctionnalités principales présentes |
| Dashboard agence | `BranchDashboardPage.tsx`, `tests/e2e/rm-opportunity.spec.ts:77-116` | Drill-down conçu et scénarisé |
| Fiche PME | `CustomerSheetPage.tsx:134-162`, E2E `rm-opportunity.spec.ts:41-75` | Parcours commercial bien couvert sur le papier |
| Rule Studio | `RuleStudioPage.tsx:45-101`, unit + E2E `rule-studio.spec.ts:15-66` | Workflow métier complet représenté |
| Back office/audit | `BackOfficePages.tsx:128-153` | Simulations et traçabilité présentes |
| Model Registry | `api/hooks.ts:109-116`, E2E `rule-studio.spec.ts:68-75` | Consultation des modèles présente |
| Démo | `DemoGuide.tsx`, `AppShell.tsx:99-100` | Guidage de démonstration présent, dev-only |
| Responsive | CSS `max-width:1280/1080/860`, E2E 1024 `rm-opportunity.spec.ts:118-126` | Intention correcte ; preuves 1440/1280 manquantes |
| Accessibilité | Landmarks, labels, focus ring, Escape | Base correcte ; focus trap/ARIA avancé manquants |
| Exports | Recherche frontend sans résultat exploitable | Non implémenté |
| Notifications | Toast local seulement | Centre/persistance non implémentés |
| Libellés | `api/format.ts` dictionnaire statique | Paramétrage métier non implémenté |

**Priorités recommandées.** Premièrement, ajouter les exports et clarifier les formats/périmètres autorisés. Deuxièmement, implémenter les notifications persistantes et leur état lu/non lu si elles sont attendues par le produit. Troisièmement, externaliser les libellés vers un catalogue administrable ou un service de configuration. Enfin, compléter les tests E2E par 1440/1280/1024 et les audits clavier/axe, puis corriger le focus trap/restauration des modales, drawers et menus.

## Limites de l’audit

Le backend/stack complet n’a pas été démarré dans cette session et la navigation navigateur vers Vite local a expiré ; aucune donnée live ni capture visuelle n’est donc utilisée comme preuve. Les mentions de parcours E2E indiquent la couverture écrite dans le dépôt, pas une exécution réussie pendant cet audit. Le rapport reste strictement en lecture seule vis-à-vis du code applicatif.
