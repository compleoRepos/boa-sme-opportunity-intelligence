# Architecture UX — BOA SME Opportunity Intelligence

**Statut :** implémentée (frontend React 19 + Vite, branché exclusivement sur le Gateway `/api/v1`)
**Cible :** desktop 1440 × 900 en priorité, puis laptop (1280) et tablette (1024).

## 1. Concept central : « Mon portefeuille PME »

Le chargé de clientèle (CC) ouvre l'application et comprend en cinq secondes : combien de PME il gère, combien présentent un signal, lesquelles regarder aujourd'hui, pourquoi, quelle opportunité, que faire. Le produit présente l'information, il ne la fait pas chercher.

L'expérience est un **cockpit unique** : le dashboard, la fiche PME, l'opportunité et le score de propension s'enchaînent sans page blanche. La fiche PME s'ouvre dans la même scène avec le rail des priorités conservé à gauche ; l'opportunité et la propension s'ouvrent dans des panneaux latéraux (drawers) adressables par l'URL (`?opportunite=…`, `?panneau=propension`), donc partageables et compatibles avec le bouton Retour.

## 2. Navigation et rôles

| Rôle (OIDC) | Accueil `/` | Écrans |
|---|---|---|
| `RELATIONSHIP_MANAGER` | Dashboard CC | `/clients/:id` (fiche PME + drawers), `/clients`, `/actions` |
| `BRANCH_MANAGER` | Dashboard agence | `/agence/cc/:rmId` (portefeuille d'un CC) → `/clients/:id?cc=…` → opportunité |
| `BUSINESS_ANALYST`, `RULE_APPROVER`, `ADMIN`, `DATA_ANALYST` | Back office `/back-office` | `regles` (Rule Studio), `regles/:id`, `regles/:id/modifier`, `regles/nouvelle`, `simulations`, `modeles` (ML Governance), `audit`, `opportunites`, `produits`, `seuils` (ADMIN) |

Les anciennes routes (`/rule-studio/*`, `/administration`, `/opportunites/:id`) redirigent vers les nouvelles ; `/opportunites/:id` ouvre la fiche PME avec le drawer d'opportunité.

## 3. Les cinq écrans prioritaires

1. **Dashboard CC** : en-tête (« Bonjour Ahmed · Agence Casablanca Anfa · 65 clients »), quatre KPI cliquables qui filtrent la file (Clients PME, Opportunités, Priorités du jour, Actions à traiter), file « À regarder aujourd'hui » dont chaque ligne est une carte d'information (secteur, agence, type d'opportunité, date de détection, trois signaux chiffrés, produit potentiel, propension, prochaine action), distribution des priorités.
2. **Fiche PME** : en-tête identité + propension (anneau cliquable) + opportunité principale + action ; « Santé de la relation » (activité, encaissements, fournisseurs, décaissements, international, trésorerie, avec sparklines 12 mois) ; « Activité » (flux / volume / international sur 30 j, 90 j, 6 mois, 12 mois, série agrégée par le transaction-service) ; « Pourquoi cette opportunité ? » ; grille d'action commerciale ; onglets historique / comptes & produits / transactions / signaux.
3. **Pourquoi cette opportunité ?** : chaîne d'évidence numérotée — signaux (valeur, seuil, période, sévérité) → règle métier (identifiant, version, conditions satisfaites, seuils, version moteur) → propension ML (modèle, features) → opportunité (produits, horizon, confiance). Chaque nœud est cliquable : signal → drawer avec évolution mensuelle et baseline ; ML → drawer propension ; opportunité → drawer opportunité. Vocabulaire : signal détecté, règle déclenchée, propension, score, évidence, période d'observation, opportunité, priorité, produit potentiel. Jamais « l'IA recommande ».
4. **Dashboard agence** : KPI, tableau des CC (cliquable), opportunités par type / secteur / produit / CC, distribution des priorités, évolution des générations, actions et outcomes, entonnoir de conversion. Drill-down : agence → CC → portefeuille → PME → opportunité.
5. **Rule Studio + simulation** : lecture métier en blocs SI / ET / OU / NON / ALORS ; builder à tokens éditables (métrique, opérateur, valeur, unité, période, poids, groupes imbriqués) ; cycle de vie en stepper (brouillon → validée → simulée → soumise → approuvée → publiée → active) ; simulation avec état de progression puis résultats réels de l'API (population, correspondances, confiance, impact par secteur / région / segment, top PME) ; revue avant soumission (version actuelle, nouvelle version, impact estimé) ; séparation des tâches (l'auteur ne peut pas approuver).

Écrans complémentaires : drawer propension (facteurs en barres divergentes, combinaison ML + règles, modèle / version / date), Model Registry (registre, seuil, métriques, coefficients, cycle de vie, rollback signalé comme non exposé par l'API), simulations (historique persisté), audit (règles + actions).

## 4. Design system

Fichiers : `frontend/src/styles/{tokens,base,components,layout,screens}.css` et composants `frontend/src/ui/*`.

- **Couleurs** : navy 950/900/800 (marque), bleu 600 (action), neutres froids, sémantique (vert, ambre, rouge, violet, teal), priorités P1..P4. Aucun dégradé décoratif, pas d'ombres lourdes.
- **Palette graphique** validée avec le script `dataviz` (bande de luminosité, chroma, séparation daltonienne, contraste) : `#1f5fd0`, `#c97a0c`, `#0e8a5f`, `#8b5cf6`, `#c0392b`, `#0e9bb0`. La couleur suit l'entité (encaissements = vert, décaissements = ambre, volume = bleu, international = teal, fournisseurs = violet), jamais le rang.
- **Typographie** : Inter / système, 14 px de base, chiffres tabulaires, échelle 11 → 40 px.
- **Composants** : Button (6 variantes, 3 tailles, état chargement), Badge (tons + priorité), Panel, Kpi (accent latéral, icône, note, cliquable), Ring (anneau de score), Delta, Tabs / Segmented, Drawer, Modal, Toast, Tooltip, Skeleton, EmptyState / NoResults / ErrorState (avec correlationId), Stepper, Timeline, Chain, Rule blocks, tables denses.
- **États** : chargement (skeletons, jamais de page blanche ni de spinner permanent), vide, erreur (message normalisé + référence de corrélation + réessayer), succès (toast discret « Action enregistrée »).

## 5. Micro-interactions (utiles, jamais gratuites)

Transitions de vue 180–260 ms (`cubic-bezier(0.16, 1, 0.3, 1)`), apparition en cascade des lignes de priorité et des nœuds de la chaîne, drawer glissant, modal montante, toast glissant, hover discret sur cartes et lignes, chiffres KPI animés (count-up 520 ms), skeleton shimmer, tabs et segments fluides, tooltips riches. `prefers-reduced-motion` désactive toutes les durées.

## 6. Performance et données

- TanStack Query : `staleTime` 45 s, cache 10 min, pas de refetch au focus ; les dashboards sont invalidés après chaque action commerciale, donc le retour au dashboard est instantané et à jour.
- Navigation dashboard → fiche : le rail réutilise le cache du dashboard ; la fiche affiche des skeletons par section pendant les appels parallèles (client, propension, opportunités, métriques, comptes, produits, signaux, actions, activité).
- Aucune donnée métier codée en dur : noms de produits, seuils, règles, versions, périodes et dates de référence proviennent des services (la date d'observation vient des métriques ; la période de simulation par défaut vient de la dernière exécution moteur).
- Découpage des bundles : react, query, charts, auth.

## 7. Accessibilité

Contrastes ≥ 4,5:1 sur le texte, focus visible, navigation clavier (lignes de tableau focusables, `Escape` ferme drawers et modals), rôles ARIA (dialog, tablist, status, alert, group), libellés sur toutes les commandes, tailles de texte ≥ 11 px pour les métadonnées, états d'erreur et de chargement annoncés.

## 8. Mode démonstration

Sans Keycloak (`VITE_AUTH_DISABLED=true` et `BOA_AUTH_DISABLED=true`), l'écran de connexion propose quatre personas (CC, responsable d'agence, approbatrice, back office) rejouées contre le Gateway réel via le header `X-Dev-Principal` (ignoré dès que l'OIDC est actif). Le bouton « Démo 5 min » lance un parcours guidé de dix étapes (message à dire, valeur démontrée, action), qui change de persona et navigue réellement dans le produit. Voir `docs/demo-scenario.md`.
