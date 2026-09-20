# Runbook — Sauvegarde et restauration PostgreSQL

**Auteur :** Manus AI
**Statut :** procédure locale prouvée; dispositif pilote/production à concevoir avec BOA

## 1. Décision opérationnelle

Le dépôt fournit un protocole exécutable de **sauvegarde logique puis restauration isolée**. Il crée deux bases temporaires PostgreSQL, applique les migrations, écrit un marqueur synthétique, produit un dump au format custom, vérifie son empreinte, restaure dans une autre base et compare l’inventaire restauré. Le protocole détecte aussi l’altération d’une copie du dump avant toute restauration.[1]

Cette procédure ne constitue pas une stratégie de continuité bancaire. Le dump temporaire n’est pas chiffré et est supprimé en fin de run. Aucun stockage indépendant, coffre de clés, calendrier, rétention, immutabilité, réplication, archivage WAL ou reprise point-in-time n’est livré. Les objectifs RPO et RTO restent **À VALIDER AVEC BOA**.

## 2. Exécuter la preuve locale

La stack locale doit utiliser uniquement des données synthétiques. L’opérateur exécute :

```bash
./scripts/validate-backup-restore.sh
```

Le script échoue au premier contrôle non satisfait. Il nettoie les deux bases temporaires même en cas d’erreur. La preuve JSON est écrite dans `docs/evidence/backup/RESULTATS-BACKUP-RESTORE.json`; son empreinte publiée se trouve dans le même répertoire.[1] [2]

Un PASS exige un dump non vide, un catalogue `pg_restore --list` lisible, un checksum stable, la détection d’une copie altérée, une restauration avec `--exit-on-error`, la même version Alembic, les mêmes nombres de schémas, tables, index et contraintes, ainsi que le même marqueur synthétique.

## 3. Réagir à un échec

Si le dump échoue, l’opérateur conserve le code retour, les versions PostgreSQL et client, l’espace disponible et les logs sans copier de secrets. Il ne supprime pas la base source. Si le checksum ne correspond pas au manifeste, le fichier est rejeté et ne doit jamais être restauré. Si `pg_restore` échoue, la base cible isolée est détruite puis recréée avant une nouvelle tentative; aucune restauration partielle n’est promue.

Si les inventaires diffèrent, le résultat reste **FAIL**. Une différence de nombre d’objets, de version Alembic ou de marqueur n’est jamais masquée par une mise à jour du seuil. La cause doit être qualifiée : dump incomplet, droits, extensions, incompatibilité de version, migration divergente ou altération du fichier.

## 4. Procédure cible à faire approuver

Avant tout pilote connecté à des données BOA, les responsables désignés doivent définir le périmètre sauvegardé, la fréquence, les objectifs RPO/RTO, la rétention, le chiffrement, l’emplacement indépendant, l’accès, l’immutabilité et la destruction. Ils doivent aussi définir la reprise de Keycloak, des secrets, certificats, images et configurations. Ces décisions ne sont pas déduites de la preuve locale.

Chaque exercice cible doit restaurer vers un environnement isolé et comparable, puis exécuter les migrations, contrôles de permissions, requêtes de fumée et vérifications d’intégrité. Les durées doivent être mesurées et comparées uniquement aux objectifs préalablement approuvés. Une restauration PostgreSQL seule ne suffit pas à déclarer le service repris.

## 5. Preuve finale locale

Le run `backup-restore-20260920T051333Z-2646494` sur PostgreSQL 16.15 et le backend Python 3.12 Alpine a produit un dump de 179 470 octets et 360 entrées de catalogue. Les durées observées sont 344 ms pour le dump, 753 ms pour la restauration et 988 ms pour les vérifications. La base restaurée contient la migration `0017_ml_shadow_governance`, 16 schémas, 65 tables, 176 index et 216 contraintes. Le protocole prouve aussi l’absence des noms temporaires avant création, leur absence après nettoyage et l’immutabilité de la base sentinelle `boa_sme`. Ces mesures décrivent uniquement le sandbox local synthétique; elles ne sont ni un RPO, ni un RTO, ni une capacité de production.[1]

## Références

[1]: ../evidence/backup/RESULTATS-BACKUP-RESTORE.json "Résultats locaux du cycle backup et restauration PostgreSQL"
[2]: ../evidence/backup/SHA256SUMS.txt "Empreinte SHA-256 de la preuve backup et restauration"
