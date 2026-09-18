# Scénario de démonstration — cinq minutes

**Statut :** scénario cible ; les résultats affichés doivent être remplacés par les mesures du run réel.

## Préparation

Démarrer la stack locale, appliquer les migrations et charger le seed déterministe. Vérifier au minimum 500 PME, 12 mois de faits synthétiques, comptes, soldes, transactions, produits détenus et règles versionnées. La table des opportunités doit être vide avant le moteur.

## Parcours

| Temps | Action | Preuve attendue |
|---:|---|---|
| 0:00–0:45 | Connexion du RM via Keycloak | Session OIDC et portefeuille autorisé |
| 0:45–1:30 | Ouverture du dashboard | Données provenant de l’API, pagination et filtres |
| 1:30–2:30 | Sélection d’une PME | Customer 360, métriques et signaux visibles |
| 2:30–3:20 | Ouverture d’une opportunité | `WHY`, `WHAT`, `WHEN`, `CONFIDENCE`, preuves et versions |
| 3:20–4:10 | Création d’une action | action canonique, audit et idempotence |
| 4:10–5:00 | Enregistrement d’un outcome | engagement mis à jour, décision moteur inchangée |

## Cas à montrer

Le cas de croissance doit produire `INVESTMENT_FINANCING` lorsque les seuils versionnés sont franchis. Le cas international exige répétition des flux et gap produit avant `TRADE_FINANCE`. L’excédent persistant produit `CASH_INVESTMENT`. La tension est `FINANCIAL_STRESS_SIGNAL`, affichée comme « signal relationnel à examiner », sans langage de risque ni décision de crédit.

Un faux positif saisonnier ou un virement international isolé doit montrer une absence de recommandation expliquée. Une étape non branchée est marquée `TODO` et ne simule pas un succès.

## Références

[1]: ../docs/implementation-blueprint.md "Blueprint d’implémentation exécutable"
[2]: ../docs/business-rules.md "Moteur déterministe d’intelligence d’opportunités"
[3]: ../docs/test-plan.md "Plan de tests"
