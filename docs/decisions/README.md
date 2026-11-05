# Décisions par module

Le détail de chaque décision métier (date, migration, fonctions, routes, écrans, volumes mesurés), un fichier par module. `CLAUDE.md` ne garde que l'état général et les règles qui traversent les modules.

Ces textes ont été déplacés tels quels depuis `CLAUDE.md` le 04/11/2026, en anglais et dans l'ordre où les décisions ont été prises : un paragraphe plus récent peut en remplacer un plus ancien (chercher « replaces », « since »).

| Fichier | Contenu |
|---|---|
| [position-bancaire.md](position-bancaire.md) | Tableaux Banques, Prévisions (lignes datées, formules), Devises (EUR / USD en lecture), graphique « Évolution de la position » |
| [releves.md](releves.md) | Import des relevés : pointage (74 catégories), sens par le solde, lignes SOLDE AU, relevé continu par compte, aperçu modifiable, `.xls`, gros fichiers, abréviations d'en-têtes, relevés sans solde, PDF, libellés BP collés |
| [operations-en-cours.md](operations-en-cours.md) | Opérations « (*) », fichiers d'opérations en cours séparés, suppression à la main, complément AWB, règle de solde |
| [ecritures-sage.md](ecritures-sage.md) | Import Sage (P10), journaux par compte, solde comptable, plusieurs comptes comptables, reprise des échéances |
| [saisies-suppressions-reprises.md](saisies-suppressions-reprises.md) | Opérations et écritures manuelles, suppression d'un import, reprise d'un état de rapprochement Excel (BP, BMCE) |
| [rapprochement-moteur.md](rapprochement-moteur.md) | Moteur (P11) : grille de score, types d'opération, devises, impayés, groupes N → 1, rapprochements manuels, codes, vitesse, recherche élargie, dates par type, Espèces, montant identique obligatoire |
| [rapprochement-ecran.md](rapprochement-ecran.md) | Écran `/rapprochement` : volets, filtres dans les en-têtes, propositions, ambiguës, actions en lot, relance ciblée, plein écran |
| [frais-bancaires.md](frais-bancaires.md) | Timbres, commissions, FRAIS avec TVA, frais à la main, seuil 200 DH, export Sage (CSV), N° pièce, « À comptabiliser » |
| [ecarts.md](ecarts.md) | Écarts (P12), construits puis mis de côté le 07/10/2026 |
| [comptes.md](comptes.md) | Écran Comptes : cartes `/banques`, comptes désactivés, suppression d'un compte sans historique |
| [dashboard.md](dashboard.md) | Dashboard (P15) : maquette, deux onglets, filtre banque, style |
| [administration-rapports.md](administration-rapports.md) | Administration (P16) : utilisateurs, rôles, permissions par personne, historique, paramètres, modèles de colonnes, rapports Excel et PDF |

Quand une décision est prise ou modifiée : l'écrire à la fin du fichier du module, en disant ce qu'elle remplace.
