# Audit initial historique — dépôt et documents

> **ARCHIVE — NE PAS UTILISER COMME STATUT COURANT.** Ce document conserve uniquement la photographie du dépôt à la révision `d40ecf6`, observée le 19 septembre 2026. Les compteurs, absences et branches mentionnés dans l’audit initial ont été remplacés par des lots ultérieurs. Le statut courant est porté par [`docs/final-status.md`](../../final-status.md) et le [lot 13 de clôture](../../lots/LOT-13-CLOTURE-PILOTE.md).

## 1. Périmètre historique

L’audit initial a examiné l’historique Git, les branches alors disponibles, les tests présents, les documents de pitch, de démonstration et de pilote, ainsi qu’un cahier d’exigences externe non versionné. La [note de provenance](../SOURCE-NOTE.md) explique pourquoi cette source externe ne constitue pas une preuve durable du dépôt.

Aucun test, pipeline, service Docker ou benchmark n’avait été exécuté dans ce workstream. Les nombres relevés étaient donc des **inventaires statiques du code à `d40ecf6`**, jamais des résultats de test.

## 2. Constats historiques et résolution actuelle

| Sujet | Constat à `d40ecf6` | Résolution ultérieure versionnée |
|---|---|---|
| Tests | 106 fonctions unitaires et 8 appels Playwright inventoriés ; aucun rapport d’exécution complet | 259 tests backend, 27 tests frontend et 20 E2E exécutés dans le lot catalogue ; résultats Playwright détaillés[1] |
| Charge | aucun artefact mesuré 50 000 PME trouvé | protocole isolé et rapport du lot 08[2] |
| Ingestion | gouvernance et qualité non démontrées dans l’audit initial | manifeste, quarantaine, rejouabilité et concurrence prouvés au lot 09[3] |
| ML | scripts présents, mais aucun artefact courant relié au commit audité | ML classique CPU verrouillé en `POC_SHADOW`, priorité `RULES_ONLY`, lot 10[4] |
| Pack bancaire | pitch, plan pilote et FAQ non trouvés | documents de pitch, plan pilote et FAQ de 30 questions désormais versionnés |
| Démonstration | scénario de cinq minutes sans structure demandée | scénario en cinq actes et script d’enregistrement optionnel versionnés |
| Accessibilité et responsive | configuration présente, mais captures et exécution non prouvées | parcours Axe/Playwright et captures versionnées au lot 07 et dans les preuves catalogue |
| Industrialisation | backup, panne DB, scans et gates non prouvés | protocoles et preuves locales du lot 11 ; release toujours `BLOCKED_IMAGE_CVES`[5] |
| Catalogue | aucun référentiel produit public gouverné | 28 produits indicatifs, 7 familles, migration et preuves du lot 12[6] |

Les valeurs historiques `106` et `8`, les branches `main`/`feat/ml-integration-validation` et les absences documentaires ne décrivent donc **pas** `feat/pilot-readiness`. Elles sont conservées uniquement pour expliquer l’origine des lots correctifs.

## 3. Limites méthodologiques conservées

L’audit initial distinguait correctement :

1. un fichier de configuration d’un résultat exécuté ;
2. un compte statique de tests d’un rapport de test ;
3. une valeur de scénario d’une mesure collectée ;
4. un POC synthétique d’une capacité de production ;
5. une intégration locale d’un raccordement aux systèmes BOA réels.

Ces distinctions restent applicables. Les runs locaux actuels ne prouvent ni SLO bancaire, ni performance prédictive de production, ni raccordement au Core Banking, au CRM, au SIEM ou à un relais SMTP BOA.

## 4. Référence courante obligatoire

Toute décision actuelle doit partir des documents et artefacts suivants :

- le [statut final](../../final-status.md) ;
- le [lot 13 de clôture](../../lots/LOT-13-CLOTURE-PILOTE.md) ;
- les artefacts JSON et manifestes sous [`docs/evidence/`](../../evidence/) ;
- le commit réellement publié sur `feat/pilot-readiness` ;
- le verdict réel des runs GitHub Actions cités dans la clôture.

La release reste **NO-GO** tant que `BLOCKED_IMAGE_CVES`, la CI incomplète et les prérequis BOA ne sont pas levés. AWS demeure hors périmètre. Le produit ne prend aucune décision de crédit et le ML ne modifie pas la priorité commerciale.

## Références

[1]: ../../evidence/catalog/RESULTATS-PLAYWRIGHT-CATALOGUE.json "Vingt parcours Playwright détaillés"
[2]: ../../lots/LOT-08-CHARGE-50000.md "Lot 08 — charge 50 000 PME"
[3]: ../../lots/LOT-09-INGESTION-QUALITE.md "Lot 09 — ingestion et qualité"
[4]: ../../lots/LOT-10-ML-SHADOW-DEFENDABLE.md "Lot 10 — ML shadow défendable"
[5]: ../../lots/LOT-11-INDUSTRIALISATION-EXPLOITATION.md "Lot 11 — industrialisation et exploitation"
[6]: ../../lots/LOT-12-CATALOGUE-PRODUITS-BOA.md "Lot 12 — catalogue produit public"
