# Relevés modifiables : aperçu standard éditable et champs métier après import

Date : 02/10/2026 · Statut : design validé par le métier, spécification à relire · Suite de P7 (import des relevés)

## 1. Objectif

À l'import d'un relevé, l'utilisateur voit **directement le relevé tel qu'il sera enregistré**, au format standard, et peut **corriger une ligne** avant d'enregistrer. Après l'import, les opérations restent **modifiables sur leurs champs métier**.

But : corriger ce que la banque fournit mal (montant illisible, date mal saisie, Pointage, commentaire) sans repasser par Excel, tout en gardant un relevé fidèle à la banque et entièrement tracé. **On ne crée jamais d'opération** : chaque opération enregistrée vient d'une ligne du fichier.

## 2. Décisions du métier (02/10/2026)

| Question | Décision |
|---|---|
| Champs modifiables **après** l'import | **Champs métier seulement** : Pointage, Lettrage / Escompte, Commentaire. Dates, libellé, débit, crédit et solde restent ceux de la banque. |
| Ce qu'on peut faire **avant** l'enregistrement | **Corriger toutes les cellules** d'une ligne du fichier. **Pas d'ajout de ligne** (décision du 02/10/2026 : « pas d'ajouter, seulement modification »). Une ligne corrigée est marquée et tracée. |
| Qui modifie après l'import | **Trésorerie seulement** (permission `statements.import` : Trésorerie, Administrateur). Comptable et Direction en lecture. |
| Comment garder les corrections jusqu'à l'enregistrement | **Lignes envoyées** avec le fichier à la confirmation. Pas de brouillon en base (recharger la page avant d'enregistrer fait perdre les corrections). |

## 3. L'aperçu standard modifiable (étape Validation)

Après l'analyse automatique (inchangée : choix du compte, dépôt du fichier, mapping de secours), le tableau de la Validation devient le relevé **tel qu'il sera enregistré**.

- **Colonnes** : les 11 du format standard, dans leur ordre (Société · Pointage · Banque · Date d'opération · Date de valeur · Libellé · Débit · Crédit · Solde · Lettrage / Escompte · Commentaire), précédées d'une colonne **État** (badge Valide / Erreur / Doublon, et mention « corrigée ») et d'une case **Importer**.
- **Modifier une ligne** : un clic la passe en édition (champs à la place des cellules) : dates (`AAAA-MM-JJ` via champ date), montants (saisie française, ex. `12 500,50`, jamais convertis en nombre à virgule flottante), Pointage (liste des types actifs), textes. Société et Banque viennent du compte et ne se modifient pas. Un bouton « Annuler les corrections » rend à la ligne ses valeurs du fichier.
- **Revérification immédiate** dans le navigateur, avec les mêmes règles que le serveur : date d'opération lisible et pas dans le futur ; date de valeur lisible si renseignée ; libellé présent ; débit ou crédit (pas les deux, pas aucun) ; montants à 2 décimales au plus ; solde facultatif ; Lettrage / Escompte 120 caractères au plus. Une ligne en erreur corrigée devient Valide et se coche automatiquement ; une ligne Valide rendue invalide par une correction reste cochée et bloque « Confirmer l'import » jusqu'à ce qu'elle soit corrigée ou décochée.
- **Pas d'ajout de ligne** : aucun bouton « Ajouter une ligne ». Une opération absente du fichier doit venir d'un nouveau fichier de la banque.
- **Case Importer** : **cochée par défaut sur toutes les lignes cochables** (décision du 08/10/2026 : lignes valides, en erreur et doublons internes au fichier ; `defaultChecked` dans `lib/importLines.ts`, partagé avec l'import Sage) ; une ligne en erreur cochée bloque la confirmation jusqu'à sa correction ou son décochage ; **non cochable** sur une ligne déjà importée pour ce compte ; les lignes ignorées n'ont pas de case et ne sont jamais importées. Boutons « Tout cocher » / « Tout décocher » (`CheckAllButtons`) au-dessus du tableau. Elle remplace « Écarter les lignes en erreur » et « Garder la ligne ».
- **Résumé recalculé en direct** sur les lignes cochées : nombre, totaux débit / crédit, période, solde d'ouverture et de clôture (lignes SOLDE INITIAL / SOLDE FINAL du fichier prioritaires), cohérence « ouverture + mouvements = clôture ».
- **« Confirmer l'import »** désactivé tant qu'une ligne cochée est en erreur, qu'aucune ligne n'est cochée, ou que le fichier est déjà importé.

## 4. Enregistrement et traçabilité

### 4.1 API

`POST /api/statements/import/confirm` (multipart, permission `statements.import`) accepte un nouveau champ facultatif **`lignes`** (JSON) : les lignes du fichier à importer, avec leurs éventuelles corrections. Chaque ligne :

| Champ | Contenu |
|---|---|
| `numero` | Numéro de la ligne dans le fichier (**obligatoire** : pas d'ajout) |
| `date_operation`, `date_valeur` | `AAAA-MM-JJ` (date de valeur facultative) |
| `libelle`, `reference` | Texte (référence facultative) |
| `debit`, `credit`, `solde` | Montants en texte exact (`"12500.50"`), solde facultatif |
| `pointage_type_id` | Type actif, ou `null` (alors déduit par la règle automatique) |
| `lettrage_escompte`, `commentaire` | Texte facultatif |

Sans `lignes`, la confirmation garde son fonctionnement actuel (`garder_doublons`, `ecarter_erreurs`, fichier importé tel quel). Avec `lignes`, ces deux champs sont refusés (422). Un même `numero` envoyé deux fois → 422.

### 4.2 Traitement serveur (une seule transaction)

1. Analyse à nouveau le fichier : empreinte (fichier déjà importé pour la société → 409), correspondance de colonnes (incomplète → 409), lignes d'origine, lignes SOLDE INITIAL / SOLDE FINAL.
2. Pour chaque ligne reçue : `numero` qui n'est pas une ligne d'opération du fichier → 409 ; revérification avec les mêmes règles que l'analyse. **Au moins une ligne invalide → rien n'est enregistré** ; la réponse (409) liste chaque ligne fautive et ses motifs. Aucune ligne → 409.
3. Origine de chaque ligne : **Fichier** (identique à la ligne d'origine) ou **Corrigée** (au moins un champ différent de la ligne d'origine).
4. Empreinte : une ligne garde **l'empreinte de sa version d'origine** quand la ligne d'origine était valide, pour que la même opération renvoyée plus tard par la banque soit reconnue comme déjà importée ; une ligne d'origine en erreur, une fois corrigée, reçoit l'empreinte de ses valeurs finales. Une ligne dont l'empreinte existe déjà pour le compte → 409 (déjà importée).
5. Pointage vide : déduit par `guess_pointage` (libellé puis sens), comme aujourd'hui.
6. Enregistrement : import, relevé (période, soldes d'ouverture et de clôture calculés sur les lignes enregistrées, lignes SOLDE INITIAL / FINAL prioritaires), opérations, solde du jour de clôture (le relevé fait foi), contrôle du solde, modèle de colonnes.
7. **Audit** `import_releve` : en plus des chiffres actuels, `lignes_corrigees` (numéro, champ, avant, après) et `lignes_fichier_non_importees` (numéros).

### 4.3 Base de données (migration 0006)

- `bank_transactions.origine` : `VARCHAR(10) NOT NULL DEFAULT 'Fichier'`, CHECK `origine IN ('Fichier', 'Corrigée')`. Les opérations existantes prennent `Fichier`. Test de la contrainte dans `tests/test_constraints.py`.
- `enums.ORIGINES_OPERATION = ("Fichier", "Corrigée")`.

## 5. Modification après l'import

- **Relevé continu** (carte « Relevés par compte ») : pour un utilisateur avec `statements.import`, chaque ligne a une icône « Modifier » (Lucide `PenLine`) qui ouvre une fenêtre (`FormModal`) : Pointage (liste), Lettrage / Escompte, Commentaire. Les autres champs s'y affichent en lecture. Une ligne corrigée avant l'import porte la petite mention « corrigée » sous son libellé.
- **API** : `PATCH /api/statements/transactions/{id}`, corps `{pointage_type_id, lettrage_escompte, commentaire}` (`extra="forbid"` : tout autre champ → 422). Permission `statements.import` (Comptable, Direction → 403). Opération inconnue → 404 ; Pointage inconnu ou inactif → 409 ; Lettrage / Escompte > 120 caractères → 422 ; textes vides → `null`. Audit `modification_operation`, avant / après des seuls champs changés ; aucune écriture si rien ne change.
- **Liste des Pointages** : `GET /api/pointage-types` (types actifs : id, code, libellé), tout utilisateur connecté (routeur protégé, sans permission métier).
- Une opération déjà rapprochée (P11) restera modifiable sur ces champs : ils n'entrent pas dans le rapprochement.

## 6. Hors périmètre

- **Ajout d'une opération**, avant ou après l'import.
- Brouillon d'import en base (corrections perdues si la page est rechargée avant l'enregistrement).
- Modification des dates, du libellé ou des montants après l'import.
- Suppression d'une opération importée.
- Le format « Montant + sens » du relevé BP (constat du 02/10/2026), traité à part.

## 7. Tests

**Backend**
- Confirmation avec `lignes` : ligne corrigée (origine `Corrigée`, empreinte d'origine conservée, champs enregistrés), ligne du fichier décochée (absente, listée dans l'audit), ligne d'origine en erreur corrigée (empreinte des valeurs finales) ; audit détaillé.
- Refus sans rien enregistrer : ligne invalide (motifs listés), `numero` absent, inconnu ou en double, ligne déjà importée, aucune ligne, `lignes` avec `garder_doublons` / `ecarter_erreurs` (422).
- Réimport plus tard d'un fichier contenant la version d'origine d'une ligne corrigée : reconnue comme déjà importée.
- Sans `lignes` : comportement actuel inchangé (tests existants).
- `PATCH` : champs autorisés, champ interdit (422), Pointage inactif (409), 404, droits (Trésorerie 200, Comptable et Direction 403), audit des seuls champs changés, aucune trace si rien ne change.
- Contrainte `origine` (valeur inconnue refusée, défaut `Fichier`) ; `GET /api/pointage-types`.

**Frontend**
- Tests unitaires de la revérification d'une ligne (mêmes cas que le serveur) et du recalcul du résumé (totaux, soldes, cohérence avec SOLDE INITIAL).

**Navigateur (Edge, Société X, données nettoyées ensuite)**
- Fichier avec SOLDE INITIAL et une ligne en erreur : correction dans l'aperçu (la ligne devient Valide et se coche), « Annuler les corrections », décochage d'une ligne, résumé recalculé, absence de bouton d'ajout, enregistrement ; mention « corrigée » visible dans le relevé continu ; modification d'un Pointage et d'un commentaire après l'import ; Direction sans icône « Modifier » ; mobile sans débordement.


## Changements du 08/10/2026

- Formats acceptés : `.xlsx` et `.xls`.
- Les tuiles de l'étape Validation filtrent le tableau (second clic : toutes les lignes). « Lignes ignorées » affiche les lignes non retenues et leur raison : SOLDE INITIAL (solde d'ouverture), SOLDE FINAL (solde de clôture), ligne de total ou de solde, ligne de titre ou sans montant. Lecture seule.


## Pointage : les 74 catégories du métier (08/10/2026)

- Les pointages sont les 74 catégories fournies par le métier (`backend/app/seeds/pointages.py`), libellés inchangés ; Encaissement / Décaissement / Frais bancaires sont désactivés.
- Pointage d'une ligne à l'import : valeur du fichier ; sinon mémoire de la société (même libellé, pointage le plus fréquent) ; sinon catégorie nommée en mots entiers dans le libellé (la plus longue gagne, synonymes COMMISSION → COM, TENUE DE COMPTE → FRAIS, SALAIRE → LA PAIE, INTERETS → INTERET, REMBOURSEMENT PRET) ; sinon vide, affiché « À choisir ». « A voir » n'est jamais automatique. Jamais bloquant.
- Migration 0017 : catégories créées, anciens types désactivés, opérations existantes re-pointées par les mots-clés (audit `repointage`).

- Gros fichiers (08/10/2026) : 50 000 lignes et 20 Mo au plus ; aperçu de l'étape Validation par pages de 100 lignes (les tuiles filtrent et les totaux portent sur tout le fichier). Mesuré : 50 000 lignes analysées en 3 à 7 s, confirmées en 10 à 19 s.
- Abréviations des en-têtes (08/10/2026) : un en-tête est aussi lu avec ses abréviations développées en mots entiers (DT → date, VAL → valeur, LIB → libellé, MNT / MT → montant, OPE / OPER → opération, DEB → débit, CRED → crédit). Exemple : relevé AWB « DT opération », « DT valeur ».

## Relevés sans soldes : solde calculé (08/10/2026)

- Quand aucune cellule Solde du fichier n'est remplie, chaque solde = solde précédent − débit + crédit, dans l'ordre chronologique, depuis un solde d'ouverture : ligne SOLDE INITIAL du fichier, sinon le dernier solde connu du compte avant la 1re opération (dernière opération importée avec un solde, ou dernier solde du jour, le plus récent), sinon saisi par l'utilisateur (confirmation refusée sans lui).
- Étape Validation : champ « Solde d'ouverture » pré-rempli et modifiable ; soldes recalculés en direct. Le serveur refait le calcul sur les lignes retenues.
- Enregistrement : `solde_calcule = true` (migration 0018) ; le solde de clôture devient le solde du jour. Affichage identique à un solde du fichier.
- Relevé déjà importé sans soldes : `python -m app.cli recalculer-soldes --releve N --solde-ouverture X`.

## Solde d'ouverture calculé à rebours (08/10/2026)

Fichier sans soldes, sans ligne SOLDE INITIAL et sans solde connu avant sa première opération : le solde d'ouverture proposé est calculé **à rebours** depuis le tableau Banques. SIMTIS prend le premier solde du jour enregistré à partir du dernier jour du fichier (jour J), puis calcule `solde de J − crédits + débits du fichier`. Les lignes déjà importées sont exclues. L'origine s'affiche sous le champ (« Calculé à rebours depuis le solde du JJ/MM/AAAA (tableau Banques) »).

Si J est postérieur au dernier jour du fichier, un avertissement orange (`solde_ouverture_avertissement`) prévient que des opérations absentes entre les deux dates fausseraient le calcul. La valeur reste modifiable, et le serveur refait le calcul à la confirmation.

## Ordre chronologique des opérations (08/10/2026)

Un relevé listé du plus récent au plus ancien (cas AWB) est importé dans l'ordre du fichier : l'id ne dit donc pas quelle opération est la dernière d'un jour. Le tableau Banques et la page Relevés lisaient le solde de la plus ancienne opération du 06/10 (20 807 737,72) au lieu de la vraie clôture (20 351 468,30).

`bank_transactions.ordre` garde le rang chronologique de chaque opération dans son relevé, dans le même ordre que le calcul des soldes (`_chronological`). Toutes les lectures trient par date, relevé, `ordre`, puis id (`ORDRE_CHRONOLOGIQUE`). La migration 0021 a rangé les relevés déjà importés : un relevé dont la première ligne importée est plus récente que la dernière est retourné.

## Solde d'ouverture verrouillé après le premier import (09/10/2026)

Pour un fichier sans soldes, le solde d'ouverture est repris automatiquement, dans cet ordre :

1. **la banque** : la ligne SOLDE INITIAL du fichier (verrouillé). S'il diffère du solde de clôture du relevé précédent, un avertissement orange le signale (« une période manque peut-être ») ;
2. **le solde de clôture du relevé précédent** : la dernière opération importée avant la première opération du fichier, dans l'ordre chronologique (verrouillé) ;
3. **le tableau de position bancaire** : le dernier solde du jour avant le fichier, sinon le calcul à rebours ;
4. sinon, à saisir.

La saisie n'est possible qu'au **premier import** du compte, c'est-à-dire quand aucune opération n'a été importée avant ce fichier (un relevé plus ancien que ceux déjà importés compte comme un premier import). L'analyse renvoie `solde_ouverture_modifiable` ; l'écran désactive alors le champ et ne l'envoie pas. Le serveur refuse (409) un `solde_ouverture` différent du solde verrouillé. La commande `recalculer-soldes` garde la saisie (outil d'administration).

## Colonne Solde remplie à moitié (09/10/2026)

Certaines banques n'écrivent le solde que sur quelques lignes (par exemple en fin de journée). Désormais :

- toute case Solde vide d'une ligne lisible est calculée (solde précédent − débit + crédit), dans l'ordre chronologique ; une ligne en erreur ne déclenche pas le calcul ;
- un solde écrit par la banque est gardé tel quel (`solde_calcule = false`) et le calcul repart de lui ;
- s'il ne suit pas le calcul, la ligne affiche « Écart avec le calcul : N » en orange (`ecart_solde`, aperçu seulement) ; ce contrôle ne bloque jamais l'import ;
- si la première opération porte le solde de la banque, le solde d'ouverture est ce solde moins son montant (verrouillé, « Solde de la banque sur la première opération du fichier ») ; sinon la règle du 09/10/2026 s'applique (SOLDE INITIAL, relevé précédent, tableau Banques, saisie au premier import) ;
- à l'étape Validation, corriger un débit ou un crédit recalcule en direct les soldes calculés (`runningBalances`), affichés en gris ; les soldes de la banque restent en noir.

## Calcul à rebours limité au dernier jour du fichier (09/10/2026)

Le calcul à rebours depuis le tableau Banques n'utilise plus qu'un solde **daté du dernier jour du fichier** : il est alors exact. Un solde postérieur (par exemple une saisie du 03/10 pour un fichier qui s'arrête au 31/08) supposait qu'aucune opération n'avait eu lieu entre les deux dates ; la proposition était souvent fausse. Dans ce cas, le solde d'ouverture est « À saisir » (premier import) et l'avertissement orange disparaît.
