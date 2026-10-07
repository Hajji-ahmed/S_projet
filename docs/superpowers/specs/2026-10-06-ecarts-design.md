# P12 — Gestion des écarts

> **Mise de côté le 07/10/2026** (décision du métier). Fonction masquée à l'écran par `ECARTS_ACTIFS = false` (`frontend/lib/features.ts`) ; backend, API, base et tests conservés. Migration 0015 (données) : écarts ouverts clôturés (commentaire « Fonction Écarts mise de côté le 07/10/2026. », auteur = premier administrateur actif, audit `cloture_ecart`), lignes « Écart » remises « Non rapprochée ». Réactivation : `ECARTS_ACTIFS = true`.

Date : 06/10/2026. Décisions validées par l'utilisateur le 06/10/2026 (plan présenté avant l'implémentation).

## Objectif

Suivre chaque anomalie du rapprochement jusqu'à sa clôture commentée : chaque ligne non rapprochée a un écart ou un statut explicite, et chaque écart garde son historique complet.

## Règles

### Types et lignes

| Type | Opération | Écriture |
|---|---|---|
| Banque sans écriture | obligatoire | interdite |
| Écriture sans banque | interdite | obligatoire |
| Montant différent | obligatoire | obligatoire (montants qui ne s'équilibrent pas) |
| Date différente | obligatoire | obligatoire |
| Libellé ambigu | obligatoire | facultative |
| Doublon potentiel | une seule ligne, l'une ou l'autre | |

Avec les deux lignes : même société, même compte bancaire. Montant = valeur absolue du montant de l'opération (sinon de l'écriture) ; différence = montant de l'opération + montant de l'écriture (sens de Sage : 0 quand elles s'équilibrent) ; date = date d'opération, sinon date d'écriture. Devise = celle du compte.

### Création

- **Manuelle** (`POST /api/discrepancies`, depuis `/rapprochement`) : refusée si une ligne a déjà un écart ouvert ou fait partie d'un rapprochement validé (à annuler d'abord) ; une proposition en attente qui contient une ligne est rejetée et tracée.
- **Automatique, sur demande** (`POST /api/discrepancies/generate`, société, compte facultatif, période ≤ 366 jours) :
  - Doublon potentiel : opérations du même compte de même date, montant et libellé (normalisé) ; écritures du même compte de même date, montant, libellé et pièce. L'original (la ligne rapprochée, sinon la plus ancienne) n'est pas signalé comme doublon ; les autres le sont s'ils sont « Non rapprochée » ou « À vérifier » sans correspondance active.
  - Banque sans écriture / Écriture sans banque : ligne « Non rapprochée », sans correspondance active, datée au plus tard aujourd'hui − `fenetre_jours` (10, grille du rapprochement).
  - Une ligne qui a déjà eu un écart, même clôturé, n'est jamais signalée de nouveau automatiquement.

### Cycle de vie

À traiter → En cours → Traité, Traité → En cours (reprise). Clôture depuis tout statut ouvert, commentaire obligatoire, auteur et date tracés ; un écart clôturé ne se modifie plus. `traite_le` est posé au passage à Traité (effacé si l'écart revient à En cours, posé à la clôture s'il manquait).

Lignes : écart ouvert → « Écart » (le moteur les ignore) ; clôture → « Non rapprochée » (seulement si elles étaient encore « Écart »).

Le responsable est un utilisateur actif qui a la permission `discrepancies.manage`.

### Correction de P11

Valider une correspondance dont les montants ne s'équilibrent pas est refusé (409) : une proposition peut atteindre 50 points sans le critère Montant ; l'utilisateur signale alors un écart « Montant différent ».

## Base de données

Migration 0012 : `uq_discrepancies_transaction_ouvert` et `uq_discrepancies_ecriture_ouvert`, index uniques partiels (`statut <> 'Clôturé'`) — un seul écart ouvert par ligne. Tests dans `test_constraints.py`.

## API

| Route | Permission |
|---|---|
| `GET /api/discrepancies?company_id=&statut=&type=&responsable_id=&bank_account_id=&from=&to=&q=&page=` | `reconciliation.view` |
| `GET /api/discrepancies/{id}` (lignes, historique lu dans `audit_logs`) | `reconciliation.view` |
| `GET /api/discrepancies/responsables?company_id=` | `reconciliation.view` |
| `POST /api/discrepancies` | `discrepancies.manage` |
| `POST /api/discrepancies/generate` | `discrepancies.manage` |
| `PATCH /api/discrepancies/{id}` (statut hors clôture, responsable, commentaire ; champ absent = inchangé) | `discrepancies.manage` |
| `POST /api/discrepancies/{id}/close` | `discrepancies.manage` |

La liste renvoie 50 écarts par page, du plus récent au plus ancien ; `par_statut` et `montants_ouverts` (par devise, jamais additionnés) portent sur tout le filtre hors statut. `GET /api/reconciliation/transactions` renvoie aussi `ecart_id` (écart ouvert de chaque opération).

Audit : `creation_ecart` (origine Manuelle / Automatique), `generation_ecarts`, `modification_ecart`, `cloture_ecart` ; chaque action verrouille la société, comme le rapprochement.

## Interface

- `/ecarts` : bouton « Générer les écarts », 4 KPI, carte « Écarts » (comptes, filtres, tableau, pagination), panneau latéral de détail et de traitement, lien direct `/ecarts?ecart=ID`.
- `/rapprochement` : « Signaler un écart » dans le panneau Correspondance (type proposé selon la sélection), bandeau avec lien vers l'écart d'une opération en écart.

## Reste à faire

Recette avec Mustapha sur un mois réel : pertinence des écarts générés et de la règle des 10 jours.
