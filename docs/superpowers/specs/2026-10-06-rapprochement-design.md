# P11 — Rapprochement bancaire 1→1

Date : 06/10/2026 · Statut : réalisé · Phase du plan : P11

## But

Proposer automatiquement des correspondances 1→1 entre les opérations bancaires (P7) et les écritures Sage (P10) d'une société, puis les faire **valider par un utilisateur autorisé**. Le moteur ne valide jamais seul.

Hors périmètre : écarts (P12), correspondances 1→N, N→1, N→N (P13), écran d'administration de la grille (P16).

## Décisions (06/10/2026, à confirmer par Mustapha)

1. La grille et les seuils du plan servent de départ ; ils sont enregistrés dans `reconciliation_rules` et se modifient en base sans toucher au code.
2. Une proposition met l'opération et l'écriture en « À vérifier » ; elles ne passent « Rapprochée » qu'après la validation d'un utilisateur, même pour un score ≥ 90.
3. Le rapprochement manuel 1→1 exige le même montant, en sens opposé. Un écart de montant relève des écarts (P12).

## Règles du moteur (`services/reconciliation_scoring.py`, fonctions pures en `Decimal`)

**Paires comparées** : même compte bancaire (celui du journal Sage de l'écriture), même société, **sens opposés** (montant de l'opération = − montant de l'écriture : un crédit en banque est un débit du compte banque dans Sage, P10), dates à ± 10 jours (`FENETRE`). Les écritures sont rangées par jour : chaque opération ne parcourt que les jours de sa fenêtre.

**Score sur 100**

| Code | Points | Règle |
|---|---|---|
| `REFERENCE` | 40 | Référence ou N° pièce de l'écriture égal à la référence de l'opération ou à celle trouvée dans son libellé ; ou cette clé (3 caractères au moins) écrite dans le libellé ou la référence bancaire, ponctuation ignorée (« REG-458 » contient REG458) |
| `MONTANT` | 30 | Montant exact, sens opposé |
| `DATE` | 15 | Plus petit écart avec la date d'opération ou de valeur ; tolérance 3 jours : 15 · 11,25 · 7,5 · 3,75 · 0 |
| `LIBELLE` | 10 | 10 × max(mots significatifs communs / mots du plus court libellé, similarité des caractères) ; mots vides ignorés (VIR, REG, CHQ, FACTURE…) |
| `TIERS` | 5 | Le tiers de l'écriture figure dans le libellé bancaire |

**Seuils** : `SEUIL_PROPOSITION` 50 (en dessous, pas un candidat) · `SEUIL_FORT` 90 (« forte correspondance », validable en lot) · `ECART_AMBIGUITE` 10.

**Choix des propositions** : une paire n'est proposée que si elle est le meilleur candidat de son opération **et** de son écriture, avec au moins 10 points d'avance sur le suivant de chaque côté. Les paires retenues sont retirées, puis le choix recommence. Ce qui garde un candidat à la fin est ambigu : « À vérifier », sans proposition. Une paire rejetée par un utilisateur n'est jamais reproposée.

Exemple de l'architecture fonctionnelle : banque 50 000 le 24/09 « VIR ABC » ↔ Sage 50 000 le 24/09 « Règlement ABC », pièce REG458, tiers ABC → 0 + 30 + 15 + 10 + 5 = **60**, proposé « À vérifier ».

## Statuts

| Événement | Correspondance | Opération et écriture |
|---|---|---|
| Proposition du moteur | Proposée | À vérifier |
| Ambiguïté | (aucune) | À vérifier |
| Validation, ou rapprochement manuel | Validée (`valide_par_id`, `valide_le`) | Rapprochée |
| Rejet | Rejetée | Non rapprochée |
| Annulation d'une validée (motif obligatoire) | Annulée | Non rapprochée |

Relancer le moteur sur une période remplace ses propositions automatiques encore « Proposée » (et remet en « Non rapprochée » les « À vérifier » sans correspondance) ; validées, rejetées, annulées et manuelles ne changent jamais. « Écart » est réservé à P12 : le moteur ignore ces lignes.

## Base de données (migration 0011)

- `reconciliation_match_items.actif` : vrai tant que la correspondance est Proposée ou Validée. Index uniques partiels `uq_reconciliation_match_items_transaction_active` et `uq_reconciliation_match_items_ecriture_active` : une opération, ou une écriture, n'est que dans **une** correspondance active.
- `reconciliation_matches.detail_score` (JSONB) : points par critère au moment du calcul.
- Seeds de référence : 9 lignes de `reconciliation_rules` (créées seulement si absentes).

Concurrence : chaque action verrouille la ligne de la société (`SELECT … FOR UPDATE`) ; un conflit restant donne un 409 « rechargez la page ».

## API (`/api/reconciliation`, routeur protégé)

| Endpoint | Permission |
|---|---|
| `POST /run` `{company_id, bank_account_id?, du, au}` (366 jours au plus) | `reconciliation.validate` |
| `GET /transactions?company_id=&bank_account_id=&from=&to=&statut=&q=&page=` (50 par page, `par_statut` sur tout le filtre hors statut, correspondance active de chaque opération) | `reconciliation.view` |
| `GET /proposals?company_id=&statut=Proposée&bank_account_id=&from=&to=` (+ `seuil_fort`) | `reconciliation.view` |
| `GET /matches/{id}` | `reconciliation.view` |
| `GET /candidates?transaction_id=` (20 meilleures écritures du même compte, sens opposé, dans la fenêtre ; drapeaux `rejetee`, `proposee_ailleurs`) | `reconciliation.view` |
| `POST /matches/{id}/validate` · `POST /matches/{id}/reject` `{commentaire?}` | `reconciliation.validate` |
| `POST /matches/validate-batch` `{ids}` (toutes fortes et proposées, sinon 409 et rien n'est validé) | `reconciliation.validate` |
| `POST /matches` `{transaction_id, ecriture_id, commentaire?}` : manuel, validé d'emblée ; rejette les propositions en attente qui contiennent l'une des deux lignes ; 409 si montant différent, même sens, autre compte, autre société, ligne en écart ou déjà rapprochée | `reconciliation.validate` |
| `DELETE /matches/{id}` `{motif}` : annule une validée | `reconciliation.validate` |

Audit : `rapprochement_lance`, `validation_rapprochement`, `rejet_rapprochement`, `rapprochement_manuel`, `annulation_rapprochement`, avec l'état avant / après.

## Écran `/rapprochement`

- En-tête : bouton « Lancer le rapprochement » (si `reconciliation.validate`).
- Carte de filtres : un bouton par compte qui a un journal Sage (+ « Tous les comptes »), Du / Au (du 1er du mois précédent à aujourd'hui par défaut) ; résumé Rapprochées · À vérifier · Non rapprochées · Propositions en attente ; « Valider les fortes correspondances (N) » avec confirmation.
- Trois volets (empilés sous 1280 px) : **Transactions bancaires** (Date, Libellé, Débit, Crédit, Statut ; filtres Statut et Recherche ; 50 par page) | **Correspondance** (transaction, écriture proposée, score, détail des critères, Valider · Rejeter · Choisir une autre écriture · Annuler le rapprochement ; liste des écritures possibles ; rapprochement manuel avec l'écriture sélectionnée à droite et écart restant) | **Écritures comptables** (Date, Libellé, Débit, Crédit, N° pièce, Échéance, Statut).
- Ligne sélectionnée : `bg-simtis-light` (`DataTable` : `onRowClick`, `isRowSelected`).
- Montants manuels comparés en centimes `BigInt` (`lib/reconciliation.ts`), jamais en float.

## Reste à faire

- Faire valider la grille et les seuils par Mustapha.
- Recette sur un mois réel : les données de développement actuelles (100 opérations, 400 écritures synthétiques) n'ont aucun montant commun ; mesurer le taux de propositions correctes.


## Compteurs cliquables et historique (07/10/2026)

Décisions de l'utilisateur du 07/10/2026 : un clic sur un compteur filtre le volet « Transactions bancaires » (pas de fenêtre séparée) ; l'historique montre **toutes** les décisions (validées, rejetées, annulées) ; pas d'export Excel avant P16.

- Compteurs Rapprochées / À vérifier / Non rapprochées : filtre Statut du volet de gauche (second clic : tous les statuts). « Propositions en attente » : fenêtre listant les propositions de la période, la plus forte d'abord ; un clic sélectionne l'opération et sa proposition dans le panneau Correspondance.
- Onglet « Historique » : `GET /api/reconciliation/history?company_id=&bank_account_id=&from=&to=&statut=&page=` (`reconciliation.view`) ; décisions dont l'opération est dans la période, triées par date de décision décroissante, 50 par page ; `par_statut` sur tout le filtre hors statut. Une ligne validée peut être annulée (motif obligatoire).
- Migration 0013 : `reconciliation_matches.decide_par_id` / `decide_le` renseignés par chaque décision (validation, rejet, annulation, rapprochement manuel) ; CHECK `decision_tracee` (toute correspondance non « Proposée » a son auteur et sa date) ; reprise des décisions passées depuis `valide_par_id` / `valide_le`, sinon la dernière trace `rejet_rapprochement` / `annulation_rapprochement` de l'audit.
