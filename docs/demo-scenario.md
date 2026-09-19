# Scénario de démonstration — cinq minutes

**Statut :** parcours intégré au produit (bouton « Démo 5 min », mode sans Keycloak) et rejoué par les tests E2E.
**Préparation :** `scripts/local-stack.sh up` (ou la stack Docker + `scripts/run-pipeline.sh`) puis `scripts/local-stack.sh rules` pour créer les règles Rule Studio en brouillon. Environnement clairement identifié comme démonstration, données synthétiques (500 PME, 25 CC, 5 agences, 12 mois).

| Temps | Écran | Action | Message à dire | Valeur démontrée |
|---:|---|---|---|---|
| 0:00 | Connexion | Choisir la persona **Ahmed Mansouri** (CC, Casablanca Anfa) | « Ahmed ouvre son cockpit. » | RBAC : périmètre limité au portefeuille du CC. |
| 0:20 | Dashboard CC | Lire les 4 KPI (65 clients, 39 opportunités, 19 priorités, actions) | « Combien de PME je gère, combien présentent un signal, lesquelles regarder aujourd'hui. » | Lecture en 5 secondes, pas de recherche. |
| 0:45 | Priorités du jour | Survoler une ligne : signaux chiffrés, propension, produit potentiel | « Chaque ligne est une carte d'information. » | Le produit présente le pourquoi. |
| 1:05 | Fiche PME | Cliquer sur la première PME ; changer la période 30 j → 12 mois | « Voici ce qui change dans son activité : encaissements +86 %, fournisseurs +340 %. » | Transition fluide, contexte conservé, séries réelles agrégées par SQL. |
| 1:45 | Pourquoi cette opportunité ? | Lire la chaîne signaux → règle → ML → opportunité | « Rien n'est une boîte noire : règle SME_INVESTMENT_001 v1, moteur 0.1.0, propension 92 %. » | Explicabilité et versions. |
| 2:15 | Drawer opportunité | Cliquer « Voir l'opportunité », ouvrir un signal et son évolution | « Valeur observée contre seuil, baseline sur 12 mois. » | Évidence datée. |
| 2:35 | Propension | Cliquer sur le score 92 % | « Facteurs, contribution, modèle, date de mise à jour. » | ML explicable, POC assistif. |
| 2:50 | Action | Choisir « À contacter », enregistrer, revenir au dashboard | « L'action est enregistrée et auditée ; le compteur Actions à traiter passe de 0 à 1. » | Boucle de feedback réelle (API). |
| 3:20 | Dashboard agence | Persona **Salma Berrada** ; cliquer un CC, puis une PME | « Salma pilote son agence : opportunités par CC, secteur, produit, résultats. » | Drill-down complet. |
| 4:00 | Rule Studio | Persona **Youssef Tazi** ; ouvrir SME_INVESTMENT_001, Modifier, changer +25 % → +30 %, enregistrer | « SI encaissements +30 % ET fournisseurs +20 % ALORS financement d'investissement. » | Règles sans code, versionnées. |
| 4:25 | Simulation | Valider, lancer la simulation, lire l'impact, soumettre | « 500 PME analysées, 63 correspondances : impact par secteur et région. » | Résultats de l'API, jamais inventés. |
| 4:45 | Approbation | Persona **Nadia Ouazzani** ; approuver, publier ; onglet Versions & audit | « Un auteur ne peut pas approuver sa propre règle ; tout est audité. » | Séparation des tâches, publication gouvernée. |
| 5:00 | ML Governance | Ouvrir le registre : version active, seuil, coefficients | « Le modèle complète les règles ; il ne décide pas du crédit. » | Gouvernance ML. |

## Cas à montrer

- Croissance (scénario `GROWTH_COMPANY`) → `INVESTMENT_FINANCING` avec trois signaux confirmés.
- International (`INTERNATIONAL_GROWTH`) → `TRADE_FINANCE`.
- Excédent persistant (`CASH_SURPLUS`) → `CASH_INVESTMENT`.
- Tension (`FINANCIAL_STRESS`) → « signal de tension financière », affiché comme signal relationnel, sans langage de risque.
- Faux positifs (`FALSE_POSITIVE_SEASONAL`, `FALSE_POSITIVE_ONE_OFF`) → aucune opportunité, message explicite sur la fiche.

## Références

[1]: ./ux-architecture.md "Architecture UX"
[2]: ./business-rules.md "Moteur déterministe d’intelligence d’opportunités"
[3]: ../tests/e2e "Parcours E2E Playwright"

## Vidéo de démonstration

`scripts/record-demo.cjs` rejoue le parcours ci-dessus dans un Chromium piloté par Playwright (curseur visible, sous-titres injectés dans la page, 1440×900) et produit un fichier `.webm` par acte dans `.local-stack/video/`. Assemblage : convertir chaque segment en H.264 (`ffmpeg -i acteN.webm -c:v libx264 -crf 20 -pix_fmt yuv420p segN.mp4`), ajouter les cartons de titre et de fin, puis concaténer avec le demuxer `concat`. La base doit être dans l'état initial (aucune action commerciale, règles `RULE-*` de test supprimées) pour que le compteur « Actions à traiter » passe bien de 0 à 1.
