# Import Sage / SI et écritures comptables (P10) — spécification

Date : 05/10/2026. Phase : P10. Design validé en deux parties le 05/10/2026.

## But

Faire entrer dans SIMTIS les écritures de trésorerie déjà passées dans Sage / SI, pour les rapprocher des opérations bancaires en P11. SIMTIS n'est pas un second Sage : les écritures sont **importées** depuis un export Excel, jamais créées ni corrigées dans SIMTIS. Seul leur statut de rapprochement changera (P11).

Aucun export Sage réel n'est disponible : on part du format standard du cahier des charges ; le mapping de secours permettra d'importer le vrai fichier ; la recette (totaux identiques à Sage) se fera avec lui.

Hors périmètre : connexion directe à Sage (ODBC / API), import CSV, correction de lignes dans l'aperçu, rapprochement (P11).

## Décisions (05/10/2026)

| Sujet | Décision |
|---|---|
| Rattachement à une banque | Par le **code journal** Sage : chaque compte bancaire porte son « Journal Sage » (ex. BQ1 = AWB). Le compte 5141 est partagé entre les banques. |
| Lignes importées | Seulement les **journaux de banque** : une ligne dont le journal n'est le journal d'aucun compte bancaire de la société est ignorée. |
| Contreparties | Seulement la **ligne banque** : son compte doit commencer par le compte comptable du compte bancaire (5141…). Les contreparties (411, 441, 6147…) sont ignorées. |
| Portée d'un fichier | **Une société, plusieurs banques** : le fichier est importé pour la société active ; ses lignes se répartissent entre les comptes bancaires selon le journal. |
| Correction | **Aucune** dans SIMTIS : une ligne en erreur se corrige dans Sage ou s'écarte à la confirmation. |

## Données

**Migration 0010** :
- `bank_accounts.journal_sage` : `String(10)`, facultatif, enregistré en majuscules sans espaces autour.
- Index unique partiel `uq_bank_accounts_journal_sage_actif` sur (`company_id`, `journal_sage`) quand `journal_sage IS NOT NULL AND actif` : un journal ne sert qu'à un compte actif par société. Test dans `test_constraints.py`.

Tables existantes, sans changement : `import_batches` (type « Comptabilité », déjà prévu ; l'index `uq_import_batches_fichier_confirme` refuse un même fichier confirmé deux fois pour la société), `accounting_entries` (journal, compte, date_ecriture, libelle, reference, debit, credit, montant = credit − debit, numero_piece, echeance, tiers, hash_ligne unique par société, statut « Non rapprochée », `bank_account_id`, `import_batch_id`), `column_mappings` (type « Comptabilité », `company_id` renseigné, `bank_id` vide).

Les montants gardent le sens de Sage : débit et crédit tels que dans le fichier (une ligne banque au débit = de l'argent qui entre en banque). Le sens n'est pas inversé à l'import ; P11 compare un crédit bancaire à un débit comptable.

## Lecture du fichier

**Module commun** `backend/app/services/import_file.py` : fonctions sorties de `import_service.py` sans changer leur comportement — lecture d'une feuille `.xlsx` (5 Mo, 5 000 lignes au plus), détection de la ligne d'en-tête dans les 30 premières lignes, colonnes avec exemples, proposition de correspondance par synonymes d'en-têtes, contrôles de taille et de format. `import_service.py` les utilise ; ses 123 tests restent verts.

**Champs** (`ACCOUNTING_FIELDS`, synonymes normalisés) :

| Code | Libellé | Obligatoire | Synonymes |
|---|---|---|---|
| `date_ecriture` | Date | oui | date, date ecriture, date piece, date comptable |
| `journal` | Journal | oui | journal, code journal, jnl |
| `compte` | Compte | oui | compte, compte general, n compte, numero de compte |
| `libelle` | Libellé | oui | libelle, libelle ecriture, intitule |
| `reference` | Référence | non | reference, ref |
| `debit` | Débit | (débit / crédit ou montant) | debit, montant debit |
| `credit` | Crédit | (débit / crédit ou montant) | credit, montant credit |
| `montant` | Montant signé | (débit / crédit ou montant) | montant, montant signe |
| `numero_piece` | N° pièce | non | n piece, numero piece, piece, no piece |
| `echeance` | Échéance | non | echeance, date echeance |
| `tiers` | Tiers | non | tiers, compte tiers, client fournisseur |

Erreurs de mapping : chaque champ obligatoire associé ; Débit et Crédit, ou Montant signé, pas les deux ; une colonne ne sert qu'à un champ. Mapping proposé : celui mémorisé pour la société (même en-têtes), sinon les synonymes ; donné par l'utilisateur en secours.

**Classement de chaque ligne** (pures, testées) :
1. Ligne vide → sautée. Ligne sans date ni montant (titre, total) → ignorée.
2. Journal (texte, majuscules, espaces retirés) qui n'est le `journal_sage` d'aucun compte actif de la société → **ignorée** (« journal hors banque »).
3. Compte qui ne commence pas par le `compte_comptable` du compte bancaire (si celui-ci est renseigné) → **ignorée** (« contrepartie »). Sans compte comptable sur le compte bancaire, toutes les lignes de son journal sont retenues.
4. Ligne retenue, rattachée au compte bancaire du journal ; **en erreur** si : date manquante ou illisible, date dans le futur, libellé manquant, montant illisible, nul, débit ou crédit négatif (extourne : jamais remis en positif, décision de la relecture du 05/10/2026), ou débit et crédit renseignés tous les deux, échéance illisible. Longueurs : journal 20, compte 20, référence 60 (tronquée), N° pièce 60, tiers 120 (au-delà : erreur).
5. **Doublons** : empreinte `line_hash(company_id, (date, journal, compte, libellé, débit, crédit, pièce, référence), occurrence)` ; déjà importée pour la société → « Déjà importée » (jamais gardable) ; identique à une autre ligne du fichier → doublon interne, gardable.

**Analyse** : si aucun compte actif de la société n'a de journal Sage → 409 « Renseignez le journal Sage de vos comptes bancaires (écran Comptes). ». Résumé : lignes retenues valides, en erreur, en double, ignorées ; total débit et crédit des valides ; période ; répartition par compte bancaire (nombre, débit, crédit).

## API

Routeur `accounting` (`backend/app/api/accounting.py`), ajouté à `protected_router`.

| Méthode | Chemin | Permission | Rôle |
|---|---|---|---|
| POST | `/api/accounting/import/analyse` | `accounting.import` | multipart `fichier`, `company_id`, `mapping` (JSON, facultatif), `feuille` (facultatif) ; n'écrit rien |
| POST | `/api/accounting/import/confirm` | `accounting.import` | mêmes champs + `lignes_choisies` (JSON, numéros des lignes cochées, 08/10/2026) ; anciens champs `ecarter_erreurs` (bool) et `garder_doublons` (JSON) encore acceptés sans `lignes_choisies` (les mêler donne 422) ; sans état : le fichier est relu |
| GET | `/api/accounting/entries` | `accounting.import` OU `reconciliation.view` | `company_id` (obligatoire), `bank_account_id`, `from`, `to`, `statut`, `q`, `page` (1 par défaut) ; 50 par page, de la plus récente à la plus ancienne (date puis id) |
| GET | `/api/accounting/entries/{id}` | idem | détail + fichier d'origine, date d'import, auteur |
| GET | `/api/accounting/imports` | idem | `company_id` ; journal des imports de la société, du plus récent au plus ancien |

Confirmation : avec `lignes_choisies`, seules ces lignes sont importées (un doublon interne coché est importé) ; refus 409 pour une ligne cochée en erreur (« Ligne N : en erreur, à corriger dans Sage ou à décocher. »), déjà importée ou introuvable ; sans `lignes_choisies`, refus 409 si des lignes sont en erreur sans `ecarter_erreurs` ; si aucune ligne n'est à importer, si le fichier est déjà confirmé pour la société ; sinon une transaction : `import_batches` (type Comptabilité, statut Confirmé, compteurs), `accounting_entries`, `column_mappings` (par société, mis à jour), audit `import_ecritures` (fichier, nombre d'écritures par compte, écartées). Société inconnue ou inactive → 404. `q` cherche sans tenir compte de la casse dans libellé, N° pièce, référence et tiers. Réponse paginée : `{ total, page, taille: 50, total_debit, total_credit, ecritures: [...] }` (totaux sur tout le filtre). Montants en texte exact.

Écran Comptes : `PUT /api/accounts/{id}` et `POST /api/accounts` acceptent `journal_sage` (facultatif, majuscules, lettres et chiffres, 10 caractères au plus ; 409 s'il est déjà utilisé par un autre compte actif de la société) ; `AccountOut` le renvoie ; audit comme les autres champs.

## Écran `/ecritures`

`frontend/components/ecritures/` ; page `frontend/app/(app)/ecritures/page.tsx` (remplace la page vide). Société active (`useCompany()`), jamais deux sociétés mélangées.

- **En-tête** : « Écritures comptables », bouton primaire « Importer un export Sage » (avec `accounting.import`).
- **Assistant** (carte « Importer un export Sage ») : étapes **Fichier → Validation** (`ImportSteps`), glisser-déposer d'un `.xlsx`, analyse dès que le fichier est choisi ; mapping de secours (« Colonnes non reconnues ») ; Validation : tuiles (Lignes à importer · En erreur · En double · Ignorées · Total débit / crédit · Période), tableau des lignes retenues en lecture seule (Importer · État · Date · Journal · Compte bancaire avec `BankLabel` · Compte · N° pièce · Libellé · Débit · Crédit · Échéance · Tiers), motifs des erreurs sous la ligne ; **case « Importer » par ligne** (08/10/2026), cochée par défaut sur les lignes valides, en erreur et les doublons internes, non cochable sur une ligne déjà importée, « Tout cocher » / « Tout décocher » ; une ligne en erreur cochée bloque la confirmation (elle se corrige dans Sage ou se décoche) ; les cases « Écarter les lignes en erreur » et « Garder » sont supprimées ; alerte si le fichier est déjà importé ; bouton « Confirmer l'import ». Résultat : écritures ajoutées par compte, écartées.
- **Carte « Écritures »** : boutons de compte bancaire (« Tous » + un par compte qui a un journal Sage, avec logo), Du / Au, Statut (`Select`), recherche ; résumé (Écritures · Total débit · Total crédit) ; `DataTable` (Date · Journal · Compte bancaire · N° pièce · Libellé · Débit · Crédit · Échéance · Tiers · Statut en `StatusBadge`) ; « Page N sur M » avec « Précédent » / « Suivant » ; changer un filtre revient à la page 1. Clic sur une ligne : fenêtre « Écriture du JJ/MM/AAAA » en lecture seule.
- **Carte « Journal des imports »** : 10 derniers puis « Afficher plus » (`showFirst`) ; Importé le + auteur · Fichier · Période · Écritures ajoutées · Total débit / crédit.
- États : chargement, erreur avec « Réessayer », vide (« Aucune écriture importée. » avec le bouton d'import).
- Montants : `formatAmount`, à droite, `tabular-nums` ; tokens et icônes Lucide (skill `simtis-design`).

## Tests (écrits avant le code)

Backend :
- `test_accounting_import_api.py` : colonnes reconnues ; ligne banque retenue et rattachée par son journal ; contrepartie et journal d'achats ignorés ; compte bancaire sans compte comptable ; montant signé ; chaque erreur ; doublon interne et déjà importé ; société sans journal Sage (409) ; aucun mélange entre sociétés ; confirmation (lignes, compteurs, audit, mapping mémorisé par société et réutilisé) ; refus sans `ecarter_erreurs` ; fichier déjà confirmé (409) ; 401 / 403 (Direction ne peut pas importer).
- `test_accounting_entries_api.py` : filtres compte, dates, statut ; recherche ; pagination et totaux sur tout le filtre ; détail ; journal des imports ; 401 / 403 / 404.
- `test_accounts_api.py` : `journal_sage` créé, modifié, normalisé, refusé en double (409), audité.
- `test_constraints.py` : unicité du journal Sage actif par société.
- `test_migrations.py` : 29 tables toujours ; aller-retour 0010.
- `test_statements_api.py` : inchangé et vert (la lecture commune ne change rien).

Frontend : Vitest pour les règles pures (filtres → requête, pagination, libellés) ; contrôle Edge sur Tefil avec un fichier de test (import, filtres, pagination, détail, Direction en lecture, mobile), puis suppression des données de test par un script SQL copié dans le conteneur (jamais passé par PowerShell).

## Documentation

`CLAUDE.md`, `docs/specs/Plan_Phases_Realisation_SIMTIS.md` (statut P10), `docs/modele-donnees.md` (`journal_sage`), `.claude/skills/simtis-design/pages.md` (page Écritures).


## Changements du 08/10/2026

- Formats acceptés : `.xlsx` et `.xls` (l'ancien format), pour les relevés comme pour les exports Sage. Le format est reconnu au contenu du fichier ; les deux donnent les mêmes valeurs.
- Étape Validation : les tuiles Lignes à importer · Lignes en erreur · Doublons · Lignes ignorées sont cliquables et filtrent le tableau. L'analyse renvoie les lignes ignorées avec leur numéro de ligne Excel, leur contenu et leur raison : ligne de titre ou de total, journal qui n'est le journal Sage d'aucun compte, compte de contrepartie (pas la ligne banque du journal).

- Gros fichiers (08/10/2026) : 50 000 lignes et 20 Mo au plus ; aperçu de l'étape Validation par pages de 100 lignes (les tuiles filtrent et les totaux portent sur tout le fichier). Mesuré : 50 000 lignes analysées en 3 à 7 s, confirmées en 10 à 19 s.
- Abréviations des en-têtes (08/10/2026) : un en-tête est aussi lu avec ses abréviations développées en mots entiers (DT → date, VAL → valeur, LIB → libellé, MNT / MT → montant, OPE / OPER → opération, DEB → débit, CRED → crédit). Exemple : relevé AWB « DT opération », « DT valeur ».
