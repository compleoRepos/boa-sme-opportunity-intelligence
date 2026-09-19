# Revue visuelle des preuves responsive

**Date :** 19 septembre 2026
**Données :** synthétiques, environnement pilote local
**Nature des images :** captures du viewport exact, sans assemblage full-page

## Dashboard CC — viewport 1 440 × 900 px

La vue affiche sans collision la navigation latérale, l’identité du portefeuille, les quatre indicateurs clés, les filtres de priorisation, la liste de clients et les repères d’usage. Les zones d’action et l’export Excel restent visibles dans le premier écran. Les contrastes renforcés conservent une hiérarchie cohérente avec l’identité bancaire. **Verdict visuel : PASS.**

## Dashboard agence — viewport 1 024 × 768 px

La vue consolidée agence présente sans chevauchement les quatre indicateurs clés et le début du tableau des chargés de clientèle. Le bouton d’export, l’état de consolidation et les colonnes principales restent lisibles. La navigation latérale demeure exploitable à cette largeur. **Verdict visuel : PASS.**

## Fiche PME — viewport 390 × 844 px

La fiche tient dans les 390 pixels sans débordement du document. La liste de priorités, l’identité client, les badges, la propension et les deux actions principales refluent correctement. Le début de la section de santé reste visible sous la carte principale, ce qui confirme une progression verticale naturelle. Le menu desktop est remplacé par son déclencheur mobile et aucun élément actif n’est tronqué latéralement. **Verdict visuel : PASS.**

## Conclusion

Les trois captures viewport exactes sont **PASS** sur la lisibilité, le reflow et l’absence de collision manifeste. La campagne Playwright complète cette revue par des assertions sur la largeur du document et sur tout élément actif qui dépasserait à gauche ou à droite, sauf lorsqu’il est contenu dans un scroller horizontal explicite.
