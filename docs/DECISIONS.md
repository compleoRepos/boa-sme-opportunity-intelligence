# Journal des décisions

## 19 septembre 2026 — Branche de départ du chantier pilote

**Question.** Le mandat indique que `feat/ux-premium-cockpit` doit être deux commits devant `main`, mais cette branche n’existe pas sur `origin`. Le bundle disponible expose uniquement le commit UX `3e43581`, déjà intégré à `main` par la pull request #2. `main` contient en outre les validations ML, la gouvernance et les correctifs postérieurs.

**Option retenue.** Créer localement `feat/ux-premium-cockpit` comme alias du `main` validé, puis créer `feat/pilot-readiness` depuis cet alias. Cette option conserve toute l’UX Claude sans perdre les validations ML et évite de réintroduire des régressions en repartant d’un commit ancien.

**Alternative si BOA décide autrement.** Rebaser les seuls commits du chantier pilote sur une future branche officielle `feat/ux-premium-cockpit`, puis rejouer toutes les migrations et portes de qualité avant fusion.

**Impact.** Aucun historique existant n’est réécrit. Le point de départ réel et le décalage avec le mandat sont traçables dans l’audit préalable.
