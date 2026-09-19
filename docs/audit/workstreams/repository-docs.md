# Audit en lecture seule — dépôt et documents

**Dépôt audité :** `/home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence`
**Exigences comparées :** `/home/ubuntu/upload/Pasted_content_100.txt`
**Date de l’audit :** 2026-09-19
**Périmètre :** historique Git, branches de référence, tests et résultats collectés, documents de pitch/démonstration/FAQ/pilote, et éléments vérifiables liés aux exigences. Aucun code n’a été modifié.

## Conclusion

Le dépôt présent sur `main` contient une base technique substantielle et le commit de validation ML annoncé pour 500 PME synthétiques. Ce commit n’est pas perdu sur une branche séparée : `c658bfc` est ancêtre de `main` (`d40ecf6`) et figure donc dans le contenu courant. En revanche, la branche `feat/ml-integration-validation` reste positionnée sur `c658bfc`, tandis que `main` a avancé avec la finalisation UX/ML et le commit de fusion. Il faut donc utiliser `main`/`origin/main` comme référence de l’état intégré ; la branche de validation est une référence historique plus ancienne, pas l’état courant.

Les chiffres de test doivent être présentés avec prudence. Le dépôt contient **106 fonctions de test unitaires** et **8 appels de tests Playwright E2E** répartis dans 3 fichiers de spécification. Ce sont des comptes statiques du code, pas des tests dont l’exécution complète est prouvée. Le seul état d’exécution persistant trouvé est `tests/e2e/test-results/.last-run.json`, qui dit `passed` avec `failedTests: []`, sans date, commit, durée ni détail de cas. Le rapport HTML Playwright est présent sur disque mais ignoré par Git et aucun artefact brut de résultats, couverture, JUnit ou charge n’est versionné. Il est donc impossible d’affirmer à partir du dépôt que les 106 tests unitaires, les 8 cas E2E, les neuf contrôles E2E cités dans la documentation ou la validation de charge ont tous été exécutés et passés.

Les livrables de discours demandés ne sont pas livrés sous la structure demandée. `docs/pitch/`, un plan de pilote dédié, une FAQ dédiée et `docs/DECISIONS.md` sont absents. Le scénario existant est un scénario intégré de **cinq minutes**, alors que l’exigence demande **quinze minutes en cinq actes** avec une structure écran/phrase/question/réponse. Il couvre plusieurs thèmes, mais ne démontre pas la conformité exacte au format demandé.

## 1. Référence Git et décalage éventuel de branche

À l’instant de l’audit, `HEAD` est `main` et le dépôt est propre : `main...origin/main`, sans modification locale. Les références observées sont :

| Référence | Commit | Lecture de l’état |
|---|---|---|
| `main`, `origin/main` | `d40ecf6` | état intégré courant, fusion de `feat/ux-premium-ml-integrated` |
| `feat/ml-integration-validation`, `origin/feat/ml-integration-validation` | `c658bfc` | branche de validation ML plus ancienne |
| `claude/feat/ux-premium-cockpit` | `3e43581` | commit UX référencé dans l’historique, déjà intégré via le commit de fusion |

Le commit `c658bfc` porte le message `test: validate end-to-end ML integration on 500 SMEs`. La commande `git merge-base --is-ancestor c658bfc main` retourne un succès : le commit de validation ML est donc bien inclus dans `main`. Le différentiel de branche est un différentiel d’avance de `main`, non une divergence de contenu ML : `main` contient le commit de validation puis les commits de finalisation UX/ML. La formulation correcte est donc : **la branche ML publiée est en retard sur `main`, mais son contenu de validation a été fusionné ; il n’existe pas de preuve qu’il faille auditer la branche ML seule comme état de production**.

La production n’est d’ailleurs pas déclarée disponible par le dépôt : `docs/deployment.md:3` indique que la disponibilité de production n’est pas certifiée, et `docs/final-status.md:31` marque la production comme bloquée par plusieurs prérequis BOA. Ces limites doivent rester attachées à toute présentation du résultat.

## 2. Tests : inventaire du code contre preuves d’exécution

### 2.1 Ce qui est réellement comptable dans le dépôt

Les commandes d’inventaire donnent :

| Élément | Compte observable | Nature de la preuve |
|---|---:|---|
| Fichiers unitaires `tests/unit/test_*.py` | 17 | inventaire Git/arborescence |
| Fonctions `def test_...` dans les tests unitaires | 106 | comptage statique du code |
| Fichiers E2E `tests/e2e/*.spec.ts` | 3 | inventaire Git/arborescence |
| Appels `test(...)` Playwright | 8 | comptage statique du code |
| État du dernier run Playwright persistant | `passed`, 0 échec listé | fichier JSON minimal, sans détail |

Commandes reproductibles :

```bash
find tests/unit -maxdepth 1 -name 'test_*.py' | wc -l
rg -n '^\\s*def test_' tests/unit --glob '*.py' | wc -l
find tests/e2e -maxdepth 1 -name '*.spec.ts' | wc -l
rg -n '^\\s*test\\(' tests/e2e --glob '*.ts' | wc -l
cat tests/e2e/test-results/.last-run.json
```

### 2.2 Ce qui n’est pas prouvé

Le fichier `tests/e2e/test-results/.last-run.json` ne contient que :

```json
{
  "status": "passed",
  "failedTests": []
}
```

Il ne permet pas d’identifier le commit testé, l’environnement, la date, le nombre de cas exécutés, les durées ou les captures associées. Le HTML présent dans `tests/e2e/playwright-report/index.html` n’est pas suivi par Git, conformément à `.gitignore` (`playwright-report/`, `test-results/`, `coverage/`). Aucun fichier de couverture, JUnit/XML, rapport de test unitaire ou log complet n’a été trouvé comme artefact versionné. En conséquence, il faut écrire **« comptes de tests présents dans le code »**, et non **« 106 tests unitaires et 8 E2E validés »**.

La documentation `docs/ml-acceptance.md:176` affirme que les contrôles bloquants sont `PASS` et que `E2E-001` à `E2E-009` sont verts. Cette affirmation est documentaire ; elle n’est pas accompagnée dans le dépôt d’un rapport brut permettant de la relier à un commit, un run et des résultats individuels. Le nombre documentaire de neuf contrôles E2E ne doit donc pas être confondu avec les huit appels `test(...)` actuellement comptés dans les fichiers Playwright.

La demande exige aussi des tests de charge reproductibles sur 50 000 PME avec résultats mesurés. Aucun artefact de charge ou de benchmark correspondant n’a été trouvé. Les exigences de performance de Rule Studio décrites dans `docs/rule-studio.md:1190-1191` et les preuves attendues de `docs/rule-studio.md:1294` restent des critères ou des prescriptions, pas des résultats collectés dans ce dépôt.

## 3. Volumes de données et chiffres de validation ML

Le dépôt décrit un jeu synthétique de **500 PME sur 12 mois** (`docs/data-model.md:168-181`) et les scripts utilisent par défaut `PIPELINE_CUSTOMER_COUNT=500` (`scripts/run-pipeline.sh:44-46`, `scripts/local-stack.sh:24`). Le script de validation ML vérifie des seuils SQL d’au moins 500 clients pour les vecteurs de features et les scores (`scripts/validate-ml-integration.sh:35-38`). Ces éléments prouvent la configuration et les assertions prévues ; ils ne constituent pas, en eux-mêmes, un résultat d’exécution collecté dans Git.

Le scénario de démonstration annonce également « 500 PME, 25 CC, 5 agences, 12 mois » (`docs/demo-scenario.md:3-4`) et emploie « 500 PME analysées, 63 correspondances » (`docs/demo-scenario.md:18`). Le texte précise que les résultats doivent venir de l’API et ne pas être inventés, mais aucun export de run, réponse API, date, seed effectivement utilisée ou capture versionnée ne permet de confirmer ici les valeurs `63` ou la distribution `25 CC / 5 agences`. Ces chiffres doivent être qualifiés comme **valeurs annoncées par le scénario ou la configuration**, et non comme mesures collectées pendant cet audit.

Le point important sur les branches est le suivant : le commit de validation ML sur `feat/ml-integration-validation` est bien ancêtre de `main`, mais l’audit ne trouve pas de preuve d’un run effectif de `scripts/validate-ml-integration.sh` sur le `HEAD` courant. Il faut donc distinguer :

1. **Code et assertions de validation présents dans `main` : oui.**
2. **Exécution ML sur 500 PME prouvée par un artefact versionné : non.**
3. **Résultats numériques détaillés d’un run 500 PME : non trouvés.**
4. **Valeurs de scénario comme `63 correspondances` : annoncées, non mesurées dans les preuves disponibles.**

## 4. Documents de pitch, pilote, démonstration et FAQ

### 4.1 Livrables absents

La demande exige un dossier de présentation dans `docs/pitch/`, un plan de pilote, un scénario de démonstration conforme et une FAQ de trente questions. Les vérifications d’existence donnent :

| Livrable requis | État observé | Preuve |
|---|---|---|
| `docs/pitch/` avec note de positionnement, modèle de valeur, architecture cible et comparaison | **Absent** | `find docs -maxdepth 2 -type f`; aucun répertoire `docs/pitch` |
| Plan de pilote dédié | **Absent** | aucun fichier ou répertoire `pilote`/`pilot` dans `docs` |
| FAQ de trente questions | **Absente** | aucun fichier `faq`/`FAQ` dans `docs` |
| `docs/DECISIONS.md` | **Absent** | test d’existence négatif |
| Compte rendu/synthèse consolidée par chantier | **Partiel** | plusieurs statuts techniques existent, mais pas le livrable demandé sous une synthèse unique vérifiable |

Des documents techniques existent (`docs/security.md`, `docs/deployment.md`, `docs/industrialization-governance.md`, `docs/final-status.md` et les documents ML), mais ils ne remplacent pas automatiquement les livrables de discours demandés. Ils ne forment notamment pas la note de positionnement en deux pages, le tableau de valeur marqué « à renseigner par BOA », la comparaison des alternatives, le plan de pilote avec ses critères, ni la FAQ de trente réponses sourcées.

### 4.2 Scénario de démonstration : écart de durée et de structure

`docs/demo-scenario.md:1-4` est explicitement intitulé **« Scénario de démonstration — cinq minutes »** et décrit un bouton « Démo 5 min ». Le scénario comporte une succession d’étapes couvrant le chargé de clientèle, la fiche PME, l’opportunité, l’action, le responsable d’agence, Rule Studio, la simulation, l’approbation et la gouvernance ML (`docs/demo-scenario.md:6-20`). Le guide intégré `frontend/src/features/demo/DemoGuide.tsx` reprend cette trame et mentionne également 500 PME.

L’exigence de `/home/ubuntu/upload/Pasted_content_100.txt:85` demande au contraire un parcours de **quinze minutes en cinq actes**, avec pour chaque acte l’écran, la phrase à dire, la question probable du comité et la réponse, puis une mise à jour du mode démo intégré pour suivre exactement ce scénario. Le dépôt ne contient pas la durée de quinze minutes ni la structure explicite en cinq actes et quatre champs par acte. Le mode démo existe, mais son alignement exact avec le scénario requis n’est pas démontré.

### 4.3 Chiffres et formulation devant la banque

Les documents techniques comportent des limites prudentes : `docs/final-status.md:27-31` positionne le produit comme assistif et non comme décision de crédit, tandis que `docs/finalization-status-2026-09-19.md:8` indique `POC_ASSISTIVE` et l’absence de revendication de performance ML de production. Ces limites sont cohérentes avec l’exigence de ne pas présenter une décision de crédit ou une IA générative comme capacité du produit.

Toutefois, l’absence de `docs/pitch/`, de plan de pilote et de FAQ signifie que le dépôt ne fournit pas le discours bancaire complet demandé. Il faut également éviter de présenter comme mesures les nombres du scénario tant qu’un rapport de run n’est pas conservé.

## 5. Finitions produit demandées pour le pilote

L’exigence de `/home/ubuntu/upload/Pasted_content_100.txt:75` demande un export Excel, une notification quotidienne par courriel avec connecteur SMTP configurable, un écran de paramétrage des libellés, une vérification d’accessibilité et des captures réelles à 1440, 1280 et 1024 pixels.

L’audit textuel trouve des éléments de référence et de responsive design, mais pas les preuves complètes demandées :

- `backend/src/boa_oi/technical/reference.py` contient des libellés d’agence surchargeables par `BRANCH_LABELS_JSON`, mais cela ne prouve pas l’existence d’un écran de paramétrage des agences, secteurs et produits sans passage par la base.
- Les recherches dans le dépôt ne trouvent pas de fonctionnalité ou d’artefact clairement identifié d’export `.xlsx`/Excel pour les opportunités et actions.
- Les recherches ne trouvent pas de notification quotidienne par courriel ni de connecteur SMTP configurable livré avec preuve d’envoi simulé.
- La présence d’attributs ARIA et de dépendances d’accessibilité ne constitue pas une vérification au clavier et au lecteur d’écran. Aucun rapport d’audit d’accessibilité ou scénario dédié n’a été trouvé.
- `tests/e2e/playwright.config.ts` définit une viewport par défaut de 1440×900 et `tests/e2e/rm-opportunity.spec.ts` contient une taille 1024, tandis que `docs/ux-architecture.md:4` mentionne 1440, 1280 et 1024. Cependant, le dépôt ne contient pas un jeu de captures réelles démontrant chaque écran aux trois tailles. La configuration responsive ne doit pas être présentée comme la preuve de la vérification visuelle demandée.

## 6. État des preuves et limites d’interprétation

Les preuves de cet audit sont reproductibles à partir de commandes en lecture seule. Les commandes principales sont :

```bash
git status --short --branch
git branch -a -vv
git log --all --oneline --decorate --graph -40
git merge-base --is-ancestor c658bfc main
git diff --name-status main...feat/ml-integration-validation
find docs -type f -print | sort
find tests/unit -maxdepth 1 -name 'test_*.py' | wc -l
rg -n '^\\s*def test_' tests/unit --glob '*.py' | wc -l
find tests/e2e -maxdepth 1 -name '*.spec.ts' | wc -l
rg -n '^\\s*test\\(' tests/e2e --glob '*.ts' | wc -l
cat tests/e2e/test-results/.last-run.json
git ls-files | grep -Ei '(^|/)(playwright-report|test-results|coverage|reports?|artifacts?|junit|.*\\.xml$)'
```

Aucune commande d’exécution de tests, de stack ou de pipeline n’a été lancée dans le cadre de cet audit en lecture seule. Le rapport ne transforme donc pas une configuration, un script ou une phrase de statut en résultat expérimental. Les éléments non trouvés sont signalés comme **non prouvés par le dépôt audité**, et non comme preuve qu’ils sont nécessairement impossibles dans un environnement externe.

## Synthèse de conformité documentaire

| Domaine demandé | État du dépôt courant | Conclusion d’audit |
|---|---|---|
| Référence Git | `main` propre, `origin/main` alignée | état courant identifiable ; branche ML en retard mais commit ML fusionné |
| Validation ML 500 PME | scripts et assertions présents | exécution et résultats détaillés non prouvés par artefact versionné |
| Tests unitaires/E2E | 106 fonctions unitaires, 8 appels E2E inventoriés | comptes de code, pas preuve complète de collecte |
| Charge 50 000 PME | exigence/documentation de performance | aucun résultat mesuré trouvé |
| Scénario démo | mode démo et document de 5 minutes | écart avec 15 minutes/cinq actes ; chiffres annoncés non corroborés par run |
| Pitch | documents techniques dispersés | `docs/pitch/` absent |
| Pilote | éléments techniques généraux | plan de pilote dédié absent |
| FAQ | aucune FAQ dédiée | livrable de trente questions absent |
| Exports/notifications/libellés | pas de preuve complète des fonctionnalités requises | exigences pilote non démontrées |
| Accessibilité/captures | responsive et quelques marqueurs UI présents | vérification clavier/lecteur d’écran et captures trois résolutions non prouvées |

**Verdict :** le dépôt est auditable et contient les briques techniques et documentaires de base, mais il ne permet pas de soutenir sans qualification que tous les lots de `/home/ubuntu/upload/Pasted_content_100.txt` sont terminés. Les écarts les plus importants pour le discours bancaire sont l’absence des livrables `docs/pitch/`, pilote et FAQ, le scénario de cinq minutes au lieu de quinze, et l’absence d’artefacts de tests permettant de relier les chiffres annoncés à une exécution identifiable.

## Références locales

[1]: /home/ubuntu/upload/Pasted_content_100.txt "Exigences de réalisation et livrables"
[2]: /home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/docs/demo-scenario.md "Scénario de démonstration présent dans le dépôt"
[3]: /home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/docs/ml-acceptance.md "Checklist d’acceptation ML"
[4]: /home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/docs/final-status.md "Statut final technique"
[5]: /home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/scripts/validate-ml-integration.sh "Script de validation de l’intégration ML"
[6]: /home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/tests/e2e/test-results/.last-run.json "État Playwright persistant trouvé dans le dépôt"
[7]: /home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/docs/data-model.md "Dataset synthétique et modèle de données"
[8]: /home/ubuntu/btp-suivi-projets/boa-sme-opportunity-intelligence/docs/deployment.md "Limites de déploiement et de production"

[1] [2] [3] [4] [5] [6] [7] [8]

---

**Note de méthode :** ce fichier est le livrable de l’audit demandé. Il a été ajouté sous `docs/audit/workstreams/`; aucun fichier de code, test, configuration ou document existant n’a été édité.
