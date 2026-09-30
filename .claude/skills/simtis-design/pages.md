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

- **Colonnes de banques** : AWB · BMCE · BP · CIH · BMCI, dans cet ordre (`banks.ordre_affichage`), affichées par leur **code**. La liste vient de l'API : ne la code pas en dur.
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

## Dashboard (`/dashboard`) — voir `reference-dashboard.png`

1. **PageHeader** : « Dashboard » + « Vue d'ensemble de la position bancaire, du rapprochement et des prévisions » ; à droite, `DateRangePicker` (icône `Calendar`, ex. `01/09/2026 - 30/09/2026`).
2. **4 KpiCards** : Total soldes bancaires · Crédit disponible · Position disponible · Opérations rapprochées (avec donut %).
3. Rangée 2 (≈ 2/3 + 1/3) : **Position bancaire par banque** (Banque, Solde bancaire, Crédit autorisé, Crédit utilisé, Crédit disponible, Position disponible + ligne Total ; logo de banque devant le nom) | **Répartition des soldes** (donut).
4. Rangée 3 : **Transactions récentes** (Date, Banque, Libellé, Débit, Crédit, Solde ; « - » pour les valeurs vides) | **Statut du rapprochement** (donut + légende nombre et %).
5. Rangée 4 : **Prévisions de trésorerie** (barres + ligne sur 10 jours) | **Écarts à traiter** (Date, Banque, Libellé, Montant, Statut en badge).

Chaque carte a un lien « Voir tout → » vers sa page.

## Banques (`/banques`)

« Banques » / « Gestion des banques et comptes bancaires ». Grille de **BankCard** : logo ou icône, nom, nombre de comptes, solde, crédit disponible, position disponible, dernière mise à jour.

## Comptes (`/comptes`)

DataTable des comptes + FilterBar (Banque, Devise, Statut) + bouton primaire « + Nouveau compte ».

## Position bancaire (`/position-bancaire`)

- FilterBar : Banque · Compte · Devise · Date · Période.
- DataTable : Banque · Compte · Devise · Solde · Crédit autorisé · Crédit utilisé · Crédit disponible · Position disponible · Dépassement · Date de mise à jour.
- Graphique d'évolution de la position.
- Tableau imposé **Banques** (voir plus haut).

## Relevés (`/releves`)

- « Relevés bancaires » + bouton primaire « + Importer un relevé ».
- Zone glisser-déposer : bordure pointillée `--simtis-border`, fond `--simtis-background`, « Glissez votre fichier Excel ou CSV ici » / « ou » / bouton « Choisir un fichier ». Au survol ou au dépôt : bordure `--simtis-primary`, fond `--simtis-light`.
- Après l'upload, stepper : **Détection des colonnes → Mapping → Validation**. Le mapping s'affiche en lignes « Colonne fichier (ex. Date opération) → Champ SIMTIS (select : Date d'opération) ».
- Résumé : lignes valides (success), en erreur (danger), doublons (warning).

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
