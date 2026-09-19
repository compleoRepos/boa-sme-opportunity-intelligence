# Lot 07 — Accessibilité clavier, WCAG automatisée et responsive

**Date de validation :** 19 septembre 2026
**Branche :** `feat/pilot-readiness`
**Auteur :** Manus AI
**Verdict :** **PASS technique**, avec validation manuelle par lecteur d’écran restant à organiser pendant le pilote

## Conclusion

Le cockpit est désormais utilisable au clavier sur les parcours contrôlés et ne présente aucune violation axe de niveau WCAG A ou AA dans les vues testées. Les dialogues Modal et Drawer piègent le focus, ferment avec Échap et restaurent le focus au déclencheur. Une pile explicite garantit qu’Échap ne ferme que le dialogue imbriqué supérieur. Les onglets suivent le modèle clavier attendu avec les flèches, Home et End. Le menu mobile est borné au clavier et un lien d’évitement donne un accès direct au contenu principal.

La campagne responsive couvre des viewports exacts de 1 440 × 900 px pour le dashboard CC, 1 024 × 768 px pour le dashboard agence et 390 × 844 px pour la fiche PME. Le défaut de débordement horizontal découvert sur la fiche mobile a été corrigé. Les groupes d’onglets ou de périodes qui dépassent la largeur restent défilables dans leur propre conteneur sans élargir le document. Les info-bulles mobiles sont ancrées dans le viewport.

Ce lot **ne suffit pas à revendiquer une conformité WCAG 2.1 AA complète**. L’automatisation ne remplace pas une revue manuelle avec NVDA, JAWS ou VoiceOver. Cette validation manuelle est donc classée **NON IMPLÉMENTÉE dans le sandbox** et doit être inscrite au protocole pilote.

## Périmètre corrigé

### Dialogues et annonces

Modal et Drawer sont rendus dans des portails, avec `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, un focus initial déterministe, un focus trap et une restauration du focus. Le sous-arbre applicatif est rendu inerte pendant l’ouverture. Le live region des notifications Toast est lui aussi portalisé dans `document.body`, ce qui permet aux annonces de rester disponibles lorsque le fond applicatif est inerte.

### Navigation clavier

Les onglets utilisent un `tabindex` itinérant. Les flèches gauche et droite déplacent la sélection, tandis que Home et End atteignent les extrémités. Le menu mobile piège temporairement le focus, se ferme avec Échap et restaure le focus sur son bouton d’ouverture. Le lien « Aller au contenu principal » devient visible au focus.

### Contrastes et reflow

Les couleurs de textes secondaires, badges, en-têtes latéraux et accents ont été renforcées après une première passe axe. Le scan final ne détecte aucune violation sur les dashboards CC et agence, le drawer Opportunity et le back office. Les panneaux peuvent désormais rétrécir sous leur largeur intrinsèque, les identités et actions de la fiche PME refluent sur petit écran, et les info-bulles ne créent plus de largeur latente.

## Contre-revue indépendante

Une première contre-revue a classé **CHANGES_REQUIRED** quatre écarts P1 : dialogue parent encore exposé lors d’une imbrication, contrôle Toast extérieur au périmètre modal, fond du menu mobile non inerte et preuve responsive qui ne vérifiait pas sa liste d’éléments débordants. Les quatre écarts ont été corrigés. Les dialogues inférieurs deviennent `inert` et `aria-hidden`, tout focus extérieur est ramené dans le dialogue supérieur, les boutons Toast sont retirés du parcours Tab, et le menu mobile isole le contenu principal. La preuve responsive échoue désormais pour tout élément actif dépassant à gauche ou à droite, sauf scroller horizontal explicite ou sous-arbre inerte. Les liaisons `tab`–`tabpanel` ont également été complétées sur tous les usages produit.

Une seconde contre-revue a encore identifié deux P1 résiduels : le lien d’évitement et les portails hors du contenu principal n’étaient pas couverts par l’isolation propre au menu mobile. Le menu réutilise désormais le même gestionnaire modal centralisé que les drawers et modales : pile de couches, garde `focusin`, neutralisation des Toasts existants et futurs, classe modale globale, verrouillage du scroll, isolation du lien d’évitement et restauration du focus. Le scrim est décoratif et non focusable ; la fermeture reste disponible par le bouton explicite et par Échap.

La troisième contre-revue a rendu un verdict **PASS sans P0/P1**. Son unique remarque P2 portait sur la restauration du `tabindex` d’un Toast créé pendant l’ouverture d’une couche. Ce cas a également été corrigé et couvert : lorsque la dernière couche se ferme, les Toasts dynamiques retrouvent leur contrôle de fermeture dans le parcours clavier.

## Résultats reproductibles

| Contrôle | Résultat | Preuve |
|---|---:|---|
| Ruff format | **PASS** | 130 fichiers conformes |
| Ruff lint | **PASS** | aucune erreur |
| mypy | **PASS** | 78 fichiers source sans erreur |
| Tests backend | **PASS** | 220 tests, 6 avertissements connus |
| ShellCheck et validation Compose/Keycloak | **PASS** | scripts et configuration valides |
| TypeScript | **PASS** | `tsc -b` |
| Tests frontend | **PASS** | 25 tests, dont 5 tests dédiés aux primitives accessibles |
| Build Vite | **PASS** | bundle de production généré |
| E2E Playwright | **PASS** | 19 scénarios |
| axe WCAG A/AA | **PASS** | 0 violation sur CC, agence, drawer et administration |
| Navigation clavier mobile | **PASS** | menu borné, Échap, restauration et lien d’évitement |
| Reflow fiche PME 390 px | **PASS** | largeur réelle 390 px, aucun débordement du document |
| Captures responsive | **PASS** | trois PNG aux dimensions exactes, versionnés avec empreintes SHA-256 vérifiées par `sha256sum -c` |
| Test manuel lecteur d’écran | **NON IMPLÉMENTÉ** | à exécuter pendant le pilote sur postes bancaires représentatifs |

## Commandes de reproduction

```bash
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:e2e

ruff format --check backend/src database tests/unit
ruff check backend/src database tests/unit
mypy backend
PYTHONPATH=backend/src:. pytest tests/unit -q --disable-warnings
shellcheck -x -e SC1091 scripts/*.sh
./scripts/validate.sh
```

Les captures sont régénérées par les scénarios intitulés `preuve responsive`. Les scans axe sont exécutés dans `tests/e2e/accessibility.spec.ts`. Le fichier `docs/evidence/accessibility/SHA256SUMS.txt` relie chaque image à son empreinte.

## Limites et suite pilote

La campagne mesure le DOM rendu avec Chromium et axe. Elle ne couvre ni les combinaisons navigateur–lecteur d’écran, ni le grossissement système supérieur à 200 %, ni les préférences de contraste propres aux postes utilisateurs. Le protocole pilote doit prévoir une session manuelle sur au moins un poste Windows avec NVDA et un poste représentatif du parc bancaire. Les constats devront être consignés avec le navigateur, la version du lecteur d’écran, le scénario et le résultat.

Les données visibles dans les captures sont synthétiques. Elles ne constituent aucune preuve de performance commerciale ou de performance ML. Le produit reste un outil POC/shadow d’aide au travail commercial, sans décision de crédit.

## Références

[1]: ../../tests/e2e/accessibility.spec.ts "Campagne Playwright et axe sur les parcours BOA SME Opportunity Intelligence"
[2]: ../../tests/e2e/responsive-captures.spec.ts "Captures responsive reproductibles"
[3]: ../evidence/accessibility/REVUE-VISUELLE.md "Revue visuelle des captures responsive"
[4]: https://www.w3.org/WAI/WCAG21/quickref/ "How to Meet WCAG 2.1"
