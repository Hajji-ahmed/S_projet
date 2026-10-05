# Tableau Banques calculé (P8.1) — spécification

Date : 03/10/2026. Phase : P8 Position bancaire, première étape. Design validé en deux parties le 03/10/2026.

## But

Remplacer la recopie Excel de Salma pour le tableau **Banques** du classeur `SIMTIS_tableaux_complets.xlsx` : SIMTIS le calcule à partir des soldes du jour déjà enregistrés (saisis à la main ou écrits par l'import d'un relevé). Le tableau est en lecture seule, par société, sur la page `/position-bancaire`.

Hors périmètre (étapes suivantes de P8) : tableau détaillé par compte, filtres Banque / Compte / Devise, graphique d'évolution, comparaison au centime près avec l'Excel de Salma (fichier attendu).

## Décisions métier (02 et 03/10/2026)

| Sujet | Décision |
|---|---|
| Comptes | Le **compte courant MAD actif** de chaque banque, pour la société active. « Exp DH convertible » (type `DH convertible`) et les comptes en devise n'entrent pas dans ce tableau. |
| Banques | Les banques **actives** seulement, dans l'ordre `banks.ordre_affichage` (AWB, BMCE, BP, CIH, BMCI). Une banque désactivée (BMCE pour le moment, à désactiver dans l'écran Banques) n'a pas de colonne. |
| facilité de caisse | Une ligne **par jour calendaire**, week-ends compris, sans limite. Cellule d'une banque = **solde du jour + LIGNE**. |
| Jour sans solde | La banque reprend son **dernier solde connu** (signalé comme repris) ; avant son premier solde, « - ». |
| DEPASSEMENT | Pour chaque ligne : **colonne TOTAL de la ligne − somme des LIGNES des mêmes banques**. |
| Exemple validé | AWB : LIGNE 500 000, solde −200 000 → 300 000. BMCE : LIGNE 300 000, solde +100 000 → 400 000. TOTAL 700 000. DEPASSEMENT 700 000 − 800 000 = **−100 000**. |

## Règles de calcul

Toutes en `Decimal`, dans `backend/app/services/position_service.py` (fonctions pures, sans accès à la base), à côté des formules existantes. Une valeur inconnue reste `None`, jamais 0.

**Colonnes.** Une par banque active, dans l'ordre d'affichage. Pour chaque banque, le compte retenu est son compte de la société avec `type_compte = 'Courant'`, `devise = 'MAD'`, `actif = true` (au plus un, garanti par l'index `uq_bank_accounts_compte_actif_par_banque`). Une banque sans tel compte garde sa colonne, avec « - » partout, et n'entre dans aucun total.

**Lignes, dans cet ordre.**

| Ligne | Cellule d'une banque | TOTAL | DEPASSEMENT |
|---|---|---|---|
| Taux | `taux_interet` du compte, en % (`taux_pct`) ; « - » si absent | vide | vide |
| LIGNE | `credit_autorise` du compte | somme des banques qui ont un compte | vide |
| facilité de caisse JJ/MM/AA (une par jour) | solde retenu ce jour-là + LIGNE | somme des cellules renseignées | TOTAL − somme des LIGNES des banques renseignées ce jour-là |
| Disponible Fc reel | dernier solde connu à la date de fin + LIGNE | somme des cellules renseignées | TOTAL − somme des LIGNES des banques renseignées |

**Solde retenu un jour J pour une banque.** Le solde (`solde` non nul) de la ligne `bank_account_balances` du compte à la date J s'il existe ; sinon le dernier solde non nul d'une date antérieure à J, marqué **repris** avec sa date ; sinon aucun (cellule « - », banque exclue du TOTAL et de la somme des LIGNES de ce jour). Une ligne de solde qui ne porte qu'un crédit utilisé (`solde` nul) ne compte pas.

**Jours.** Du **premier jour** où l'un des comptes retenus a un solde non nul jusqu'à la **date de fin** incluse, chaque jour calendaire. Date de fin = min(date demandée, aujourd'hui au Maroc, `business_today()`). Si aucun compte retenu n'a de solde jusqu'à la date de fin : aucune ligne facilité de caisse, et Disponible Fc reel n'a que des « - » (TOTAL et DEPASSEMENT vides).

**Disponible Fc reel** = les valeurs de la ligne de la date de fin (même solde retenu, même règle de reprise). Formule du CDC : Solde bancaire + LIGNE.

**LIGNE dans le passé.** SIMTIS ne garde pas l'historique de la LIGNE : tous les jours utilisent la LIGNE actuelle du compte. L'interface le signale par une infobulle sur la ligne LIGNE.

**TOTAL vide.** Quand aucune banque n'est renseignée sur une ligne, TOTAL et DEPASSEMENT sont `null` (affichés « - »).

## API

`GET /api/position/banques?company_id=<id>&date=<AAAA-MM-JJ>`

- Routeur `position` existant (`backend/app/api/position.py`), déjà dans `protected_router` ; permission `position.view` (401 sans jeton, 403 sans la permission).
- `date` facultative, aujourd'hui (Maroc) par défaut ; date invalide → 422. Société inconnue → 404 (`NotFoundError`). N'écrit rien en base, pas d'audit (lecture).
- Couches : endpoint mince → `position_service` (construction du tableau) → repository (lecture des banques actives, des comptes courants MAD actifs de la société et de leurs soldes jusqu'à la date de fin) → modèles existants. **Aucune migration.**
- Montants et taux en chaînes exactes (`"300000.00"`), jamais en `float`.

Réponse (schéma Pydantic `BanquesTableOut`) :

```json
{
  "company_id": 1,
  "date_fin": "2026-09-30",
  "banques": [
    { "bank_id": 1, "code": "AWB", "logo": "/banques/attijariwafa.png",
      "bank_account_id": 4, "taux_pct": "5.50", "ligne": "500000.00" }
  ],
  "ligne_total": "800000.00",
  "jours": [
    { "date": "2026-09-30",
      "cellules": [ { "bank_id": 1, "valeur": "300000.00", "date_solde": "2026-09-30", "reprise": false } ],
      "total": "700000.00", "depassement": "-100000.00" }
  ],
  "disponible": {
    "cellules": [ { "bank_id": 1, "valeur": "300000.00", "date_solde": "2026-09-30", "reprise": false } ],
    "total": "700000.00", "depassement": "-100000.00"
  }
}
```

- `banques` : une entrée par banque active, dans l'ordre ; `bank_account_id`, `taux_pct` et `ligne` à `null` sans compte courant MAD actif.
- `jours` : ordre chronologique croissant (le plus ancien d'abord, la date de fin en dernier). `cellules` a une entrée par banque de `banques`, dans le même ordre ; `valeur` et `date_solde` à `null` pour « - ».
- `ligne_total` : `null` si aucune banque n'a de compte.

## Écran

`/position-bancaire` (composant `frontend/components/position/BanquesTable.tsx`, chargé dans `PositionView`), en lecture seule pour tous ceux qui voient la page.

- Carte **« Banques »** (icône Lucide `Landmark`), **en premier**, au-dessus de Devises et Prévisions ; suit la date du haut de page et la société active (`useCompany()`).
- Même grille que les tableaux Devises et Prévisions (`GRID_TABLE`, `GRID_HEAD` de `GridCell.tsx`) ; en-têtes : cellule vide « Banque », puis un `BankLabel` empilé (logo au-dessus du code) par banque, puis TOTAL et DEPASSEMENT. Les colonnes viennent de la réponse de l'API, pas de la liste des banques de la page.
- Lignes : Taux (format `0,00 %`), LIGNE (infobulle « LIGNE actuelle du compte, appliquée à tous les jours »), puis une ligne « facilité de caisse » par jour avec sa date `jj/mm/aa`, la date de fin en bas.
- Les **10 derniers jours** sont visibles ; au-dessus, bouton « Afficher N jours plus anciens » (par 10), comme le relevé continu (`showLast` de `frontend/lib/statements.ts`). Changer de date ou de société revient aux 10 derniers.
- Cellule reprise : texte `text-simtis-muted`, infobulle « dernier solde connu : JJ/MM/AAAA ». Valeur inconnue : « - », jamais 0.
- **Disponible Fc reel** : ligne séparée sous le tableau, mêmes colonnes ; texte `text-simtis-success` si la valeur est > 0, `text-simtis-danger` si < 0, y compris TOTAL et DEPASSEMENT.
- Montants alignés à droite, `tabular-nums`, `formatAmount()` (jamais tronqués). Le tableau défile horizontalement dans la carte sur mobile ; la page ne déborde pas.
- États : `LoadingState`, `ErrorState` avec « Réessayer », et sans aucun solde : Taux et LIGNE affichés, puis le message « Aucun solde enregistré pour cette société. ».
- Description de la page : « Tableau Banques calculé ; Devises et Prévisions saisis à la main ».
- Appels via `apiFetch` dans `frontend/services/position.ts` ; types dans `frontend/types/position.ts`. L'interface ne calcule ni TOTAL ni DEPASSEMENT.

## Tests (écrits avant le code)

Backend, fonctions pures (`tests/test_position_service.py`) :
- l'exemple validé (300 000 / 400 000 / 700 000 / −100 000) ;
- l'exemple du CDC : solde 300 000, autorisé 500 000, utilisé 100 000 → crédit disponible 400 000, position disponible 700 000 ;
- reprise du dernier solde connu, avec sa date et `reprise = true` ;
- banque sans solde avant son premier solde : « - », exclue du TOTAL et de la somme des LIGNES de ce jour ;
- les week-ends ont leur ligne ; jours du premier solde à la date de fin, sans trou ;
- une ligne de solde sans `solde` (crédit utilisé seul) ne compte pas ;
- Disponible Fc reel = ligne de la date de fin ; TOTAL vide quand rien n'est renseigné ;
- aucun résultat de type `float`.

Backend, API (`tests/test_position_banques_api.py`) :
- un compte `DH convertible`, un compte EUR, un compte inactif, une banque inactive et une autre société sont exclus ;
- banque sans compte courant MAD : colonne présente, valeurs `null` ;
- une date de fin après aujourd'hui est ramenée à aujourd'hui, avec des dates de test loin d'aujourd'hui pour ne pas dépendre du décalage horaire du Maroc ;
- 401 sans jeton, 403 sans `position.view`, 404 société inconnue, 422 date invalide ;
- montants en chaînes exactes.

Frontend (Vitest) : choix des jours visibles et texte du bouton ; classe de couleur selon le signe (positif, négatif, zéro, `null`).

Contrôle Edge : Société X avec des soldes de test (écran d'ordinateur, mobile, rôle Direction en lecture), puis nettoyage par un script SQL copié dans le conteneur (`docker compose cp`), jamais passé par PowerShell.

## Documentation à mettre à jour

`CLAUDE.md` (état actuel), `docs/specs/Plan_Phases_Realisation_SIMTIS.md` (statut de P8.1), `.claude/skills/simtis-design/pages.md` (tableau Banques : ligne par jour, reprise, bouton « Afficher plus »).
