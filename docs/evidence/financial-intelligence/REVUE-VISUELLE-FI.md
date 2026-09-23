# Revue visuelle — Financial Intelligence

**Révision fonctionnelle :** `9c8edc1f09ce7e545c71856ce430b1e2d89dd73d`
**Périmètre :** données synthétiques, non-production, aucune décision de crédit.

| Capture | Dimensions | Verdict | Constats |
|---|---:|---|---|
| `FI-PORTFOLIOS-FONDS-A-1440x900.png` | 1440 × 900 | **PASS** | Le catalogue autorisé est lisible. Le bandeau affiche `DETERMINISTIC_RULES`, `ML GOVERNANCE NOT_APPLICABLE`, `ML MODE NOT ATTESTED` et des poids non fournis. Cette absence d’attestation est correcte : le catalogue ne consulte pas Portfolio Service pour une société. |
| `FI-PORTFOLIO-FUND-001-1440x900.png` | 1440 × 900 | **PASS** | Le portfolio affiche les KPI backend et atteste `ML GOVERNANCE VERIFIED`, `POC_SHADOW`, `rulesWeight=1` et `mlWeight=0`. La série temporelle non disponible est distinctement rendue `NOT IMPLEMENTED — BLOCKED`. |
| `FI-COMPANY-SME-00001-1440x900.png` | 1440 × 900 | **PASS** | Le nom synthétique, l’identifiant, le Fund, le Portfolio et `asOf` sont visibles. La gouvernance ML vérifiée et `NO_CREDIT_DECISION` sont explicites. Les capacités sans agrégat propriétaire restent bloquées sans valeur inventée ; aucun IBAN, compte ou mouvement brut n’est affiché. |
| `FI-COMPANY-SME-00001-390x844.png` | 390 × 844 | **PASS** | Le titre, le contexte d’autorisation, `NO_CREDIT_DECISION`, la gouvernance ML et les premières métriques restent lisibles sans débordement horizontal. Le contenu se réorganise en une colonne sans masquer les garde-fous. |

## Verdict

Les quatre captures régénérées satisfont la revue visuelle du POC et concordent avec la sémantique fail-closed introduite par les corrections P1. Elles prouvent le rendu de ces parcours connectés au backend, pas une homologation ergonomique, accessibilité ou métier BOA. Les libellés anglais encore présents dans certains titres techniques et la longueur de la fiche société demeurent une **HYPOTHÈSE À VALIDER AVEC BOA**.
