# SIMTIS — Spécifications par page

Les données citées sont des **exemples de démonstration**. Affiche toujours les vraies données de l'API.

---

## Tableaux imposés (RÈGLE ABSOLUE)

Ces 3 tableaux suivent **exactement** la maquette Excel (`docs/specs/SIMTIS_3_tableaux_corriges(1).xlsx`).
Ne change pas les intitulés, n'ajoute ni ne supprime de colonne, ne déplace aucune information, ne les transforme pas en cartes ou en graphiques. Seul le style (tokens, DataTable) s'applique.

### Tableau « Banques » (page Position bancaire / Banques)

```text
┌─────────────────┬─────┬──────────────┬──────┬────┬────────┬─────────────┐
│ Banque          │ CIH │ Attijariwafa │ BMCE │ BP │ Totale │ Dépassement │
├─────────────────┼─────┼──────────────┼──────┼────┼────────┼─────────────┤
│ Taux            │     │              │      │    │        │             │
│ Crédit autorisé │     │              │      │    │        │             │
│ Date            │     │              │      │    │        │             │
└─────────────────┼─────┴──────────────┴──────┴────┴────────┼─────────────┘
                  │           Disposition FC réel           │
                  └─────────────────────────────────────────┘
```

- Colonnes : Banque · CIH · Attijariwafa · BMCE · BP · Totale · Dépassement. La maquette Excel écrit « Tijari » : le métier a confirmé « Attijariwafa ».
- Lignes : Taux · Crédit autorisé · Date.
  - **Taux** = taux d'intérêt.
  - **Crédit autorisé** remplace « Linge » de la maquette (= « Ligne » = crédit autorisé, confirmé par le métier). Libellé provisoire, en attendant le nom définitif : ne le change pas sans confirmation.
  - **Date** = date de mise à jour (une seule).
- **« Disposition FC réel »** : ligne placée **sous** le tableau, cellule fusionnée qui s'étend sous les colonnes bancaires (CIH → Totale, comme la fusion `B5:F5` de l'Excel). Formule : Solde bancaire + Crédit autorisé.

### Tableau « Devises »

```text
┌───────────────────┐
│ EUR               │
│ USD               │
│ Ex rh convertible │
└───────────────────┘
```

- Uniquement ces 3 lignes. Aucune colonne ni information supplémentaire.
- La maquette écrit « UAR » : le métier a confirmé qu'il s'agit d'EUR, afficher « EUR ».
- La structure complète (où s'affichent les montants) sera précisée par les tableaux complets que l'équipe doit envoyer.

### Tableau « Prévisions »

```text
┌────────┬──────────────────────┬──────────────┬──────────┬────────┐
│ Date   │ Libellé              │ Encaissement │ Escompte │ Douane │
├────────┼──────────────────────┼──────────────┼──────────┼────────┤
│        │ Encaissement 24/09   │              │          │        │
│        │ Encaissement 25/09   │              │          │        │
│ (une   │ Encaissement 29/09   │              │          │        │
│ seule  │ La paie              │              │          │        │
│ cellule│ Refinancement        │              │          │        │
│ fusion-│ Douane               │              │          │        │
│ née)   │ CHQ1                 │              │          │        │
│        │ CHQ2                 │              │          │        │
│        │ CHQ3                 │              │          │        │
└────────┴──────────────────────┴──────────────┴──────────┴────────┘
```

- **Une seule colonne Date**, verticale à gauche, fusionnée sur toutes les lignes (`rowSpan`). Ne crée jamais une colonne par date.
- Colonnes de montants : Encaissement · Escompte · Douane.

---

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
