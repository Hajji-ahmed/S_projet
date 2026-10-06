# SIMTIS Finance — Plan détaillé des phases de réalisation

> Document de pilotage consolidé à partir de l'ensemble des documents du dossier `docs/specs/`.
> Il remplace et corrige la numérotation incohérente de `README_Phases_Realisation_Projet_SIMTIS.md`
> (vue d'ensemble en 20 phases, détail en 23 phases).

---

## 0. Sources analysées

| Document | Contenu utile au plan |
|---|---|
| `Cahier_des_charges_SIMTIS_V3_Position_Rapprochement_Previsions.pdf` | Périmètre, structures standard, formules, statuts, plan de réalisation en 13 phases, critères d'acceptation |
| `Architecture_fonctionnelle_detaillee_SIMTIS.pdf` | Flux Sources → Intégration → Normalisation → Traitement → Pilotage, modules, rôles utilisateurs |
| `Architecture_technique_detaillee_SIMTIS.pdf` | Stack Next.js / FastAPI / PostgreSQL / Docker, arborescences, services, tables, sécurité, MVP technique en 9 étapes |
| `README_Phases_Realisation_Projet_SIMTIS.md` | Phases existantes, scoring de rapprochement, MVP, règles de conduite |
| `Prompt_Design_SIMTIS_Claude.md` | Design System (palette teal, composants, pages, états UI) |
| `ChatGPT Image 29 sept. 2026.png` | Maquette cible du Dashboard |
| `Remarque_modification_3_tableaux_SIMTIS.md` + `SIMTIS_3_tableaux_corriges(1).xlsx` | Structure imposée des tableaux Prévisions, Devises, Banques |

**Constat** : le dossier ne contient que de la documentation. Aucun code n'existe encore, donc le projet démarre de zéro.
Le prompt de design parle de « refondre » un frontend existant. Dans le cadre de ce plan, le Design System est intégré **dès le départ** (Phase 3) plutôt qu'en refonte.

---

## 1. Principes directeurs (non négociables)

1. **Comprendre avant de coder** : aucune règle automatique n'est figée avant la validation des fichiers Excel réels de Salma (position) et Mustapha (rapprochement).
2. **SIMTIS n'est pas un second Sage** : l'application consomme et contrôle les données comptables, elle ne les recrée pas.
3. **Normaliser avant de calculer** : chaque source (banque, Sage/SI, Excel) passe par le modèle standard interne.
4. **Aucune validation automatique sur le seul montant** : toute correspondance ambiguë passe par un humain.
5. **Tout est traçable** : import, validation, modification, clôture → `audit_logs`.
6. **Montants exacts** : `NUMERIC(18,2)` en base, `Decimal` en Python. Jamais de `float`.
7. **Devises jamais additionnées directement** : conversion MAD avec taux et date du taux conservés.
8. **Validation métier avant production** : les utilisateurs métier signent la recette, pas le développeur.

---

## 2. Vue d'ensemble

### 2.1 Les phases

```text
┌─ CADRAGE ────────────────────────────────────────────────────────────┐
│ P0  Cadrage métier & collecte des fichiers réels                     │
│ P1  Analyse des fichiers & dictionnaire de données                   │
│ P2  Modèle de données standard & règles métier                       │
└──────────────────────────────────────────────────────────────────────┘
┌─ FONDATIONS ─────────────────────────────────────────────────────────┐
│ P3  Initialisation technique + Design System                         │
│ P4  Base PostgreSQL (schéma, migrations, seeds)                      │
│ P5  Socle sécurité : authentification, rôles, permissions, audit     │
└──────────────────────────────────────────────────────────────────────┘
┌─ TRÉSORERIE ─────────────────────────────────────────────────────────┐
│ P6  Banques & Comptes (P6.1 banques · P6.2 comptes · P6.3 soldes)    │
│ P7  Import & normalisation des relevés bancaires                     │
│ P8  Position bancaire (tableau Banques)                              │
│ P9  Gestion des devises (tableau Devises)                            │
└──────────────────────────────────────────────────────────────────────┘
┌─ COMPTABILITÉ & RAPPROCHEMENT ───────────────────────────────────────┐
│ P10 Import Sage / SI & tableau des écritures                         │
│ P11 Rapprochement 1→1 : moteur, scoring, validation manuelle         │
│ P12 Gestion des écarts                                               │
│ P13 Rapprochement avancé 1→N, N→1, N→N                               │
└──────────────────────────────────────────────────────────────────────┘
┌─ PILOTAGE ───────────────────────────────────────────────────────────┐
│ P14 Prévisions & position prévisionnelle (tableau Prévisions)        │
│ P15 Dashboard, KPI & alertes                                         │
│ P16 Administration, historique & rapports                            │
└──────────────────────────────────────────────────────────────────────┘
┌─ LIVRAISON ──────────────────────────────────────────────────────────┐
│ P17 Tests (unitaires, intégration, métier)                           │
│ P18 Recette sur données réelles & validation utilisateurs            │
│ P19 Déploiement Docker & mise en production                          │
│ P20 Exploitation, support & évolutions                               │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Dépendances

```text
P0 → P1 → P2 ─┬─► P3 → P4 → P5 ─► P6 → P7 → P8 → P9
              │                          │
              │                          └──► P10 → P11 → P12 → P13
              │                                              │
              └────────────────────────────────► P14 ◄───────┘ (P14 dépend de P8)
                                                  │
                                          P15 ◄───┴─── (P8, P11, P12, P14)
                                          P16
                                          P17 (continu dès P4) → P18 → P19 → P20
```

- **P10 peut démarrer en parallèle de P8/P9** dès que P7 est fini, car le mécanisme d'import est réutilisé.
- **P17 (tests) n'est pas une phase de fin** : les tests unitaires s'écrivent dans chaque phase ; P17 regroupe les tests transverses et métier.

### 2.3 Planning indicatif

> Estimations pour **1 développeur full-stack**, à ajuster après la Phase 0 selon la complexité réelle des fichiers.

| Phase | Durée indicative | Jalon |
|---|---|---|
| P0 – P2 | 3 à 4 semaines | **J1 : règles métier validées** |
| P3 – P5 | 2 à 3 semaines | **J2 : socle technique opérationnel** |
| P6 – P9 | 4 à 5 semaines | **J3 : position bancaire automatisée** |
| P10 – P12 | 4 à 5 semaines | **J4 : MVP rapprochement 1→1** |
| P13 – P16 | 5 à 6 semaines | **J5 : version complète** |
| P17 – P19 | 3 à 4 semaines | **J6 : mise en production** |
| **Total** | **≈ 21 à 27 semaines** | |

---

## 3. Points à arbitrer avant développement

Ces points bloquent la conception de la base. Ils doivent être tranchés en **Phase 0**.

### 3.1 Termes métier ambigus

| Terme | Où il apparaît | Question à poser |
|---|---|---|
| **Taux** | Tableau Banques | Taux d'intérêt du crédit ? Taux de change ? Taux d'utilisation ? |
| **Ligne** (écrit « Linge » dans l'Excel) | Tableau Banques | Montant de la ligne de crédit autorisée ? Égal à « Crédit autorisé » ? |
| **Date** (3 lignes dans le CDC, 1 dans la maquette) | Tableau Banques | Date de solde ? d'échéance ? de mise à jour ? Combien de dates au final ? |
| **Disposition / Déposition FC réel** | Sous le tableau Banques | Disponible facilité de caisse réel ? Formule exacte ? |
| **Lettrage / Escompte** | Relevé standard (champ 10) | Un seul champ ou deux notions distinctes ? |
| **Ex rh convertible / compte RH convertible** | Tableau Devises | Compte en dirhams convertibles ? Comment est-il valorisé ? |
| **UAR** | Tableau Devises (maquette) | Faute de frappe pour **EUR** ? |
| **Escompte** | Tableau Prévisions | Flux d'escompte commercial (entrée) ou coût (sortie) ? |
| **Pointage** | Relevé standard (champ 2) | Valeurs possibles ? Lien avec le statut de rapprochement ? |
| **Société** | Relevé standard (champ 1) | Multi-sociétés ? Si oui, il faut une table `companies`. |

### 3.2 Contradictions entre documents

| Sujet | Cahier des charges V3 | Maquette Excel + Remarque | Décision à prendre |
|---|---|---|---|
| **Colonnes Banques** | CIH, BP, Autres, Total, Dépassement | CIH, **Tijari**, **BMCE**, BP, Totale, Dépassement | Liste fixe ou **colonnes dynamiques** selon les banques actives ? (recommandé : dynamique, rendu identique à la maquette) |
| **Lignes Banques** | Taux, Ligne, Date ×3, Solde, Crédit autorisé/utilisé/disponible, Position | Taux, Ligne, Date + **Disposition FC réel** | Les lignes de calcul (solde, crédit, position) restent-elles visibles ? |
| **Devises** | MAD, EUR, USD, Compte RH convertible, Autre + 6 colonnes (Montant, Banque, Compte, Taux, Équiv. MAD, Date) | **Uniquement** UAR, USD, Ex rh convertible, sans colonnes | L'affichage suit la maquette, mais **le modèle de données doit garder** montant, taux et date (règle de traçabilité du CDC) |
| **Prévisions** | Date en ligne, catégories en colonnes (Encaissement, Escompte, Douane, Paie, Refinancement, Chèques, Commentaire) | Colonne Date **fusionnée** à gauche, **libellés en lignes** (Encaissement 24/09, La paie, Refinancement, Douane, CHQ1..3), colonnes Encaissement / Escompte / Douane | Adopter la maquette pour l'affichage ; stocker chaque flux comme une ligne `forecasts` avec catégorie + date |
| **Nom des tables** | `bank_discrepancies`, `cash_forecasts` | (archi technique) `discrepancies`, `forecasts` | Choisir une convention unique (recommandé : `discrepancies`, `cash_forecasts`) |

> **Règle** : la maquette Excel fait foi pour l'**affichage** des 3 tableaux (consigne « RÈGLE ABSOLUE »).
> Le cahier des charges fait foi pour le **modèle de données et les calculs**.

### 3.3 Décisions prises (30/09/2026)

| Sujet | Décision | Conséquence |
|---|---|---|
| **Taux** | Taux d'intérêt | Champ `taux_interet NUMERIC(18,6)` sur le compte / la ligne de crédit |
| **Ligne** | = Crédit autorisé | Pas de champ séparé : `bank_accounts.credit_autorise`. Le tableau Banques l'affiche sous le libellé **« LIGNE »**, comme le classeur |
| **Date** (tableau Banques) | Remplacée par 3 lignes « facilité de caisse » datées (28, 29, 30/09 dans le classeur) | Historique **par jour** : table `bank_account_balances` (compte, date, solde, crédit utilisé) |
| **Disposition FC réel** | ~~= Solde bancaire + Crédit autorisé~~ ; **depuis le 03/10/2026 : facilité de caisse du dernier jour − LIGNE** (TOTAL = somme ; DEPASSEMENT = TOTAL, la LIGNE étant déjà retirée : correction du 03/10/2026, qui remplace « TOTAL − somme des LIGNES »). Libellé du classeur : **« Disponible Fc reel »** | Exemple : AWB LIGNE 800 000, solde 400 000 → facilité 1 200 000 → Disponible 400 000 ; avec BP (LIGNE 600 000, solde 650 000) : TOTAL 1 050 000, DEPASSEMENT 1 050 000. À vérifier sur l'Excel de Salma en recette |
| **Solde d'un jour** (décidé le 03/10/2026) | Solde de la **dernière opération importée** ce jour-là (date d'opération, ordre du relevé, opérations sans solde ignorées), sinon solde du jour saisi ou écrit par l'import, sinon dernier solde connu | Calculé à la lecture (`position_repository.last_operation_soldes`) ; l'import ne change pas (il n'écrit toujours que le solde du jour de clôture) |
| **UAR** | = EUR | Affiché « EUR » dans le tableau Devises |
| **Structure des 3 tableaux** | `SIMTIS_tableaux_complets.xlsx` (envoyé le 30/09/2026) | Une feuille, 3 tableaux empilés sur les mêmes colonnes de banques. Remplace `SIMTIS_3_tableaux_corriges(1).xlsx` et la Remarque |
| **Banques** | 5 : AWB (Attijariwafa), BMCE, BP, CIH, **BMCI** | Affichées par code, dans cet ordre (`banks.ordre_affichage`) |
| **Prévisions** | Appartiennent à une société et, facultativement, à une banque | Une prévision sans banque = montant de la journée (Encaissement / Escompte / Douane). Chaque prévision porte son propre sens (Entrée / Sortie) |
| **Exp DH convertible** | Type de compte `DH convertible`, en MAD | Hypothèse de modélisation, définition métier à confirmer (§3.4) |
| **Crédit utilisé** | Saisi à la main | Formulaire par compte : montant, date de mise à jour, utilisateur ; audit avant / après |
| **Taux de change** | Saisis à la main | Formulaire `exchange_rates` : devise, taux, date du taux, utilisateur ; audit avant / après |
| **Pointage** | Type d'opération : encaissement, décaissement, frais bancaires… (liste ouverte) | Table de référence éditable, distincte du statut de rapprochement |
| **Société** | Multi-sociétés : Simtis et **Tefil** (nom confirmé le 05/10/2026 ; affichée « Société X » avant, code `SOCX` inchangé, renommée par la migration 0009). Tefil n'a pas de comptes EUR / USD, donc pas de tableau Devises | Table `companies` obligatoire ; chaque compte bancaire est rattaché à une société. Le nom est une donnée, modifiable sans toucher au code |
| **Position par société** | Affichée séparément, pas de total consolidé Simtis + Société X | Position, tableaux et dashboard filtrés par société |
| **Fichiers comptables** | Un export de comptabilisation par société | Chaque import comptable est rattaché à une société ; le rapprochement ne croise jamais deux sociétés |
| **Format des relevés** | Excel uniquement | Import `.xlsx` (et `.xls` si les banques l'exportent) ; CSV et MT940 hors MVP |
| **Accès Sage / SI** | Export de fichier | Import manuel de fichier ; pas de connexion ODBC/API dans le MVP |
| **Nom de la banque** | « Attijariwafa » (code **AWB** dans les tableaux) | Remplace « Tijari » / « TIJARI » ; les en-têtes des tableaux affichent le code de la banque |
| **Logos** | Fournis | `frontend/public/logo-simtis.png` et `frontend/public/banques/{attijariwafa,bmce,bp,cih,bmci}.png` |
| **facilité de caisse** (décidé le 02/10/2026) | Une ligne **par jour**, sans limite (chaque jour ajoute sa date), valeur de chaque banque = **Solde du jour + LIGNE** | Calculé depuis `bank_account_balances`. Exemple validé : AWB LIGNE 500 000 et solde −200 000 → 300 000 ; BMCE LIGNE 300 000 et solde +100 000 → 400 000 ; TOTAL 700 000 |
| **DEPASSEMENT** (décidé le 02/10/2026) | Pour chaque date : TOTAL des facilités de caisse des banques − TOTAL des LIGNES des banques | Exemple ci-dessus : 700 000 − 800 000 = −100 000. Remplace la proposition max(0, −Disponible Fc reel) |
| **Comptes du tableau Banques** (décidé le 02/10/2026) | Le **compte courant MAD** de chaque banque seulement | « Exp DH convertible » reste dans le tableau Devises, hors TOTAL et hors Disponible Fc reel |
| **Évolutions** | D'autres fonctionnalités comptables s'ajouteront après le MVP, selon l'équipe | Architecture modulaire (un module = api + service + permissions) ; vérifier que ces ajouts respectent le principe « pas un second Sage » |

### 3.4 Encore en attente

- **Tableaux du classeur** (à trancher avant P8, P9 et P14, sans bloquer P4 ni P5) :
  - ~~« facilité de caisse » : solde ou facilité utilisée ? Toujours 3 jours ?~~ Tranché le 02/10/2026 (§3.3) : Solde du jour + LIGNE, une ligne par jour sans limite.
  - Prévisions : 30/09 est-elle la date de la situation ? La colonne C contient-elle une échéance, un libellé (« La paie », « CHQ1 »…) ou les deux ? Encaissement, Escompte et Douane sont-ils des totaux de la journée, non répartis par banque ?
  - Devises : que contiennent les cellules grisées de EUR / USD / Exp DH convertible (montant en devise ?) et le TOTAL (équivalent MAD, ou total par devise) ?
  - « Exp DH convertible » : compte en dirhams convertibles ? Compte-t-il dans le Disponible Fc reel et le TOTAL MAD ? (proposé : à part)
- **Termes** : Lettrage / Escompte, Escompte (entrée ou sortie). (Dépassement tranché le 02/10/2026, §3.3.)
- ~~**Libellés provisoires** : nom de la « Société X ».~~ Tranché le 05/10/2026 : Tefil.
- **Pointage** : liste complète des valeurs.
- **Règles** : tolérances de rapprochement, grille de scoring, règle de doublon, exceptions, seuils d'alerte.
- **Fichiers réels** : le format **cible** (structure standard) est décrit dans le CDC §4 et l'architecture technique §5. Les fichiers réels ne bloquent pas le démarrage : on développe avec des fichiers de test au format standard. Ils restent nécessaires pour la recette : au moins un relevé par banque (P7), l'Excel de Salma (P8), un export comptable par société (P10).

---

## 4. Phases détaillées

Chaque phase est décrite avec : **Objectif · Prérequis · Tâches · Livrables · Critères de fin (Definition of Done)**.

---

### PHASE 0 — Cadrage métier & collecte des fichiers réels

**Objectif** : comprendre le processus réel tel qu'il est pratiqué aujourd'hui dans Excel, avant d'écrire la moindre règle.

**Acteurs** : Salma (Trésorerie), Mustapha (Comptabilité / rapprochement), Responsable Finance, Direction.

**Tâches**

- [ ] Ateliers avec Salma : dérouler **en direct** la construction de la position bancaire quotidienne
- [ ] Ateliers avec Mustapha : dérouler un rapprochement complet sur un mois réel
- [ ] Collecter les fichiers (réels ou anonymisés) :
  - [ ] Excel de position bancaire de Salma
  - [ ] Excel de rapprochement de Mustapha
  - [ ] 1 relevé réel **par banque** (AWB, BMCE, BP, CIH, BMCI), idéalement sur 2 à 3 mois
  - [ ] Export Sage / SI représentatif
  - [ ] Tableau réel des prévisions
- [ ] Faire trancher **tous les points de la section 3** (termes et contradictions)
- [ ] Identifier les exceptions métier : frais bancaires, agios, chèques non débités, virements groupés, rejets
- [ ] Définir les **tolérances** : écart de date accepté (± N jours), écart de montant accepté (0 ? arrondi ?)
- [ ] Confirmer techniquement : formats de relevés (Excel, CSV, MT940 ?), mode d'accès à Sage/SI (export manuel, ODBC, API ?)
- [ ] Lister les utilisateurs cibles, leurs rôles et le volume de données (nombre de comptes, de lignes/mois)

**Livrables**

- Compte rendu des ateliers avec le processus actuel décrit pas à pas
- Jeu de fichiers réels de référence (déposés dans `docs/samples/`, anonymisés)
- **Glossaire métier validé** (Taux, Ligne, FC réel, Lettrage/Escompte, RH convertible…)
- Liste des règles métier et tolérances
- Liste des utilisateurs et rôles

**Critères de fin**

- ✅ Chaque terme ambigu de la section 3.1 a une définition signée par la Trésorerie
- ✅ Chaque contradiction de la section 3.2 a une décision écrite
- ✅ Au moins 1 relevé réel par banque est disponible

---

### PHASE 1 — Analyse des fichiers & dictionnaire de données

**Objectif** : étudier techniquement chaque fichier collecté pour concevoir l'import et la normalisation.

**Prérequis** : P0 (fichiers réels disponibles)

**Tâches**

- [ ] Pour chaque banque, relever : nom des colonnes, ordre, ligne d'en-tête, lignes parasites (titres, totaux, pieds de page)
- [ ] Identifier les formats : dates (`dd/mm/yyyy`, `yyyy-mm-dd`, Excel serial), montants (séparateur décimal `,` ou `.`, espaces de milliers, signe `-`, colonnes Débit/Crédit séparées ou montant signé)
- [ ] Repérer : doublons, lignes vides, soldes d'ouverture/clôture, encodage (UTF-8, Latin-1)
- [ ] Analyser l'export Sage/SI : journaux, comptes (512xxx), N° pièce, échéance, tiers
- [ ] Comparer libellés banque vs libellés comptables pour identifier les **clés de rapprochement** exploitables (référence virement, n° chèque, nom du tiers)
- [ ] Rétro-ingénierie des formules Excel de Salma (position) et Mustapha (rapprochement)

**Livrables**

- **Dictionnaire de données** : pour chaque source, colonne → type → format → obligatoire → champ standard cible
- **Fiche de format par banque** (sert de base aux modèles de mapping de P7)
- Règles de validation des fichiers
- Liste des formules Excel traduites en pseudo-code

**Critères de fin**

- ✅ Chaque colonne de chaque fichier source est associée à un champ standard ou explicitement ignorée
- ✅ Les formules Excel sont reproduites à la main sur un exemple et donnent le même résultat

---

### PHASE 2 — Modèle de données standard & règles métier

**Objectif** : définir le modèle interne commun et formaliser toutes les règles de calcul.

**Prérequis** : P1

**Tâches**

- [ ] Définir la **structure standard du relevé** (11 champs du CDC) :
  `Société · Pointage · Banque · Date d'opération · Date de valeur · Libellé · Débit · Crédit · Solde · Lettrage/Escompte · Commentaire`
  + champs techniques : `reference`, `montant signé`, `account_id`, `statement_id`, `source`, `hash_ligne`, `status`
- [ ] Définir la **structure standard comptable** :
  `Date · Libellé · Débit · Crédit · N° pièce · Échéance` + `journal`, `compte`, `référence`, `tiers`, `source`, `status`
- [ ] Formaliser les formules :

  ```text
  Crédit disponible        = Crédit autorisé − Crédit utilisé
  Position disponible      = Solde bancaire + Crédit disponible
  Total soldes             = Σ soldes sélectionnés
  Total crédit disponible  = Σ crédits disponibles
  Total position           = Σ positions disponibles
  Dépassement              = (à définir en P0, ex. max(0, Crédit utilisé − Crédit autorisé))
  Position prévisionnelle  = Position de départ + Encaissements prévus − Décaissements prévus
  Équivalent MAD           = Montant devise × Taux (taux + date conservés)
  ```

- [ ] Définir les **machines à états** :

  ```text
  Transaction / écriture : Non rapprochée → À vérifier → Rapprochée
                                         ↘ Écart
  Écart     : À traiter → En cours → Traité → Clôturé
  Prévision : Prévu → En attente → Réalisé | Reporté | Annulé
  Contrôle solde : Conforme | Écart | À vérifier
  ```

- [ ] Définir la règle de **détection de doublon** (ex. `compte + date_operation + montant + libellé normalisé + référence`)
- [ ] Définir la **grille de scoring** du rapprochement (voir P11) avec les seuils
- [ ] Rédiger le Modèle Conceptuel de Données (MCD)

**Livrables**

- Spécification du modèle standard (banque + comptable)
- Document des règles métier et formules
- MCD / diagramme entité-relation
- Diagrammes d'états

**Critères de fin**

- ✅ Modèle et règles validés par Salma et Mustapha
- ✅ Aucune notion ambiguë restante dans le modèle

---

### PHASE 3 — Initialisation technique + Design System

**Objectif** : poser le squelette du projet, l'environnement de développement et le Design System SIMTIS.

**Prérequis** : P2

> **Statut : réalisé le 30/09/2026** (`docker compose up` lance les 3 services, CI écrite, layout et 13 routes). Écarts par rapport à la liste ci-dessous, à reprendre dans la phase qui en a besoin :
> - Composants non créés : `BankCard` (P6), `DateRangePicker` et `FilterBar` (P8), `NotificationCenter` (P15). `ChartCard` = `Card`. `SearchBar` est en place mais non branchée. `DataTable` n'a ni tri, ni pagination, ni sélection multiple (P11).
> - Recharts est installé depuis P8.3 (03/10/2026) ; à réutiliser pour P14 et P15.
> - Rechargement à chaud : le frontend tourne en mode webpack avec scrutation des fichiers, car Turbopack ne détecte pas les modifications sur un dossier monté depuis Windows.
> - PostgreSQL est publié sur le port 5434 du poste (5432 et 5433 sont souvent occupés).
> - La CI (`.github/workflows/ci.yml`) est validée en syntaxe mais n'a pas encore tourné : elle ne s'exécutera qu'après un `push` sur GitHub.

**Tâches — Structure du dépôt**

```text
simtis/
├── frontend/                 # Next.js (App Router, TypeScript, Tailwind)
│   ├── app/
│   │   ├── login/
│   │   ├── dashboard/
│   │   ├── banques/  └── [id]/
│   │   ├── comptes/
│   │   ├── releves/
│   │   ├── ecritures/
│   │   ├── position-bancaire/
│   │   ├── rapprochement/
│   │   ├── ecarts/
│   │   ├── previsions/
│   │   ├── devises/
│   │   ├── rapports/
│   │   ├── historique/
│   │   └── administration/
│   ├── components/  services/  hooks/  types/  lib/  public/
├── backend/                  # FastAPI
│   ├── app/
│   │   ├── api/              # banks, accounts, statements, accounting, position,
│   │   │                     # reconciliation, discrepancies, forecasts, currencies,
│   │   │                     # dashboard, auth, admin, audit
│   │   ├── services/         # bank, import, normalization, position, reconciliation,
│   │   │                     # forecast, audit, auth
│   │   ├── models/           # SQLAlchemy
│   │   ├── schemas/          # Pydantic
│   │   ├── repositories/
│   │   └── core/             # config, sécurité, db, dépendances
│   ├── alembic/
│   ├── tests/
│   └── main.py
├── docs/                     # documents S_projet + samples anonymisés
├── docker-compose.yml
├── .env.example
└── README.md
```

- [ ] Initialiser Git, conventions de branches et de commits
- [ ] `docker-compose.yml` de développement : `frontend`, `backend`, `db` (PostgreSQL)
- [ ] Backend : FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2 + pytest ; endpoint `/health`
- [ ] Frontend : Next.js + TypeScript + Tailwind + Lucide React + librairie de graphiques (Recharts) ; client API centralisé dans `lib/`
- [ ] Linting et formatage (ruff/black côté Python, ESLint/Prettier côté TS)
- [ ] CI minimale : lint + tests à chaque push
- [ ] **Design System** (d'après `Prompt_Design_SIMTIS_Claude.md`) :
  - [ ] Variables CSS : `--simtis-primary #006B70`, `--simtis-primary-dark #004F54`, `--simtis-secondary #18B7C8`, `--simtis-light #E6F7F7`, `--simtis-background #F5F8FA`, `--simtis-card #FFFFFF`, `--simtis-text #17324D`, `--simtis-muted #64748B`, `--simtis-border #D9E3E8`, `--simtis-success #16A66A`, `--simtis-warning #F59E0B`, `--simtis-danger #E5484D`
  - [ ] Police Inter, échelle typographique, espacements (4 à 32px), radius, ombres légères
  - [ ] Layout : `AppSidebar` (teal foncé, 240-260px, logo SIMTIS, 12 entrées de menu, version en bas) + `AppHeader` (70px, recherche, notifications, profil)
  - [ ] Composants : `PageHeader`, `KpiCard`, `BankCard`, `DataTable`, `StatusBadge`, `SearchBar`, `DateRangePicker`, `ChartCard`, `FilterBar`, `Modal`, `Toast`, `EmptyState`, `LoadingState`, `ErrorState`, `NotificationCenter`
  - [ ] Badges de statut : Rapprochée, À vérifier, Non rapprochée, Écart, Prévu, Réalisé, En attente, Reporté, À traiter, En cours, Clôturé
  - [ ] Responsive : sidebar repliable (tablette), menu mobile, tableaux scrollables horizontalement

**Livrables**

- Dépôt initialisé, `docker compose up` lance les 3 services
- Page de démonstration du Design System (tous les composants)
- Layout Sidebar + Header fonctionnel sur toutes les routes (pages vides)

**Critères de fin**

- ✅ Un nouveau développeur démarre le projet en une commande
- ✅ CI verte
- ✅ Layout conforme à la maquette de référence

---

### PHASE 4 — Base de données PostgreSQL

**Objectif** : créer le schéma relationnel complet, versionné par migrations.

**Prérequis** : P2, P3

> **Statut : réalisé le 30/09/2026.** Le schéma réel (25 tables) est décrit dans [`docs/modele-donnees.md`](../modele-donnees.md), qui fait foi en cas de différence avec la liste ci-dessous. Écarts par rapport à cette liste :
> - **Nouvelle table `bank_account_balances`** : solde et crédit utilisé par compte et **par jour**, pour les lignes « facilité de caisse » du classeur. `bank_accounts` ne porte plus le solde ni le crédit utilisé.
> - **`bank_accounts`** : pas de colonne `ligne` (LIGNE = `credit_autorise`). Ajouts : `type_compte` (Courant / DH convertible), `compte_comptable`.
> - **`cash_forecasts`** : rattachées à une société et à une banque **facultative** (pas obligatoirement à un compte), avec un `sens` propre à chaque prévision.
> - **`banks`** : colonne `ordre_affichage`. **`pointage_types`** : nouvelle table de référence. **`reconciliation_matches`** : ajout de `company_id` et `commentaire` ; `origine` (Automatique / Manuelle) remplace `proposé_par`.
> - **`audit_logs`** : ajout seul, garanti par un trigger PostgreSQL (UPDATE, DELETE et TRUNCATE refusés).
> - **Non réalisé** : « jeu de données de test anonymisé issu de P0 » (il n'y a pas encore de fichiers réels). Remplacé par des données de démonstration (`python -m app.seeds --demo`), marquées DEMO.
> - **Seeds** : l'administrateur initial n'est pas créé ici mais en P5, avec son mot de passe haché. La matrice des permissions proposée en P5 est chargée avec les rôles, sans validation métier.
> - **Limite** : `alembic check` ne compare pas les contraintes CHECK ; elles sont protégées par `backend/tests/test_constraints.py`.

**Tables**

| Table | Champs principaux |
|---|---|
| `companies` *(si multi-sociétés confirmé)* | id, nom, code |
| `banks` | id, nom, code, logo, actif, created_at |
| `bank_accounts` | id, bank_id, company_id, libellé, numéro/RIB, devise, solde, crédit_autorisé, crédit_utilisé, taux, ligne, actif |
| `import_batches` | id, type (bank/accounting), fichier, hash_fichier, user_id, statut, nb_lignes, nb_erreurs, nb_doublons, created_at |
| `column_mappings` | id, bank_id, nom_modèle, mapping (JSONB), format_date, séparateur_décimal |
| `bank_statements` | id, account_id, import_batch_id, période_début, période_fin, solde_ouverture, solde_clôture |
| `bank_transactions` | id, statement_id, account_id, société, pointage, date_operation, date_valeur, libellé, référence, débit, crédit, montant, solde, lettrage_escompte, commentaire, hash_ligne, status |
| `accounting_entries` | id, import_batch_id, journal, compte, date, libellé, référence, débit, crédit, montant, numero_piece, echeance, tiers, source, status |
| `reconciliation_rules` | id, nom, critère, poids, tolérance, actif |
| `reconciliation_matches` | id, type (1-1, 1-N, N-1, N-N), score, statut, proposé_par (auto/manuel), validé_par, validé_le |
| `reconciliation_match_items` | id, match_id, bank_transaction_id *ou* accounting_entry_id, montant_affecté |
| `balance_checks` | id, account_id, date, solde_relevé, solde_enregistré, écart, statut, commentaire, user_id |
| `discrepancies` | id, type, bank_transaction_id, accounting_entry_id, montant, différence, date, responsable_id, statut, commentaire, traité_le |
| `currencies` | code, libellé |
| `exchange_rates` | id, devise, taux, date_taux, source |
| `forecast_categories` | id, code (ENCAISSEMENT, ESCOMPTE, DOUANE, PAIE, REFINANCEMENT, CHEQUES, AUTRE), sens (entrée/sortie) |
| `cash_forecasts` | id, account_id, category_id, libellé, date_prévue, montant, devise, statut, date_réalisation, bank_transaction_id, commentaire |
| `users` | id, nom, email, mot_de_passe_hash, actif, dernier_login |
| `roles`, `permissions`, `user_roles`, `role_permissions` | RBAC dynamique |
| `audit_logs` | id, user_id, action, entité, entité_id, ancienne_valeur (JSONB), nouvelle_valeur (JSONB), ip, created_at |

**Tâches**

- [ ] Modèles SQLAlchemy + migrations Alembic
- [ ] Types montants `NUMERIC(18,2)`, taux `NUMERIC(18,6)`
- [ ] Contraintes : clés étrangères, `UNIQUE(account_id, hash_ligne)` pour les doublons, `CHECK` sur les statuts
- [ ] Index : `(account_id, date_operation)`, `(date, montant)`, `status`, `numero_piece`, `reference`
- [ ] Script de **seed** : banques (CIH, Attijariwafa, BMCE, BP), comptes, rôles, permissions, admin initial, catégories de prévision, devises
- [ ] Jeu de données de test anonymisé issu de P0

**Livrables** : schéma validé, migrations, seeds, diagramme ER à jour.

**Critères de fin**

- ✅ `alembic upgrade head` puis `downgrade base` fonctionnent sans erreur
- ✅ Les seeds chargent un environnement utilisable

---

### PHASE 5 — Socle sécurité : authentification, rôles, permissions, audit

**Objectif** : sécuriser l'API **avant** d'y exposer des données financières. Le backend doit vérifier les permissions avant chaque opération sensible (architecture technique §12).

**Prérequis** : P4

> **Statut : réalisé le 01/10/2026.** Choix et écarts par rapport à la liste ci-dessous :
> - **Jetons** : jeton d'accès JWT de 15 min gardé en mémoire dans le navigateur ; session de 12 h dans un cookie `HttpOnly`, `SameSite=Strict`, limité à `/api/auth`, dont seule l'empreinte est stockée (`user_sessions`). Pas de rotation du jeton de session (elle déconnecterait les onglets ouverts en parallèle). Les permissions ne sont **jamais** dans le jeton : relues en base à chaque requête.
> - **Hachage** : argon2id (`pwdlib`). Verrouillage 15 min après 5 échecs ; message unique « Email ou mot de passe incorrect », y compris pour un compte verrouillé ou désactivé (le motif réel est dans l'audit).
> - **Comptes** : pas d'écran d'administration avant P16. En attendant : `python -m app.cli create-user` / `set-password`. Comptes de démonstration (un par rôle) avec `python -m app.seeds --demo`.
> - **Menu** : une page est visible si l'utilisateur a l'une des permissions de `ROUTE_PERMISSIONS` (`frontend/lib/permissions.ts`). Proposition validée le 01/10/2026 ; la matrice des rôles reste à valider par le métier.
> - **Protection par défaut** : toute route hors de la liste publique exige un utilisateur connecté ; un test échoue si une route répond sans jeton.
> - **Hors périmètre, reporté** : limitation du nombre de requêtes par IP, IP réelle derrière un reverse proxy, désactivation de `/docs` en production (P19) ; double authentification et SSO (non demandés).

**Tâches**

- [ ] Authentification : login email + mot de passe (hash bcrypt/argon2), JWT access + refresh token
- [ ] Dépendance FastAPI `require_permission("reconciliation.validate")` réutilisable sur chaque endpoint
- [ ] Permissions de base :

  | Permission | Admin | Trésorerie | Comptable | Responsable | Direction / Consultation |
  |---|:-:|:-:|:-:|:-:|:-:|
  | banks.manage | ✅ | ✅ | | | |
  | statements.import | ✅ | ✅ | | | |
  | position.view | ✅ | ✅ | ✅ | ✅ | ✅ |
  | accounting.import | ✅ | | ✅ | | |
  | reconciliation.view | ✅ | ✅ | ✅ | ✅ | ✅ |
  | reconciliation.validate | ✅ | | ✅ | ✅ | |
  | discrepancies.manage | ✅ | | ✅ | ✅ | |
  | forecasts.manage | ✅ | ✅ | | | |
  | dashboard.view | ✅ | ✅ | ✅ | ✅ | ✅ |
  | admin.users / admin.roles | ✅ | | | | |
  | audit.view | ✅ | | | ✅ | |

- [ ] **AuditService** : fonction `audit.log(user, action, entité, avant, après)` appelée par tous les services
- [ ] Frontend : page `/login`, stockage sécurisé du token, garde de routes, menu filtré selon les permissions, profil dans le header (ex. « Salma — Trésorerie »)

**Livrables** : authentification fonctionnelle, RBAC centralisé, service d'audit prêt.

**Critères de fin**

- ✅ Un appel API sans token renvoie 401 ; sans permission, il renvoie 403 (tests automatisés)
- ✅ Chaque action d'écriture produit une ligne dans `audit_logs`

---

### PHASE 6 — Module Banques & Comptes

**Objectif** : gérer le référentiel bancaire, base de tous les autres modules.

**Prérequis** : P5

P6 est découpée en **3 sous-phases**, dans cet ordre. Chacune livre un écran utilisable, avec son API, ses tests et son contrôle dans le navigateur, et passe par son propre plan (skill `simtis-plan`).

```text
P6.1 Référentiel des banques ──► P6.2 Comptes bancaires + société active ──► P6.3 Soldes du jour, crédit utilisé, chiffres
```

**Règles communes aux 3 sous-phases**

- Lecture : permission `position.view`. Création, modification, activation, saisie : `banks.manage` (Administrateur, Trésorerie).
- Aucune suppression : une banque ou un compte se **désactive** (l'historique et l'audit restent cohérents).
- Chaque écriture produit une ligne `audit_logs` avec les valeurs avant / après, dans la même transaction.
- Les boutons d'action ne s'affichent qu'avec `banks.manage` ; l'API refuse de toute façon (403).

---

#### P6.1 — Référentiel des banques

> **Statut : réalisé le 01/10/2026.** Propositions 1 et 2 appliquées (désactivation refusée tant que des comptes sont actifs ; logo choisi parmi les fichiers fournis). Règle ajoutée : le **code n'est plus modifiable** après la création, car les seeds retrouvent les banques par leur code à chaque démarrage. Le nombre de comptes d'une carte compte les deux sociétés ; il sera filtré par société en P6.2. Erreurs métier : `NotFoundError` (404) et `ConflictError` (409), réutilisables par les modules suivants.

**Objectif** : consulter les banques et, pour la Trésorerie, en ajouter, les modifier et les désactiver. Ce sont les colonnes des 3 tableaux du classeur.

**Backend**

- [ ] `bank_repository`, `bank_service`, schémas Pydantic
- [ ] `GET /api/banks` (triées par `ordre_affichage`, avec le nombre de comptes actifs) et `GET /api/banks/{id}`
- [ ] `POST /api/banks`, `PUT /api/banks/{id}`, `PATCH /api/banks/{id}/status`
- [ ] Règles : code unique en majuscules (AWB, BMCE…), nom obligatoire, logo choisi parmi les fichiers de `frontend/public/banques/` ou vide, ordre d'affichage modifiable

**Frontend**

- [ ] Composants de formulaire réutilisables : champ, texte, liste déroulante, nombre, fenêtre de formulaire
- [ ] `BankCard` (version référentiel : logo, nom, code, nombre de comptes, statut)
- [ ] `/banques` : grille de `BankCard`, fenêtre « Nouvelle banque » / « Modifier », activer / désactiver

**Critères de fin**

- ✅ Création, modification, activation et désactivation tracées dans l'audit
- ✅ Direction / Consultation voit les banques mais reçoit 403 sur toute écriture (test)
- ✅ Contrôle dans le navigateur : Trésorerie modifie une banque, Direction ne voit aucun bouton d'action

---

#### P6.2 — Comptes bancaires et société active

> **Statut : réalisé le 01/10/2026.** Écarts : « Société X » garde son nom (pas de commande de renommage, à la demande du métier). Règle ajoutée par le métier : **pour une société, une banque a un seul compte actif par devise et par type** (lecture A : un compte courant MAD avec LIGNE et taux, au plus un EUR, un USD, un DH convertible), garantie par un index unique partiel (migration 0003). Société, banque et devise d'un compte ne sont plus modifiables ; taux saisi en %, stocké en fraction. Corrections transverses faites pendant P6.2 : tolérance de 60 s sur l'horloge pour les jetons (recalage de l'horloge Docker), vrai NULL SQL dans `audit_logs`.

**Objectif** : gérer les comptes de chaque société (Simtis, Société X), sans jamais mélanger les deux.

**Backend**

- [ ] `GET /api/companies` (liste des sociétés actives, pour tout utilisateur connecté)
- [ ] `account_repository`, `account_service`, schémas
- [ ] `GET /api/accounts?company_id=&bank_id=&devise=&type_compte=&actif=` et `GET /api/accounts/{id}`
- [ ] `POST /api/accounts`, `PUT /api/accounts/{id}`, `PATCH /api/accounts/{id}/status`
- [ ] Champs : société, banque, libellé, numéro (RIB), devise, type (Courant / DH convertible), compte comptable, **LIGNE** (crédit autorisé), taux d'intérêt
- [ ] Règles : société et banque actives, numéro unique, devise connue, compte DH convertible en MAD, LIGNE ≥ 0, taux entre 0 et 100 %
- [ ] Commande `python -m app.cli rename-company` pour donner son vrai nom à « Société X » (écran en P16)

**Frontend**

- [ ] Sélecteur de **société active** dans l'en-tête (une seule à la fois, mémorisée dans le navigateur)
- [ ] `FilterBar` (Banque, Devise, Statut)
- [ ] `/comptes` : tableau (Banque, Libellé, Numéro, Devise, Type, LIGNE, Taux, Statut) + fenêtres de création et de modification + activation

**Critères de fin**

- ✅ CRUD complet tracé dans l'audit
- ✅ Aucun écran ni aucune réponse d'API ne mélange les comptes de deux sociétés (test)
- ✅ Règles de validation testées (doublon de numéro, DH convertible en EUR refusé…)

---

#### P6.3 — Soldes du jour, crédit utilisé et chiffres des banques

> **Statut : réalisé le 01/10/2026.** Hypothèses validées par le métier : **H1** chaque champ (solde, crédit utilisé) prend sa dernière valeur connue jusqu'à aujourd'hui (heure du Maroc) ; **H2** une valeur jamais saisie reste vide, jamais comptée pour 0 ; **H3** pas de saisie dans le futur ni sur un compte inactif, et ressaisir un jour le corrige (l'audit garde l'avant). Formules du CDC dans `position_service.py` (fonctions pures, à réutiliser en P8). Écart : une date future renvoie 409 (règle métier) et non 422. Les comptes de démonstration inactifs (EUR, USD, DH convertible) ont été supprimés de la base de développement.

**Objectif** : saisir chaque jour le solde et le crédit utilisé d'un compte, et voir sur chaque banque son solde, son crédit disponible et sa position disponible.

**Backend**

- [ ] `GET /api/accounts/{id}/balances?from=&to=` (historique)
- [ ] `PUT /api/accounts/{id}/balances/{date}` : saisie ou correction du solde et/ou du crédit utilisé d'une date (source « Saisie », date future refusée, audit avant / après)
- [ ] Calculs, dans un module réutilisé par la position bancaire (P8) :
  - Crédit disponible = Crédit autorisé − Crédit utilisé
  - Position disponible = Solde + Crédit disponible
  - Date de mise à jour = date du dernier solde connu
- [ ] Chiffres exposés dans les réponses des comptes et des banques. Totaux par banque **par devise** : jamais de somme entre devises différentes

**Frontend**

- [ ] `BankCard` complète : solde, crédit disponible, position disponible, dernière mise à jour (société active)
- [ ] `/banques/[id]` : détail de la banque, ses comptes pour la société active, historique des soldes
- [ ] Fenêtre « Saisir le solde du jour », depuis `/comptes` et `/banques/[id]`

**Critères de fin**

- ✅ Exemple du CDC vérifié en test : solde 300 000, LIGNE 500 000, utilisé 100 000 → crédit disponible 400 000, position disponible 700 000
- ✅ Montants exacts (`Decimal`) de la base à l'écran, aucune somme entre devises (tests)
- ✅ Chaque saisie de solde tracée (avant / après)

---

**Points à trancher avant P6** (propositions entre parenthèses)

| # | Question | Proposition | Bloque |
|---|---|---|---|
| 1 | Désactiver une banque qui a encore des comptes actifs ? | Refusé, avec un message : désactiver d'abord ses comptes | P6.1 |
| 2 | Ajouter le logo d'une nouvelle banque ? | Choisi parmi les fichiers déjà fournis ; téléversement en P16 | P6.1 |
| 3 | Qui renomme « Société X » ? | L'administrateur, par la commande en ligne ; écran en P16 | P6.2 |
| 4 | Quels comptes alimentent la `BankCard` ? | Les comptes courants MAD actifs de la société active ; les autres devises affichées à part sur la carte, sans conversion | P6.3 |
| 5 | Saisie manuelle du solde : seulement en attendant les relevés (P7), ou toujours ? | Toujours possible, avec la source enregistrée (« Saisie » ou « Relevé ») | P6.3 |

La question encore ouverte du §3.4 (« facilité de caisse » = solde ou facilité utilisée ?) ne bloque pas P6 : les deux valeurs sont saisissables, et le crédit disponible suit la formule du CDC.

**Livrables** : module Banques & Comptes utilisable.

> **Avance hors phase (01/10/2026) — tableaux Devises et Prévisions saisis à la main.** À la demande du métier, `/position-bancaire` affiche dès maintenant les tableaux Devises et Prévisions au format exact du classeur, saisis cellule par cellule pour une société et une date (`GET` / `PUT /api/position/devises` et `/api/position/previsions`, tables `saisies_devises`, `saisies_previsions`, `saisies_previsions_jour`, migration 0004). Rien n'y est calculé, pas même le TOTAL. Lecture : `position.view` ; saisie : `banks.manage` (Devises) et `forecasts.manage` (Prévisions) ; audit des seules cellules modifiées. Libellés des 14 lignes en texte libre ; dates futures acceptées. Ces saisies seront remplacées par les calculs de P9 et P14 : il faudra alors décider si les valeurs saisies sont reprises ou archivées.

---

### PHASE 7 — Import & normalisation des relevés bancaires

**Objectif** : première vraie automatisation du travail Excel. Chaque banque fournit un format différent ; le système le ramène à la structure standard.

**Prérequis** : P6, fiches de format de P1

P7 est découpée en **3 sous-phases** : **P7.1 Analyse** (lecture du fichier, détection des colonnes, correspondance, aperçu des lignes valides / en erreur / en double, rien d'enregistré) → **P7.2 Confirmation** (enregistrement de `import_batches`, `bank_statements`, `bank_transactions`, mémorisation du modèle de correspondance, refus d'un fichier déjà importé, audit) → **P7.3 Écran Relevés** (`/releves` : glisser-déposer, étapes Détection → Correspondance → Validation, résumé, historique, contrôle du solde de clôture).

> **P7.1 — Statut : réalisé le 01/10/2026** (sans plan préalable, à la demande du métier). `POST /api/statements/import/analyse` (multipart : `fichier`, `bank_account_id`, `mapping` JSON facultatif, `feuille` facultative), permission `statements.import`, **n'écrit rien en base**. Choix appliqués en attendant le métier : `.xlsx` seulement (5 Mo, 5 000 lignes au plus) ; ligne d'en-tête détectée dans les 30 premières lignes ; correspondance proposée par synonymes d'en-têtes, ou reprise du modèle mémorisé de la banque (`column_mappings`, écrit en P7.2), ou choisie par l'utilisateur ; Débit / Crédit **ou** une colonne Montant signé ; une colonne « Banque » du fichier sert seulement à vérifier le compte ; Lettrage / Escompte en texte libre (120 caractères) ; Pointage gardé en texte brut (rattachement à `pointage_types` en P7.2) ; référence extraite du libellé (n° de chèque, REF, N°, facture) quand il n'y a pas de colonne ; lignes sans date ni montant, et lignes de total ou de solde sans date, ignorées ; date d'opération future en erreur ; doublons = ligne déjà importée pour le compte (empreinte) ou ligne identique dans le fichier (signalée, empreinte distincte). Résumé : totaux débit / crédit des lignes valides, période, soldes d'ouverture et de clôture et leur cohérence quand le fichier a une colonne Solde.

> **P7.2 — Statut : réalisé le 01/10/2026** (sans plan préalable, à la demande du métier ; propositions appliquées en attendant sa validation). `POST /api/statements/import/confirm` : mêmes champs que l'analyse, plus `garder_doublons` (JSON, numéros de lignes) et `ecarter_erreurs`. **Sans état** : le fichier est renvoyé et analysé à nouveau, donc ce qui est enregistré correspond toujours à son contenu (pas de fichier stocké entre les deux étapes ; `import_batches` n'a que des lignes « Confirmé »). Règles : un fichier déjà confirmé pour la société est refusé (409) ; une ligne en erreur bloque la confirmation, sauf si l'utilisateur choisit de l'écarter ; une ligne déjà importée est toujours écartée ; une ligne identique à une autre du même fichier est écartée, sauf si l'utilisateur la garde ; un Pointage doit correspondre à un type actif (code ou libellé), sinon la ligne est en erreur. Enregistrement en une transaction : `import_batches`, `bank_statements` (période, soldes d'ouverture et de clôture), `bank_transactions` (« Non rapprochée »), modèle de correspondance de la banque (`column_mappings`, par en-tête ; non mémorisé si une colonne associée n'a pas d'en-tête), audit `import_releve`. **Solde de clôture** : le relevé fait foi, il devient le solde du jour de clôture (source « Relevé », crédit utilisé saisi conservé, audit `saisie_solde` / `correction_solde`) ; s'il existait déjà un solde ce jour-là, un `balance_checks` est créé : Conforme, Écart (avec le montant) ou À vérifier (mouvements incohérents avec le solde de clôture). Seul le jour de clôture est mis à jour, pas les jours intermédiaires du relevé. **Validé par le métier le 02/10/2026** : le relevé fait foi sur le solde du jour (l'écart reste tracé) ; seul le solde du jour de clôture est mis à jour ; un **Pointage inconnu reste vide et ne bloque pas la ligne** (changé en P7.3).

> **P7.3 — Statut : réalisé le 02/10/2026.** Page `/releves` : bouton « Importer un relevé » (permission `statements.import`), assistant en 3 étapes **Détection des colonnes → Mapping → Validation** (compte actif de la société active + glisser-déposer d'un `.xlsx` ; tableau « Colonne fichier → Champ SIMTIS » avec exemples et choix de la feuille ; résumé valides / en erreur / doublons / ignorées, période, totaux, soldes, filtre des lignes, case « Écarter les lignes en erreur », case « Garder » sur chaque doublon interne, alerte si le fichier est déjà importé ou si les soldes sont incohérents), résultat de l'import (opérations enregistrées, écartées, effet sur le solde du jour, contrôle du solde, modèle mémorisé), historique des imports de la société active et opérations d'un relevé. API : `GET /api/statements?company_id=&bank_account_id=` et `GET /api/statements/{id}/transactions`, lisibles avec `statements.import` **ou** `reconciliation.view` (mêmes droits que la page ; Direction et Comptable en lecture). Badges Valide / Erreur / Doublon ajoutés (success / danger / warning). L'aperçu affiche 500 lignes au plus par filtre.

> **Format standard des relevés — réalisé le 02/10/2026** (demande du métier, design validé). Tout relevé importé se lit et s'exporte dans la même structure standard (CDC §4), ses 11 champs dans cet ordre : Société · Pointage · Banque · Date d'opération · Date de valeur · Libellé · Débit · Crédit · Solde · Lettrage / Escompte · Commentaire. Pointage = **type d'opération** (décision du 30/09 confirmée : « État du pointage » n'est que le libellé du CDC). Banque = code (AWB, BMCE…). `GET /api/statements/{id}/transactions` renvoie ces champs dans cet ordre (puis référence, montant signé, statut) ; `GET /api/statements/{id}/export` renvoie un `.xlsx` d'une feuille « Relevé standard » (11 colonnes exactement, dates et montants en vraies valeurs Excel, débit ou crédit nul = cellule vide), nommé `releve_<BANQUE>_<DEVISE>_<début>_<fin>.xlsx`, mêmes droits que la lecture. Page Relevés : tableau des opérations à 11 colonnes + Statut, bouton « Exporter » sur la carte et icône dans l'historique. Hors périmètre : export de plusieurs relevés ou d'une période.

> **Relevé continu par compte — réalisé le 02/10/2026** (demande du métier, design validé). Chaque import s'**ajoute au relevé existant du compte** au lieu de créer un tableau séparé. En base rien ne change : un `bank_statements` par fichier (traçabilité, contrôle du solde de clôture), les doublons restent écartés, donc un fichier qui chevauche le précédent n'ajoute que ses nouvelles lignes. `GET /api/statements/accounts/{id}?from=&to=` renvoie le relevé continu (toutes les opérations du compte au format standard, par date puis ordre d'import ; période, nombre d'opérations, totaux, solde d'ouverture avant la 1re opération et de clôture après la dernière ; tout l'historique sans dates ; 404 compte inconnu, 409 période inversée) ; `GET /api/statements/accounts/{id}/export?from=&to=` l'exporte (`releve_<BANQUE>_<DEVISE>_<1re date>_<dernière date>.xlsx`, 409 s'il est vide). Page Relevés : carte « Relevés par compte » (un bouton par compte qui a des imports, filtre Du / Au, résumé, tableau standard, « Exporter » qui suit la période), puis « Journal des imports » en lecture seule (le tableau séparé par fichier est retiré de l'interface ; les routes par fichier restent dans l'API). Après un import, le relevé du compte importé s'affiche avec ses nouvelles lignes. Pas de pagination : le tableau affiche les 50 dernières opérations et le journal les 10 derniers imports, avec un bouton « Afficher plus » (ajouté le 02/10/2026) ; le résumé et l'export portent toujours sur tout le relevé ou la période.

> **Import direct — réalisé le 02/10/2026** (demande du métier, design validé). L'assistant passe à 2 étapes, **Fichier → Validation** : plus de bouton « Analyser » ni d'étape Mapping ; dès que le compte et le fichier sont choisis, l'analyse se lance et mène directement à la Validation. Le mapping ne s'affiche qu'**en secours**, si les colonnes ne sont pas reconnues (encadré « Colonnes non reconnues » ; la correspondance est ensuite mémorisée pour la banque). Le choix du compte devient une liste déroulante maison avec le **logo de chaque banque** (accessible au clavier). Aucun changement d'API ni des règles d'import.

> **Solde initial et Pointage automatique — réalisé le 02/10/2026** (demande du métier, design validé). (1) Une ligne SOLDE INITIAL / ANCIEN SOLDE / SOLDE PRÉCÉDENT / REPORT (ou SOLDE FINAL / NOUVEAU SOLDE), datée ou non, **sans débit ni crédit** (cellules vides, à zéro ou « - », ajouté le 02/10/2026 car les banques écrivent souvent 0), n'est plus une erreur et n'est pas affichée dans l'aperçu : ce n'est pas une opération, son montant devient le solde d'ouverture (de clôture) du relevé et sert au contrôle « solde initial + mouvements = solde de clôture ». (2) **Pointage rempli automatiquement** : la valeur connue de la colonne Pointage du fichier l'emporte ; sinon COMMISSION, AGIOS, FRAIS, TENUE DE COMPTE → Frais bancaires, puis crédit → Encaissement, débit → Décaissement (`normalization_service.guess_pointage`). La Validation affiche la colonne Pointage. (3) La migration **0005** (données seulement) a appliqué la même règle aux 60 opérations déjà importées dont le Pointage était vide (trace dans `audit_logs`, action `remplissage_pointage`) ; son retour arrière ne vide rien. **Constat** : le relevé BP « Format_Different » importé le 02/10 a toutes ses opérations au crédit (une seule colonne Montant, en positif) alors que la colonne Solde montre des débits ; son contrôle de solde est « À vérifier ». Le format « Montant + sens » doit être traité avant de le réimporter (voir le compte rendu au métier). **Corrigé le 04/10/2026** : (1) à l'import, une colonne Montant sans aucun montant négatif, avec une colonne Solde, prend son sens dans la chaîne des soldes (`import_service._direction_from_balances`) dès que cette chaîne prouve au moins un débit ; une ligne dont le sens n'est pas prouvé passe en erreur « Sens introuvable… », jamais au crédit par défaut ; le solde précédent de la 1re ligne est le SOLDE INITIAL du fichier ; (2) la migration **0008** (données seulement) a corrigé le relevé déjà importé : 9 opérations sur 15 passées au débit (Pointage Encaissement → Décaissement, empreinte recalculée), contrôle du solde « À vérifier » → « Écart » (327 955 face au solde de 638 000 enregistré avant l'import), audit `correction_sens`.

> **Relevés modifiables — réalisé le 02/10/2026** (spécification `docs/superpowers/specs/2026-10-02-releves-modifiables-design.md`, plan `docs/superpowers/plans/2026-10-02-releves-modifiables.md`). (1) **Aperçu modifiable** : l'étape Validation montre le relevé tel qu'il sera enregistré, au format standard (Importer · État · 11 colonnes), chaque ligne se corrige (crayon, « Annuler les corrections »), revérifiée aussitôt avec les règles du serveur ; une ligne en erreur corrigée se coche ; résumé recalculé en direct ; **aucun ajout de ligne**. (2) **Enregistrement** : partie `lignes` (fichier JSON, pour dépasser la limite de 1 Mo d'un champ de formulaire) de `POST /api/statements/import/confirm` ; le serveur revérifie chaque ligne (une seule invalide ou déjà importée → rien n'est enregistré ; une ligne en erreur dans le fichier et laissée telle quelle est refusée avec ses motifs ; une ligne d'une autre banque est toujours refusée), garde l'empreinte d'origine (la même opération renvoyée par la banque reste reconnue ; une ligne en erreur corrigée prend l'empreinte de ses valeurs finales), marque `bank_transactions.origine` = `Corrigée` (migration **0006**) et trace chaque correction (`lignes_corrigees`, `lignes_fichier_non_importees`). (3) **Après l'import** : Pointage, Lettrage / Escompte et Commentaire modifiables par la Trésorerie (`PATCH /api/statements/transactions/{id}`, audit `modification_operation`) ; Comptable et Direction en lecture ; mention « corrigée avant l'import » dans le relevé continu. `GET /api/pointage-types` liste les types actifs.

**Workflow**

```text
Upload (Excel / CSV / MT940 si confirmé)
   ↓
Détection du format et des colonnes      ← modèle de mapping de la banque proposé automatiquement
   ↓
Mapping colonne source → champ standard  ← modifiable par l'utilisateur, sauvegardable
   ↓
Prévisualisation
   ↓
Contrôles  → lignes valides / lignes en erreur / doublons
   ↓
Validation utilisateur
   ↓
Normalisation + enregistrement (bank_statements, bank_transactions)
   ↓
Résumé d'import + audit
```

**Tâches — Backend**

- [ ] `ImportService` : lecture Excel (openpyxl/pandas), CSV (détection séparateur + encodage), MT940 en option
- [ ] `NormalizationService` :
  - [ ] dates → format unique ISO
  - [ ] montants → `Decimal` (gestion `,` / `.` / espaces / signe)
  - [ ] débit/crédit → sens normalisé + montant signé
  - [ ] libellé : trim, majuscules, espaces multiples, extraction de la **référence** (n° virement, n° chèque) par regex
- [ ] Contrôles : colonnes obligatoires, dates et montants valides, relevé rattaché au bon compte/banque, doublons (hash), lignes incomplètes
- [ ] Idempotence : refuser un fichier déjà importé (hash du fichier)
- [ ] Modèles de mapping par banque (`column_mappings`)
- [ ] Endpoints en 2 temps : `POST /statements/import` (analyse + aperçu) → `POST /statements/import/{batch_id}/confirm`
- [ ] Contrôle solde : solde de clôture du relevé comparé au solde enregistré → `balance_checks` (Conforme / Écart / À vérifier)

**Tâches — Frontend**

- [ ] `/releves` : bouton « + Importer un relevé », zone glisser-déposer
- [ ] Assistant en étapes : Détection → Mapping (colonne fichier → champ SIMTIS) → Validation
- [ ] Résumé : X lignes valides, Y en erreur (avec motif), Z doublons
- [ ] Historique des imports + consultation des transactions

**Livrables** : import opérationnel pour **chaque banque réelle** de P0.

**Critères de fin**

- ✅ Chaque relevé réel de P0 s'importe sans correction manuelle du fichier
- ✅ Un fichier importé 2 fois ne crée aucun doublon
- ✅ Les totaux débit/crédit importés égalent ceux du fichier source

---

### PHASE 8 — Position bancaire

**Objectif** : reproduire automatiquement la position bancaire de Salma, sans recopie Excel.

**Prérequis** : P7

> **P8.1 — Tableau Banques calculé : réalisé le 03/10/2026** (spécification `docs/superpowers/specs/2026-10-03-tableau-banques-design.md`, plan `docs/superpowers/plans/2026-10-03-tableau-banques.md`). `GET /api/position/banques?company_id=&date=` (`position.view`, sans migration). Colonnes : banques actives, compte courant MAD actif de la société. Une ligne « facilité de caisse » par jour calendaire (solde du jour + LIGNE, dernier solde connu repris), DEPASSEMENT = TOTAL − somme des LIGNES, Disponible Fc reel = ligne de la date de fin ; 10 derniers jours visibles + « Afficher plus ». La LIGNE n'est pas historisée : les jours passés utilisent la LIGNE actuelle. Aucun solde avant le 01/01/2000 (saisie refusée, ligne ignorée par le tableau) : une année mal saisie créerait sinon des milliers de lignes. Restent : P8.3 graphique, recette sur l'Excel de Salma.

> **P8.2 — Tableau détaillé par compte et filtres : abandonnée le 03/10/2026** (décision du métier : « pas besoin de ce tableau »). Ni tableau détaillé, ni filtres Banque / Compte / Devise sur la page ; le tableau Banques suffit. Les tâches « Tableau détaillé » et « filtres » ci-dessous ne sont donc pas à faire.

> **P8.3 — Graphique d'évolution : réalisé le 03/10/2026** (design validé dans la conversation, demande limitée). Carte « Évolution de la position » sous le tableau Banques : courbe en aire (teal `chart-1`, fond `light`) du TOTAL « facilité de caisse » des 30 derniers jours jusqu'à la date choisie, infobulle avec le montant exact, un jour sans TOTAL laissé vide (jamais 0). Aucune modification de l'API : mêmes données que le tableau Banques, sans second appel. Première librairie de graphiques du projet : **Recharts**. Reste pour clore P8 : la recette au centime près sur l'Excel de Salma.

> **Ajustements du 03/10/2026** (demandes du métier) : (1) Disponible Fc reel = facilité de caisse du dernier jour − LIGNE (voir §3.3) ; (2) le solde d'un jour est celui de la dernière opération importée ce jour-là, sinon le solde du jour (§3.3) ; (3) graphique : boutons TOTAL | AWB | BP…, une courbe à la fois ; (4) tableau Prévisions : Encaissement, Escompte et Douane saisis **ligne par ligne** (migration 0007, valeurs de la journée reprises sur la ligne 1) ; (5) style des trois tableaux aligné sur les autres tableaux.

**Tâches — Backend**

- [ ] `PositionService` : calcul par **compte**, par **banque** et **global**
- [ ] `GET /position?date=&bank_id=&account_id=&currency=`
- [ ] Calcul du **Dépassement** et de la **Disposition FC réel** selon les définitions de P0
- [ ] Historisation quotidienne de la position (pour le graphique d'évolution)
- [ ] Contrôles : conforme / écart / à vérifier, avec montant d'écart, commentaire de justification, date et utilisateur

**Tâches — Frontend**

- [ ] `/position-bancaire` : filtres Banque / Compte / Devise / Date / Période
- [ ] **Tableau Banques (structure imposée par `SIMTIS_tableaux_complets.xlsx`)** :

  ```text
  ┌─────────────────────────┬─────┬──────┬────┬─────┬──────┬───────┬─────────────┐
  │ Banque                  │ AWB │ BMCE │ BP │ CIH │ BMCI │ TOTAL │ DEPASSEMENT │
  │ Taux                    │     │      │    │     │      │       │             │
  │ LIGNE                   │     │      │    │     │      │       │             │
  │ facilité de caisse 28/09│     │      │    │     │      │       │             │
  │ facilité de caisse 29/09│     │      │    │     │      │       │             │
  │ facilité de caisse 30/09│     │      │    │     │      │       │             │
  │ Disponible Fc reel      │     │      │    │     │      │       │             │  ← vert > 0, autre couleur < 0
  └─────────────────────────┴─────┴──────┴────┴─────┴──────┴───────┴─────────────┘
  ```

  Colonnes de banques issues de l'API (`banks.ordre_affichage`), affichées par code. Les 3 lignes « facilité de caisse » sont des **dates** (historique `bank_account_balances`). Ne pas renommer, ajouter, supprimer ni déplacer de colonnes ; ne pas remplacer par des cartes. Une société à la fois.
- [ ] Tableau détaillé : Banque, Compte, Devise, Solde, Crédit autorisé, Crédit utilisé, Crédit disponible, Position disponible, Dépassement, Date de mise à jour
- [ ] Graphique d'évolution de la position

**Livrables** : position bancaire calculée automatiquement.

**Critères de fin**

- ✅ Sur les données réelles de P0, la position calculée égale **au centime près** celle de l'Excel de Salma
- ✅ Exemple CDC vérifié en test : solde 300 000, autorisé 500 000, utilisé 100 000 → crédit disponible 400 000 → position 700 000

---

### PHASE 9 — Gestion des devises

**Objectif** : suivre les soldes par devise sans jamais mélanger les monnaies.

**Prérequis** : P8

**Tâches**

- [ ] Référentiel `currencies` + `exchange_rates` (saisie manuelle ou import des taux)
- [ ] Conversion MAD : montant d'origine + taux + date du taux **toujours conservés**
- [ ] Totaux par devise ; total consolidé MAD en option
- [ ] Traitement du **compte RH convertible** selon la définition de P0
> **P9 — en partie réalisée le 05/10/2026** (décision du métier) : les lignes **EUR** et **USD** du tableau Devises affichent les **soldes des comptes courants EUR / USD** de la société, dans leur devise, **sans conversion** (`GET /api/position/devises/soldes`, même règle de solde que le tableau Banques, dernier solde connu grisé) ; TOTAL = somme de la devise, DEPASSEMENT vide ; la ligne Exp DH convertible reste saisie à la main. Pas de tableau Devises pour une société sans compte EUR, USD ni DH convertible (Tefil). La conversion MAD et le référentiel des taux ne sont pas demandés pour ce tableau.

- [ ] ~~`/devises`~~ **sur `/position-bancaire`** (page `/devises` supprimée le 05/10/2026, décision du métier) — **tableau selon `SIMTIS_tableaux_complets.xlsx`** : lignes **EUR**, **USD**, **Exp DH convertible**, sur les mêmes colonnes de banques (cellules grisées) avec TOTAL et DEPASSEMENT ; aucune colonne supplémentaire. Contenu exact des cellules : à confirmer (§3.4)
- [ ] Le détail (montant, taux, équivalent MAD, date) reste disponible en infobulle ou en vue détail, pour la traçabilité, sans modifier le tableau principal

**Critères de fin**

- ✅ Aucune somme directe entre devises différentes (test)
- ✅ Chaque équivalent MAD affiche son taux et sa date

---

### PHASE 10 — Import Sage / SI & tableau des écritures comptables

**Objectif** : récupérer les écritures comptables déjà réalisées pour les rapprocher. Sage/SI reste la référence.

> **P10 — Statut : réalisé le 05/10/2026** (spécification `docs/superpowers/specs/2026-10-05-import-sage-design.md`, plan `docs/superpowers/plans/2026-10-05-import-sage.md`). Décisions du 05/10/2026 : une écriture est rattachée à son compte bancaire par le **code journal Sage** (champ « Journal Sage » de chaque compte, migration **0010**, un compte actif par journal et par société) ; seules les **lignes banque des journaux de banque** sont importées (compte qui commence par le compte comptable du compte bancaire, ex. 5141) — contreparties et autres journaux ignorés ; un fichier = une société, plusieurs banques ; **aucune correction** dans SIMTIS (une ligne en erreur se corrige dans Sage ou s'écarte). API : `POST /api/accounting/import/analyse` et `/confirm` (`accounting.import`), `GET /api/accounting/entries` (50 par page, filtres compte / dates / statut / recherche, totaux sur tout le filtre), `/entries/{id}`, `/imports`. Page `/ecritures` : assistant Fichier → Validation (lecture seule), liste paginée, détail, journal des imports. Lecture du classeur commune aux relevés (`services/import_file.py`). Aucun export Sage réel disponible : format standard du CDC ; la recette (export réel, totaux identiques à Sage) reste à faire.

**Prérequis** : P7 (réutilise le moteur d'import et de mapping)

**Tâches — Backend**

- [ ] `AccountingImportService` : même workflow que P7 (upload → mapping → contrôles → aperçu → confirmation)
- [ ] Champs : Date, Journal, Compte, Libellé, Référence, Débit, Crédit, Montant, **N° pièce**, **Échéance**, Tiers, Facture, Source
- [ ] Filtrage sur les comptes de trésorerie (ex. 512xxx) liés aux comptes bancaires
- [ ] Contrôles : lignes invalides, doublons potentiels, champs obligatoires manquants
- [ ] Endpoints : `POST /accounting/import`, `POST /accounting/import/{id}/confirm`, `GET /accounting/entries` (filtres, recherche, pagination)
- [ ] Évolution possible : connexion directe (ODBC/API) si confirmée en P0

**Tâches — Frontend**

- [ ] `/ecritures` : tableau filtrable (date, journal, compte, statut, montant), recherche, détail d'une écriture, statut de rapprochement

**Critères de fin**

- ✅ L'export Sage réel de P0 s'importe intégralement
- ✅ Totaux débit/crédit identiques à Sage

---

### PHASE 11 — Rapprochement bancaire 1→1 : moteur, scoring, validation manuelle

**Objectif** : proposer automatiquement les correspondances banque ↔ comptabilité et les faire valider par un utilisateur autorisé.

**Prérequis** : P7, P10

**Critères de comparaison** : montant, date, libellé, référence, sens débit/crédit, n° chèque, n° pièce, tiers.

**Grille de scoring (paramétrable dans `reconciliation_rules`)**

| Critère | Points |
|---|---|
| Référence / n° chèque / n° pièce identique | +40 |
| Montant exact (et même sens) | +30 |
| Date dans la tolérance (ex. ± 3 jours, dégressif) | +15 |
| Libellé similaire (similarité textuelle) | +10 |
| Tiers correspondant | +5 |
| **Total** | **100** |

| Score | Classement |
|---|---|
| 90 – 100 | Forte correspondance → proposée « Rapprochée », **confirmation humaine requise** |
| 70 – 89 | Probable → « À vérifier » |
| 50 – 69 | Faible → « À vérifier » |
| < 50 | « Non rapprochée » |

> Si plusieurs candidats ont un score proche (ambiguïté), **aucune proposition automatique** : la ligne passe en « À vérifier ».

**Tâches — Backend**

- [ ] `ReconciliationService.run(période, comptes)` : génère les propositions dans `reconciliation_matches` et `reconciliation_match_items`
- [ ] Performance : pré-filtrage par compte, sens et fenêtre de dates avant le scoring
- [ ] Endpoints : `POST /reconciliation/run`, `GET /reconciliation/proposals`, `POST /reconciliation/matches/{id}/validate`, `POST /reconciliation/matches/{id}/reject`, `POST /reconciliation/matches` (rapprochement manuel), `DELETE /reconciliation/matches/{id}` (annulation tracée)
- [ ] Mise à jour des statuts des transactions et écritures ; audit de chaque décision

**Tâches — Frontend**

- [ ] `/rapprochement` en 2 volets : **Transactions bancaires** (Date, Libellé, Débit, Crédit) | **Écritures comptables** (Date, Libellé, Débit, Crédit, N° pièce, Échéance)
- [ ] Panneau central « Correspondance proposée » avec score et détail des critères
- [ ] Actions : Valider, Refuser, Choisir une autre écriture, Rapprocher manuellement
- [ ] Filtres, recherche, statut, pagination, sélection multiple, validation en lot des scores ≥ 90

**Critères de fin**

- ✅ Exemple de l'architecture fonctionnelle : banque 50 000 MAD le 24/09 « VIR ABC » ↔ compta 50 000 MAD le 24/09 « Règlement ABC » pièce REG458 → proposé, puis validé par l'utilisateur
- ✅ Sur un mois réel de Mustapha : taux de propositions correctes mesuré et accepté

---

### PHASE 12 — Gestion des écarts

**Objectif** : centraliser et suivre tout ce qui n'est pas rapproché.

**Prérequis** : P11

**Types d'écarts**

| Type | Exemple | Traitement |
|---|---|---|
| Banque sans écriture | Frais bancaires non comptabilisés | Identifier / traiter |
| Écriture sans banque | Chèque émis non débité | Suivre / attendre |
| Montant différent | 12 500 banque / 12 450 compta | Analyser, justifier |
| Date différente | Dates différentes entre systèmes | Appliquer la tolérance |
| Libellé ambigu | Référence insuffisante | Validation manuelle |
| Doublon potentiel | Même opération importée 2 fois | Vérifier |

**Tâches**

- [ ] Création automatique des écarts à l'issue du rapprochement + création manuelle
- [ ] Champs : type, transaction, écriture, montant, différence, date, responsable, statut, commentaire, date de traitement
- [ ] Cycle de vie : **À traiter → En cours → Traité → Clôturé** ; la clôture exige un commentaire, avec responsable et date/heure tracés
- [ ] Endpoints : `GET /discrepancies`, `PATCH /discrepancies/{id}`, `POST /discrepancies/{id}/close`
- [ ] `/ecarts` : KPI (À traiter, En cours, Clôturés, Montant total) + tableau + panneau latéral de détail et de traitement

**Critères de fin**

- ✅ Chaque ligne non rapprochée a un écart ou un statut explicite
- ✅ Historique complet de chaque écart

---

###(sauter pour le moment) PHASE 13 — Rapprochement avancé 1→N, N→1, N→N

**Objectif** : couvrir les cas obligatoires du CDC : virement global, paiements fractionnés, règlements groupés.

**Prérequis** : P11, P12

**Tâches**

- [ ] **1→N** : 1 transaction = somme de plusieurs écritures (virement global) → recherche de combinaisons dont la somme égale le montant (subset-sum borné : même compte, fenêtre de dates, nombre max d'éléments)
- [ ] **N→1** : plusieurs transactions = 1 écriture (paiements fractionnés)
- [ ] **N→N** : règlement groupé, en **manuel assisté** d'abord (sélection multiple + contrôle que les sommes s'équilibrent)
- [ ] Garde-fous : limite de combinatoire, timeout, jamais de validation automatique
- [ ] UI : sélection multiple des deux côtés, affichage de la somme et de l'écart restant en temps réel

**Critères de fin**

- ✅ Les 4 cas du CDC testés avec des exemples réels
- ✅ Le moteur répond en moins de quelques secondes sur un mois de données réelles

---

### PHASE 14 — Prévisions & position prévisionnelle

**Objectif** : passer de la situation actuelle à une vision future de la trésorerie.

**Prérequis** : P8

**Catégories** : Encaissement · Escompte · Douane · Paie · Refinancement · Chèques · Autre
**Statuts** : Prévu · En attente · Réalisé · Reporté · Annulé (conservé dans l'historique)

**Tâches — Backend**

- [ ] `ForecastService` : CRUD des prévisions (compte, catégorie, libellé, date, montant, devise, statut)
- [ ] Calcul en cascade :

  ```text
  Jour J   : Position de départ = position actuelle (P8)
  Jour J+1 : Position de départ = position prévisionnelle de J
  Position prévisionnelle = départ + encaissements prévus − décaissements prévus
  ```

- [ ] Vues : jour / semaine / mois, par banque, compte, devise, catégorie, statut
- [ ] **Prévu vs réalisé** : rapprochement d'une prévision avec une transaction bancaire réelle
- [ ] Report : changement de date tracé (ancienne et nouvelle valeur dans l'audit)
- [ ] Endpoints : `GET/POST/PUT /forecasts`, `GET /forecasts/projection?from=&to=&granularity=`

**Tâches — Frontend**

- [ ] ~~`/previsions`~~ **sur `/position-bancaire`** (page `/previsions` supprimée le 05/10/2026, décision du métier) : KPI (Position actuelle, Encaissements prévus, Décaissements prévus, Position future) + bouton « + Nouvelle prévision »
- [ ] **Tableau Prévisions (structure imposée par `SIMTIS_tableaux_complets.xlsx`)** :

  ```text
  ┌────────────┬──────────┬─────┬──────┬────┬─────┬──────┬──────────────┬──────────┬────────┐
  │ 30/09/2026 │ date     │ AWB │ BMCE │ BP │ CIH │ BMCI │ Encaissement │ Escompte │ Douane │
  │ (une seule │ (14      │     montants par banque    │ 1 cellule fusionnée par colonne   │
  │ cellule    │ lignes)  │                            │ pour tout le bloc                 │
  │ fusionnée) │          │                            │                                   │
  └────────────┴──────────┴────────────────────────────┴───────────────────────────────────┘
  ```

  Une seule colonne Date à gauche (`rowSpan`) ; ne pas créer de colonnes par date. Encaissement, Escompte et Douane = montants de la journée (prévisions sans banque). Contenu exact de la 2ᵉ colonne à confirmer (§3.4).
- [ ] Graphique combiné : encaissements (barres turquoise), décaissements (barres teal foncé), position prévisionnelle (ligne)

**Critères de fin**

- ✅ La projection sur le tableau réel de P0 égale le calcul manuel
- ✅ Chaque modification de prévision est tracée (avant / après)

---

### PHASE 15 — Dashboard, KPI & alertes

**Objectif** : donner en un coup d'œil la santé de la trésorerie. Le dashboard vient après les modules, pour afficher des données fiables.

**Prérequis** : P8, P11, P12, P14

**Tâches**

- [ ] `GET /dashboard/kpis?from=&to=` agrégeant les services existants (aucun calcul dupliqué)
- [ ] Mise en page conforme à la maquette :
  - En-tête « Dashboard » + sous-titre + sélecteur de période
  - **4 KPI** : Total soldes bancaires · Crédit disponible · Position disponible · Opérations rapprochées (avec donut %) — chacun avec sa variation vs le mois précédent
  - **Position bancaire par banque** (tableau + ligne Total) + **Répartition des soldes** (donut)
  - **Transactions récentes** + **Statut du rapprochement** (donut : Rapprochées, À vérifier, Non rapprochées, Écarts)
  - **Prévisions de trésorerie** (graphique combiné) + **Écarts à traiter** (tableau avec badges)
- [ ] **Alertes** (centre de notifications du header) :
  - position prévisionnelle sous un seuil
  - décaissement important à venir
  - refinancement proche de l'échéance
  - chèque important attendu au débit
  - écart entre prévision et réalisation
  - dépassement de ligne de crédit
- [ ] Seuils d'alerte paramétrables
- [ ] États : chargement (skeletons), vide, erreur + « Réessayer »

**Critères de fin**

- ✅ Le dashboard répond aux 7 questions UX : position, disponible, crédit disponible, taux de rapprochement, écarts, position future, actions à mener
- ✅ Les KPI du dashboard égalent ceux des pages détaillées

---

### PHASE 16 — Administration, historique & rapports

**Objectif** : donner à l'administrateur la gestion dynamique des accès et exposer la traçabilité.

**Prérequis** : P5

**Tâches**

- [ ] `/administration` : utilisateurs (créer, modifier, activer, désactiver, réinitialiser le mot de passe), rôles, permissions (matrice éditable), profil « Personnalisé »
- [ ] Paramètres : tolérances de rapprochement, poids du scoring, seuils d'alertes, modèles de mapping
- [ ] `/historique` : journal d'audit filtrable (utilisateur, action, entité, période), affichage avant / après
  ```text
  28/09/2026 14:30 — Mustapha — Validation rapprochement
  Banque : VIR-45821 — 50 000 DH — À vérifier → Rapprochée
  ```
- [ ] `/rapports` : exports Excel/PDF (position du jour, état de rapprochement, écarts ouverts, prévisions)
- [ ] Audit obligatoire (CDC §11) : import de relevé, validation de rapprochement, modification de prévision (avant/après), modification de rôle ou de permission, clôture d'écart

**Critères de fin**

- ✅ Toutes les actions sensibles listées ci-dessus apparaissent dans l'historique
- ✅ Un changement de permission s'applique sans redéploiement

---

### PHASE 17 — Tests (unitaires, intégration, métier)

**Objectif** : garantir l'exactitude des calculs et la robustesse des traitements. Les tests unitaires s'écrivent **dans chaque phase** ; cette phase complète la couverture transverse.

**Tâches**

- [ ] **Unitaires** : formules (crédit disponible, position, dépassement, position prévisionnelle, conversion devises), normalisation (dates, montants, signes), scoring, détection de doublons
- [ ] **Intégration API** : chaque endpoint avec base de test, codes 401/403, validations Pydantic
- [ ] **Scénarios métier** :
  - [ ] rapprochement 1→1, 1→N, N→1, N→N
  - [ ] montant différent, date différente, référence différente, transaction inconnue, doublon
  - [ ] fichier importé deux fois, fichier mal formé, banque inconnue
- [ ] **Non-régression** : jeu de fichiers réels anonymisés avec résultats attendus figés
- [ ] **End-to-end** (Playwright) : import → position → rapprochement → écart → dashboard
- [ ] **Performance** : import d'un gros relevé, rapprochement sur un mois complet
- [ ] **Sécurité** : injection, accès sans droits, upload de fichiers malveillants

**Critères de fin**

- ✅ Couverture ≥ 80 % sur `services/`
- ✅ 100 % des formules métier testées
- ✅ CI verte

---

### PHASE 18 — Recette sur données réelles & validation utilisateurs

**Objectif** : les tests de développement ne suffisent pas. Le métier valide sur **ses** données.

**Prérequis** : P17

**Tâches**

- [ ] Environnement de recette alimenté avec 1 à 3 mois de données réelles
- [ ] **Exécution en parallèle** : pendant 2 à 4 semaines, Salma et Mustapha continuent sur Excel ET utilisent SIMTIS ; les résultats sont comparés chaque jour
- [ ] Sessions de recette par profil :

  | Utilisateur | Périmètre à valider |
  |---|---|
  | Salma (Trésorerie) | Banques, relevés, position, devises, prévisions |
  | Mustapha (Comptabilité) | Écritures, rapprochement, écarts |
  | Responsable Finance | Validations, supervision, KPI |
  | Direction | Dashboard, reporting |

- [ ] Suivi des anomalies, corrections, nouvelle recette
- [ ] Vérification des **critères d'acceptation du CDC** (section 5 ci-dessous)

**Livrables** : cahier de recette exécuté, rapport de validation fonctionnelle, **procès-verbal de recette signé**.

**Critères de fin**

- ✅ Position SIMTIS = position Excel sur toute la période parallèle
- ✅ Rapprochements jugés cohérents par Mustapha
- ✅ PV signé par le métier

---

### PHASE 19 — Déploiement Docker & mise en production

**Objectif** : livrer une application exploitable et sécurisée.

**Prérequis** : P18

**Tâches**

- [ ] Images Docker de production (multi-stage, non-root) : `frontend`, `backend`, `db`
- [ ] `docker-compose.prod.yml` + reverse proxy (Nginx/Traefik) avec **HTTPS**
- [ ] Secrets en variables d'environnement (jamais dans Git), `.env.example` à jour
- [ ] **Sauvegardes PostgreSQL** automatiques (quotidiennes, rétention, copie hors serveur) + **test de restauration**
- [ ] Logs centralisés, monitoring (santé des services, erreurs, espace disque)
- [ ] Migrations appliquées automatiquement au déploiement
- [ ] Checklist avant ouverture :
  - [ ] sauvegardes testées
  - [ ] rôles et comptes utilisateurs vérifiés, admin par défaut désactivé
  - [ ] imports validés sur la production
  - [ ] rapprochements et dashboard vérifiés
  - [ ] accès testés par profil
  - [ ] performances vérifiées
- [ ] Formation des utilisateurs + guide utilisateur par profil
- [ ] Reprise des données historiques si nécessaire

**Livrables** : application en production, documentation d'exploitation, guide utilisateur.

**Évolution possible** : Redis ou un worker asynchrone (Celery/RQ) si les imports ou le rapprochement deviennent volumineux. Ce n'est pas nécessaire pour le MVP.

---

### PHASE 20 — Exploitation, support & évolutions

**Tâches**

- [ ] Période d'hypercare (2 à 4 semaines) : support rapproché, corrections rapides
- [ ] Arrêt officiel des fichiers Excel remplacés, avec l'accord du métier
- [ ] Suivi des indicateurs : taux de rapprochement automatique, temps de traitement, écarts ouverts
- [ ] Backlog d'évolutions : connexion directe Sage/API, import MT940, alertes e-mail, reporting avancé, multi-sociétés, application mobile

---

## 5. Critères d'acceptation globaux (Cahier des charges §13)

| Domaine | Critère | Phase |
|---|---|---|
| Relevés | Import d'un fichier réel et transformation vers la structure standard | P7 |
| Rapprochement banque | Date, libellé, débit, crédit disponibles | P7 / P11 |
| Comptabilité | Date, libellé, débit, crédit, N° pièce, échéance disponibles | P10 |
| Position | Soldes multi-banques et crédits disponibles correctement calculés | P8 |
| Devises | EUR, USD et autres devises séparées et convertibles | P9 |
| Rapprochement | 1→1, 1→N, N→1, N→N | P11 / P13 |
| Validation | Acceptation, refus et correction par un utilisateur autorisé | P11 |
| Écarts | Statut, responsable, montant, commentaire et historique | P12 |
| Prévisions | Encaissement, escompte, douane, paie, refinancement, chèques et autres flux par date | P14 |
| Dashboard | Situation actuelle + rapprochement + écarts + prévisions | P15 |
| Audit | Actions sensibles historisées | P5 / P16 |

---

## 6. Découpage MVP / Version complète

### MVP (jalon J4, environ 13 à 17 semaines)

| Inclus | Phases |
|---|---|
| Cadrage + modèle validé | P0 – P2 |
| Socle technique, Design System, BDD, authentification et rôles de base | P3 – P5 |
| Banques & comptes | P6 |
| Import des relevés (formats des banques réelles) | P7 |
| Position bancaire + tableau Banques | P8 |
| Import Sage/SI + écritures | P10 |
| Rapprochement **1→1** + validation manuelle | P11 |
| Écarts simples | P12 |
| Dashboard de base (KPI position + rapprochement) | P15 (partiel) |

### Version complète

- Devises complètes (P9) si non nécessaire au MVP
- Rapprochement 1→N, N→1, N→N (P13)
- Prévisions et position prévisionnelle (P14)
- Dashboard complet + alertes (P15)
- Administration dynamique complète, historique, rapports (P16)

---

## 7. Risques principaux

| Risque | Impact | Mitigation |
|---|---|---|
| Fichiers réels non fournis ou tardifs | Bloquant | P0 en préalable strict ; pas de règle définitive sans fichiers |
| Termes métier mal compris (Taux, Ligne, FC réel…) | Calculs faux | Glossaire signé en P0 |
| Formats bancaires changeants | Imports cassés | Modèles de mapping éditables par l'utilisateur |
| Accès Sage/SI limité | Import manuel uniquement | Démarrer par l'export fichier ; API en évolution |
| Faux rapprochements automatiques | Erreurs comptables | Validation humaine obligatoire + scoring + audit |
| Erreurs d'arrondi | Écarts fictifs | `Decimal` / `NUMERIC` partout |
| Faible adoption | Retour à Excel | Recette en parallèle, formation, UI fidèle aux maquettes |
| Perte de données | Critique | Sauvegardes automatiques + tests de restauration |

---

## 8. Récapitulatif

```text
P0  Cadrage & fichiers réels          →  Glossaire + règles validées
P1  Analyse des fichiers              →  Dictionnaire de données
P2  Modèle standard                   →  MCD + formules + états
P3  Init technique + Design System    →  Squelette Docker + UI SIMTIS
P4  PostgreSQL                        →  Schéma + migrations + seeds
P5  Sécurité & audit (socle)          →  JWT + RBAC + audit_logs
P6  Banques & comptes                 →  Référentiel bancaire
P7  Import relevés                    →  Transactions normalisées
P8  Position bancaire                 →  Position automatisée       ★ J3
P9  Devises                           →  Soldes par devise + MAD
P10 Import Sage/SI                    →  Écritures disponibles
P11 Rapprochement 1→1                 →  Matching + validation
P12 Écarts                            →  Suivi des anomalies         ★ J4 MVP
P13 Rapprochement avancé              →  1→N, N→1, N→N
P14 Prévisions                        →  Position future
P15 Dashboard & alertes               →  Pilotage
P16 Administration & historique       →  Traçabilité complète        ★ J5
P17 Tests                             →  Qualité garantie
P18 Recette données réelles           →  PV signé
P19 Production                        →  Application en ligne        ★ J6
P20 Exploitation                      →  Support + évolutions
```

> **Conclusion** : SIMTIS doit automatiser la méthode réellement utilisée par la Trésorerie et la Comptabilité, sans imposer une nouvelle logique métier non validée.
> La première étape reste la récupération et l'analyse des fichiers réels de Salma et Mustapha.
