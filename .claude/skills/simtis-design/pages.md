# SIMTIS — Spécifications par page

Les données citées sont des **exemples de démonstration**. Affiche toujours les vraies données de l'API.

---

## Tableaux imposés (RÈGLE ABSOLUE)

Ces 3 tableaux suivent **exactement** le classeur `docs/specs/SIMTIS_tableaux_complets.xlsx` (une feuille, les trois tableaux empilés sur les **mêmes colonnes de banques**). Il remplace l'ancienne maquette et la Remarque, dont la règle reste valable : ne change pas les intitulés, n'ajoute ni ne supprime de colonne, ne déplace aucune information, ne les transforme pas en cartes ou en graphiques. Seul le style (tokens, DataTable) s'applique.

**Style commun des 3 tableaux** (décision du 03/10/2026 : « comme les autres tableaux ») : constantes de `components/position/GridCell.tsx`. `GRID_FRAME` = même cadre que `DataTable` (arrondi 12px, bordure `border`, fond `card`, défilement horizontal). `GRID_TABLE` = texte 13,5px normal, traits **horizontaux et verticaux fins** `border` (choix du métier : grilles de montants et de saisie), contour extérieur masqué (`border-hidden`) au profit du cadre, survol `light/40`. `GRID_HEAD` = en-tête de colonne comme `DataTable` (fond `light/60`, texte `primary-dark` semi-gras 13px). `GRID_ROW_HEAD` = libellé de ligne à gauche, `font-medium`. `GRID_GREY` (cellules grisées du classeur) inchangé. Cellules de saisie : hauteur 40px. Disponible Fc reel : ligne séparée, semi-gras sur fond `background`, comme une ligne Total.

```text
            ┌─────────────────────────┬─────┬──────┬────┬─────┬──────┬───────┬─────────────┐
 BANQUES    │ Banque                  │ AWB │ BMCE │ BP │ CIH │ BMCI │ TOTAL │ DEPASSEMENT │
            │ Taux                    │  %                           │       │             │
            │ LIGNE                   │                              │       │             │
            │ facilité de caisse 28/09│                              │       │             │
            │ facilité de caisse 29/09│                              │       │             │
            │ facilité de caisse 30/09│                              │       │             │
            │ Disponible Fc reel      │  vert > 0, autre couleur < 0 │       │             │
            ├─────────────────────────┼──────────────────────────────┼───────┼─────────────┘
 DEVISES    │ EUR                     │  cellules grisées (par banque)│ TOTAL │
            │ USD                     │                              │       │
            │ Exp DH convertible      │                              │       │
            └─────────────────────────┴──────────────────────────────┴───────┘
 PRÉVISIONS ┌────────────┬────────────┬─────┬──────┬────┬─────┬──────┬──────────────┬──────────┬────────┐
            │ 30/09/2026 │ date       │ AWB │ BMCE │ BP │ CIH │ BMCI │ Encaissement │ Escompte │ Douane │
            │ (fusionnée │ (14 lignes)│  montants par banque         │ 1 cellule par ligne (03/10/2026)  │
            │ sur 14 l.) │            │                              │ pour tout le bloc                 │
            └────────────┴────────────┴──────────────────────────────┴───────────────────────────────────┘
```

### Règles communes

- **Colonnes de banques** : AWB · BMCE · BP · CIH · BMCI, dans cet ordre (`banks.ordre_affichage`), affichées par leur **code**. La liste vient de l'API : ne la code pas en dur. L'en-tête de chaque colonne porte le **logo de la banque au-dessus du code** (`<BankLabel layout="stacked">`, validé par le métier le 02/10/2026) : seul l'en-tête gagne une image, aucune colonne ni ligne ne change.
- **Une société à la fois** : ces tableaux se filtrent par société (Simtis ou Société X), jamais de total consolidé des deux.
- Montants alignés à droite, chiffres tabulaires. Police du classeur : 9 pt gras. En-têtes centrés, bordures fines noires.

### Tableau « Banques »

- **Colonnes** : Banque · AWB · BMCE · BP · CIH · BMCI · TOTAL · DEPASSEMENT. Le classeur écrit « AWB » : c'est Attijariwafa.
- **Lignes** :
  - **Taux** : taux d'intérêt, format pourcentage (`0,00 %`).
  - **LIGNE** : crédit autorisé, montants entiers. C'est le libellé du classeur : ne le remplace pas par « Crédit autorisé ».
  - **facilité de caisse** : un libellé fixe et une **date** par ligne (format `jj/mm/aa`). Le classeur en montre 3 (28/09, 29/09, 30/09), mais c'est **une ligne par jour, sans limite** (décision du 02/10/2026) : chaque jour ajoute sa ligne. Valeur = Solde du jour + LIGNE, calculée par l'API ; DEPASSEMENT de la ligne = TOTAL − TOTAL des LIGNES. Ce sont des données, pas un libellé en dur.
  - Affichage : les 10 derniers jours visibles, au-dessus « N derniers jours sur M » et un bouton ghost « Afficher N jours plus anciens » (`ChevronUp`) ; une valeur reprise d'un jour précédent est en `text-simtis-muted` avec l'infobulle « dernier solde connu : JJ/MM/AAAA » ; sans aucun solde : « Aucun solde enregistré pour cette société. ». Carte « Banques » (icône `Landmark`), en premier sur `/position-bancaire`, lecture seule (`components/position/BanquesTable.tsx`).
  - **Disponible Fc reel** : ligne **séparée** sous le tableau. Formule (décision du 03/10/2026, calculée par l'API) : facilité de caisse du dernier jour − LIGNE ; TOTAL = somme ; DEPASSEMENT = TOTAL (la LIGNE est déjà retirée). Mise en forme conditionnelle : vert quand la valeur est > 0, une autre couleur quand elle est < 0, y compris sur TOTAL et DEPASSEMENT. Utilise les tokens de statut (`success` / `danger`), pas le vert du classeur.
- **TOTAL** et **DEPASSEMENT** sont des colonnes calculées par l'API, jamais par l'interface.

### Tableau « Devises »

- **Lignes** : EUR · USD · Exp DH convertible (le classeur écrit « EUR », pas « UAR »).
- **Colonnes** : les mêmes colonnes de banques, **cellules grisées** (fond gris clair), et TOTAL et DEPASSEMENT à droite. Sous cette forme, le tableau n'a aucune autre colonne.
- Les montants restent dans leur devise. **Ne fais jamais de somme entre devises différentes.**
- **Contenu (décision du 05/10/2026)** : lignes **EUR** et **USD** en lecture seule = solde du compte EUR / USD de chaque banque à la date choisie, **dans sa devise, sans conversion** (« 217 500 EUR »), calculé par l'API (`GET /api/position/devises/soldes`) ; un solde repris d'un jour précédent est en `text-simtis-muted` avec l'infobulle « dernier solde connu : JJ/MM/AAAA » ; « - » sans compte ni solde ; TOTAL = somme de la devise (API) ; DEPASSEMENT vide. La ligne **Exp DH convertible** reste saisie à la main (seule ligne à cellules modifiables, bouton « Enregistrer »).
- **Société sans compte EUR, USD ni DH convertible** (Tefil) : la carte Devises n'est pas affichée du tout (`affiche: false`).

### Tableau « Prévisions »

- **Colonne Date** : **une seule**, à gauche, verticale, fusionnée sur toutes les lignes du bloc (`rowSpan`). Ne crée jamais une colonne par date.
- **Colonne suivante** : date au format `jj/mm/aa`, gras, alignée à gauche (une par ligne).
- **Colonnes de banques** : montants par banque et par ligne, mêmes colonnes que le tableau Banques.
- **Encaissement · Escompte · Douane** : trois colonnes, en-têtes sur fond gris clair, montants sans banque. Depuis le 03/10/2026 (décision du métier), **une cellule par ligne** (14 par colonne, libellé lecteur d'écran « Ligne N Encaissement »), comme les colonnes de banques ; avant, une cellule fusionnée pour toute la journée.
- Le sens de chaque flux (entrée ou sortie) est porté par la prévision elle-même, pas déduit de la colonne.

## Logos des banques (tous les tableaux)

Partout où un tableau nomme une banque, son vrai logo s'affiche à côté du code avec le composant `components/banks/BankLabel.tsx` : 20 px, fond blanc, bordure fine, image décorative (`alt=""`, le code écrit nomme la banque). « inline » dans les cellules (Comptes, historique et opérations des Relevés), « stacked » dans les en-têtes de colonnes (tableaux imposés). Une banque sans logo : le code seul, sans icône de remplacement. Les logos viennent de la liste des banques (`bank.logo`, ou `bank_logo` des comptes) ; ne recrée jamais un logo. Pas de logo dans les listes déroulantes natives ni dans les exports Excel.

## Dashboard (`/dashboard`) — voir `reference-dashboard.png`

1. **PageHeader** : « Dashboard » + « Vue d'ensemble de la position bancaire, du rapprochement et des prévisions » ; à droite, `DateRangePicker` (icône `Calendar`, ex. `01/09/2026 - 30/09/2026`).
2. **4 KpiCards** : Total soldes bancaires · Crédit disponible · Position disponible · Opérations rapprochées (avec donut %).
3. Rangée 2 (≈ 2/3 + 1/3) : **Position bancaire par banque** (Banque, Solde bancaire, Crédit autorisé, Crédit utilisé, Crédit disponible, Position disponible + ligne Total ; logo de banque devant le nom) | **Répartition des soldes** (donut).
4. Rangée 3 : **Transactions récentes** (Date, Banque, Libellé, Débit, Crédit, Solde ; « - » pour les valeurs vides) | **Statut du rapprochement** (donut + légende nombre et %).
5. Rangée 4 : **Prévisions de trésorerie** (barres + ligne sur 10 jours) | **Écarts à traiter** (Date, Banque, Libellé, Montant, Statut en badge).

Chaque carte a un lien « Voir tout → » vers sa page.

## Banques (`/banques`)

« Banques » / « Gestion des banques et comptes bancaires ». Grille de **BankCard** : logo ou icône, nom, nombre de comptes, solde, crédit disponible, position disponible (du compte courant MAD de la société active), autres comptes listés chacun dans sa devise, dernière mise à jour, lien « Voir le détail → ».

**Détail (`/banques/[id]`)** : lien retour « ← Banques », logo et nom, DataTable des comptes de la société active (Compte, Devise, LIGNE, Solde, Crédit utilisé, Crédit disponible, Position disponible, Mis à jour, Statut, action « Saisir le solde »), puis historique des soldes sur 30 jours avec un sélecteur de compte. Un montant inconnu s'affiche « - », jamais 0.

## Comptes (`/comptes`)

DataTable des comptes + FilterBar (Banque, Devise, Statut) + bouton primaire « + Nouveau compte ».

## Position bancaire (`/position-bancaire`)

**Aujourd'hui (saisie manuelle)** : un sélecteur de date dans le PageHeader, puis les tableaux imposés **Devises** et **Prévisions** de la société active, saisis cellule par cellule (`components/position/`). Chaque cellule est un champ sans bordure ; en lecture seule (sans `banks.manage` pour Devises, sans `forecasts.manage` pour Prévisions) elle affiche le texte seul. Un bouton « Enregistrer » et « Annuler » par tableau. Les colonnes de droite des Devises portent les en-têtes du classeur (TOTAL, DEPASSEMENT) mais sont saisies, jamais calculées. Les en-têtes de banques sont répétés au-dessus de chaque tableau, puisque le tableau Banques n'est pas encore sur la page.

**Cible (P8)** :

- FilterBar : Banque · Compte · Devise · Date · Période.
- DataTable : Banque · Compte · Devise · Solde · Crédit autorisé · Crédit utilisé · Crédit disponible · Position disponible · Dépassement · Date de mise à jour.
- Graphique d'évolution de la position : carte « Évolution de la position » (icône `TrendingUp`) sous la carte Banques (`components/position/PositionChart.tsx`, Recharts). Courbe en aire, trait 2 px `chart-1`, remplissage `light`, grille horizontale pointillée `border`, axes en `muted` ; TOTAL « facilité de caisse » des 30 derniers jours jusqu'à la date choisie ; sous-titre « TOTAL facilité de caisse, N derniers jours (DH) » ; infobulle date + montant exact ; ligne de zéro seulement si une valeur est négative ; un jour sans TOTAL = vide dans la courbe. Pas de légende (une seule série). Au-dessus, boutons **TOTAL | AWB | BP…** (`BankLabel`, banques qui ont un compte courant MAD ; actif : bordure `primary`, fond `light`, `aria-pressed`) : une courbe à la fois (décision du 03/10/2026), sous-titre « Facilité de caisse AWB, N derniers jours (DH) ». Pas de tableau Détail par compte ni de filtres (P8.2 abandonnée le 03/10/2026).
- Tableau imposé **Banques** (voir plus haut).

## Relevés (`/releves`)

- « Relevés bancaires » + bouton primaire « + Importer un relevé » (seulement avec `statements.import`), qui ouvre la carte « Importer un relevé » au-dessus de l'historique.
- Zone glisser-déposer : bordure pointillée `--simtis-border`, fond `--simtis-background`, « Glissez votre fichier Excel ici » / « ou » / bouton « Choisir un fichier » (`.xlsx` seulement, décision §3.3 : pas de CSV). Au survol ou au dépôt : bordure `--simtis-primary`, fond `--simtis-light`.
- À côté : « Compte du relevé », liste déroulante maison `AccountPicker` (comptes actifs de la société active), **chaque compte avec le logo de sa banque** (« logo AWB · MAD · Compte DÉMO »), le compte choisi aussi ; clavier : flèches, Début, Fin, Entrée, Échap.
- Stepper : **Fichier → Validation** (étape faite : rond teal coché ; en cours : anneau teal). Pas de bouton « Analyser » : dès que le compte et le fichier sont choisis, l'analyse se lance et mène **directement à la Validation** (décision métier du 02/10/2026).
- Mapping **seulement en secours** : si les colonnes ne sont pas reconnues, l'étape Fichier affiche l'encadré « Colonnes non reconnues » (bordure warning, fond `background`) : alerte warning listant ce qui manque, tableau « Colonne fichier (lettre + en-tête) · Exemples · Champ SIMTIS (select, « Ignorer cette colonne ») », bouton « Valider les colonnes ». La correspondance est mémorisée pour la banque : le relevé suivant de cette banque va directement à la Validation.
- Validation = **le relevé tel qu'il sera enregistré, modifiable** (`EditablePreview`) : 4 tuiles (Lignes à importer success, Lignes en erreur danger, Doublons warning, Lignes ignorées muted), période, totaux, soldes (mention « ligne SOLDE INITIAL du fichier » sous un solde lu sur une telle ligne), alerte warning si les mouvements ne retrouvent pas le solde de clôture ; tableau Importer (case) · État (badge Valide / Erreur / Doublon + « ligne N » + « corrigée » en `primary`) · Société · Pointage (« Automatique » si déduit à l'enregistrement) · Banque (`BankLabel`) · Date d'opération · Date de valeur · Libellé (+ référence) · Débit · Crédit · Solde · Lettrage / Escompte · Commentaire · crayon `PenLine`. En édition, la ligne prend un fond `light/40` et des champs (`DateInput`, `NumberInput`, `TextInput`, `Select`), avec `Check` « Terminer » et `RotateCcw` « Annuler les corrections » ; les motifs s'affichent sous la ligne (danger). **Aucun bouton d'ajout.** Le conteneur défilant du tableau est `relative` (sinon un texte `sr-only` élargit la page). Boutons : secondaire « Changer de fichier », primaire « Confirmer l'import » désactivé tant qu'une ligne cochée est en erreur, qu'aucune n'est cochée ou que le fichier est déjà importé.
- Après l'import : bandeau résultat (bordure gauche success), puis le relevé du compte importé.
- Carte « Relevés par compte » : **un seul relevé continu par compte**, chaque import s'y ajoute (jamais un tableau par fichier). En haut, un bouton par compte qui a des imports, **sur une seule ligne** (jamais de retour à la ligne : faute de place, la rangée défile horizontalement dans la carte) ; chaque bouton : `BankLabel` « CIH · MAD », numéro du compte dessous en `text-xs` muted ; actif : bordure `primary`, fond `light` ; filtre Du / Au (« Tout l'historique » pour l'effacer) ; bouton secondaire « Exporter » (icône `Download`, suit la période) ; résumé (Période · Opérations · Total débit / crédit · Solde d'ouverture · Solde de clôture en `primary`) ; tableau au **format standard** : Société · Pointage · Banque · Date d'opération · Date de valeur · Libellé · Débit · Crédit · Solde · Lettrage / Escompte · Commentaire (cet ordre, ne pas le changer), puis Statut (badge). Sous le libellé d'une opération corrigée avant l'import : « corrigée avant l'import » (`text-xs text-simtis-primary`). Avec `statements.import` seulement, colonne Actions : crayon `PenLine` qui ouvre la fenêtre « Modifier l'opération du JJ/MM/AAAA » (`FormModal`) : rappel en lecture (libellé, débit, crédit), puis Pointage (`Select`, « Aucun »), Lettrage / Escompte (120 caractères), Commentaire.
- Le tableau du relevé n'affiche que les **50 dernières opérations** (`OPERATIONS_AFFICHEES`, `showLast` dans `lib/statements.ts`), toujours dans l'ordre des dates : au-dessus du tableau, « 50 dernières opérations sur 312 » (`text-simtis-muted`) et le bouton `ghost` « Afficher 50 opérations plus anciennes » (icône `ChevronUp`, le nombre suit ce qui reste), qui ajoute les lignes en haut. Changer de compte, de période ou importer revient aux 50 dernières. Le résumé et l'export portent toujours sur tout le relevé ou la période.
- Carte « Journal des imports » en dessous, lecture seule : Importé le + auteur · Compte · Fichier · Période · Opérations ajoutées · Solde de clôture · Contrôle du solde (badge). Pas d'action par fichier. Seuls les **10 derniers imports** s'affichent (`IMPORTS_AFFICHES`, `showFirst`) : sous le tableau, « 10 derniers imports sur 24 » et le bouton `ghost` « Afficher 10 de plus » (icône `ChevronDown`).

## Écritures comptables (`/ecritures`)

Réalisé en P10 (`components/ecritures/`), société active, lecture seule (Sage reste la référence) :
- En-tête « Écritures comptables », bouton primaire « Importer un export Sage » (`accounting.import`).
- Carte « Importer un export Sage » : `ImportStepper` Fichier → Validation, `FileDropzone`, analyse automatique, mapping de secours « Colonnes non reconnues » ; Validation : tuiles (Lignes à importer · En erreur · En double · Ignorées · Total débit / crédit · Période), répartition par compte (`BankLabel` « AWB · BQ1 »), DataTable en lecture seule (État + motifs · Date · Journal · Compte bancaire · Compte · N° pièce · Libellé · Débit · Crédit · Échéance · Tiers), case « Garder la ligne N » sur un doublon interne, case « Écarter les lignes en erreur », « Changer de fichier » / « Confirmer l'import ». Erreur « Renseignez le journal Sage… » avec un lien vers `/comptes`.
- Encadré de résultat (bordure gauche `success`) : écritures ajoutées, par compte, écartées, colonnes mémorisées.
- Carte « Écritures » (icône `BookText`) : boutons de compte (« Tous les comptes » + `BankLabel` « BP · TFBQ », une ligne qui défile), Du / Au, Statut, Recherche (soumise par « Rechercher » ou Entrée), « Effacer les filtres » ; résumé Écritures · Total débit · Total crédit (sur tout le filtre) ; DataTable Date · Journal · Compte bancaire · N° pièce · Libellé (+ Réf.) · Débit · Crédit · Échéance · Tiers · Statut (badge) · Détail (icône `Eye`) ; 50 par page, « Page N sur M » + « Précédent » / « Suivant ».
- Fenêtre « Écriture du JJ/MM/AAAA » : tous les champs + fichier d'origine, date d'import, auteur ; aucun champ modifiable.
- Carte « Journal des imports » : 10 derniers + « Afficher N de plus ».

Écran Comptes : champ « Journal Sage » (facultatif, majuscules, 10 lettres ou chiffres) dans le formulaire, colonne « Journal Sage » dans le tableau.

## Rapprochement (`/rapprochement`)

```text
┌─ Transactions bancaires ─┐  ┌─ Correspondance ─┐  ┌─ Écritures comptables ──────────┐
│ Date Libellé Débit Crédit│  │ Transaction      │  │ Date Libellé Débit Crédit       │
│ ☐ ...                    │  │ 50 000 DH        │  │ N° pièce Échéance               │
│ ☐ ...                    │  │      ↕  Score 92 │  │ ☐ ...                           │
│                          │  │ Écriture         │  │                                 │
│                          │  │ 50 000 DH        │  │                                 │
│                          │  │ [Valider le      │  │                                 │
│                          │  │  rapprochement]  │  │                                 │
│                          │  │ [Rejeter]        │  │                                 │
└──────────────────────────┘  └──────────────────┘  └─────────────────────────────────┘
```

Filtres, recherche, statut, pagination, sélection multiple des deux côtés, somme sélectionnée et écart restant visibles. Ligne sélectionnée : `bg-simtis-light`.

Réalisé en P11 (06/10/2026, 1→1 seulement ; la sélection multiple viendra en P13) :
- PageHeader + bouton « Lancer le rapprochement » (icône `Play`). Carte de filtres : boutons de compte (`AccountButton` d'`EntriesCard`, logo + « BP · journal »), Du / Au ; résumé Rapprochées · À vérifier · Non rapprochées · Propositions en attente ; bouton secondaire « Valider les fortes correspondances (N) » (`CheckCheck`) avec fenêtre de confirmation.
- Grille `xl:grid-cols-[1fr_minmax(300px,360px)_1fr]`, empilée en dessous ; panneau central `xl:sticky`.
- Panneau « Correspondance » (`GitCompareArrows`) : blocs Transaction / Écriture sur fond `simtis-background`, montant en 20px `primary-dark` + sens (« crédit », « débit Sage »), `ScoreBadge` (success si forte, warning sinon), détail des 5 critères, boutons pleine largeur Valider (primaire) · Rejeter (secondaire) · Choisir une autre écriture (ghost) ; Annuler le rapprochement (motif obligatoire) ; bloc « Rapprochement manuel » sur `simtis-light/40` avec écart restant (success à 0, danger sinon).

## Écarts (`/ecarts`)

- 4 KPI : Écarts à traiter · Écarts en cours · Écarts clôturés · Montant total.
- DataTable des écarts avec badges.
- Clic sur une ligne : panneau latéral avec Type, Transaction bancaire, Écriture comptable, Montant, Différence, Commentaire, Responsable, Statut.

## Prévisions et Devises : pas de page dédiée

Les pages `/previsions` et `/devises` ont été **supprimées le 05/10/2026** (décision du métier : pas besoin). Les tableaux imposés **Prévisions** et **Devises** sont sur `/position-bancaire`, sous le tableau Banques. Ce qui était prévu pour ces pages (KPI de prévisions, bouton « + Nouvelle prévision », graphique combiné, filtres) se fera, si le métier le demande, sur `/position-bancaire`. Ne recrée pas ces routes sans demande.

## Rapports (`/rapports`) · Administration (`/administration`)

Mêmes composants : PageHeader, cartes, DataTable, FilterBar, Modal. Aucun style spécifique.
