# SIMTIS — Spécifications par page

Les données citées sont des **exemples de démonstration**. Affiche toujours les vraies données de l'API.

---

## Tableaux imposés (RÈGLE ABSOLUE)

Ces 3 tableaux suivent **exactement** le classeur `docs/specs/SIMTIS_tableaux_complets.xlsx` (une feuille, les trois tableaux empilés sur les **mêmes colonnes de banques**). Il remplace l'ancienne maquette et la Remarque, dont la règle reste valable : ne change pas les intitulés, n'ajoute ni ne supprime de colonne, ne déplace aucune information, ne les transforme pas en cartes ou en graphiques. Seul le style (tokens, DataTable) s'applique.

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
            │ (fusionnée │ (14 lignes)│  montants par banque         │ 1 cellule fusionnée par colonne   │
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
  - **facilité de caisse** ×3 : un libellé fixe et une **date** par ligne (28/09, 29/09, 30/09 dans le classeur, format `jj/mm/aa`). Ce sont des données par jour, pas un libellé en dur. La définition exacte (solde du jour ou facilité utilisée) reste à confirmer : affiche ce que l'API renvoie.
  - **Disponible Fc reel** : ligne **séparée** sous le tableau. Formule : Solde bancaire + LIGNE. Mise en forme conditionnelle : vert quand la valeur est > 0, une autre couleur quand elle est < 0, y compris sur TOTAL et DEPASSEMENT. Utilise les tokens de statut (`success` / `danger`), pas le vert du classeur.
- **TOTAL** et **DEPASSEMENT** sont des colonnes calculées par l'API, jamais par l'interface.

### Tableau « Devises »

- **Lignes** : EUR · USD · Exp DH convertible (le classeur écrit « EUR », pas « UAR »).
- **Colonnes** : les mêmes colonnes de banques, **cellules grisées** (fond gris clair), et TOTAL et DEPASSEMENT à droite. Sous cette forme, le tableau n'a aucune autre colonne.
- Les montants restent dans leur devise. **Ne fais jamais de somme entre devises différentes.** Ce que contiennent exactement les cellules grisées et le TOTAL reste à confirmer : affiche ce que l'API renvoie et n'invente aucun calcul.
- Le détail (taux, équivalent MAD, date du taux) s'ouvre en infobulle ou en vue détail, sans changer le tableau.

### Tableau « Prévisions »

- **Colonne Date** : **une seule**, à gauche, verticale, fusionnée sur toutes les lignes du bloc (`rowSpan`). Ne crée jamais une colonne par date.
- **Colonne suivante** : date au format `jj/mm/aa`, gras, alignée à gauche (une par ligne).
- **Colonnes de banques** : montants par banque et par ligne, mêmes colonnes que le tableau Banques.
- **Encaissement · Escompte · Douane** : trois colonnes, chacune avec **une cellule fusionnée sur tout le bloc**, en-têtes sur fond gris clair. Ce sont des montants de la journée, sans banque.
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
- Graphique d'évolution de la position.
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

DataTable : Date · Journal · Compte · Libellé · Référence · Débit · Crédit · N° pièce · Échéance · Tiers · Statut (badge). Filtres + recherche.

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

## Écarts (`/ecarts`)

- 4 KPI : Écarts à traiter · Écarts en cours · Écarts clôturés · Montant total.
- DataTable des écarts avec badges.
- Clic sur une ligne : panneau latéral avec Type, Transaction bancaire, Écriture comptable, Montant, Différence, Commentaire, Responsable, Statut.

## Prévisions (`/previsions`)

- 4 KPI : Position actuelle · Encaissements prévus · Décaissements prévus · Position future.
- Bouton primaire « + Nouvelle prévision ».
- Tableau imposé **Prévisions** (voir plus haut).
- Graphique combiné encaissements / décaissements / position prévisionnelle.

## Devises (`/devises`)

- FilterBar : Banque · Compte · Devise · Date.
- Tableau imposé **Devises** (voir plus haut).

## Rapports (`/rapports`) · Administration (`/administration`)

Mêmes composants : PageHeader, cartes, DataTable, FilterBar, Modal. Aucun style spécifique.
