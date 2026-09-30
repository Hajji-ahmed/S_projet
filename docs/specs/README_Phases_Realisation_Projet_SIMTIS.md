# SIMTIS - README des phases de réalisation du projet

## 1. Contexte du projet

SIMTIS est une plateforme de gestion financière et de trésorerie destinée à centraliser :

- les soldes bancaires ;
- les comptes bancaires ;
- les relevés bancaires ;
- les écritures comptables issues de Sage / SI ;
- le rapprochement entre les mouvements bancaires et les écritures ;
- les écarts et anomalies ;
- les prévisions de trésorerie ;
- les indicateurs de pilotage et le dashboard.

Le projet vise à remplacer progressivement le travail manuel réalisé dans Excel, en automatisant le traitement des données, en normalisant les imports et en améliorant le contrôle des positions et des rapprochements.

La cible technique proposée est :

- Frontend : Next.js
- Backend : FastAPI
- Base de données : PostgreSQL
- Conteneurisation : Docker / Docker Compose

---

## 2. Objectif principal du projet

SIMTIS doit permettre à la finance et à la comptabilité de :

1. importer les relevés bancaires ;
2. normaliser les données malgré les différences de format entre banques ;
3. calculer la position bancaire ;
4. importer les écritures comptables ;
5. rapprocher les mouvements bancaires et les écritures comptables ;
6. détecter les écarts ;
7. garder un historique de chaque validation ;
8. sécuriser l’accès via utilisateurs, rôles et permissions ;
9. fournir un dashboard de pilotage et des prévisions de trésorerie.

---

## 3. Vue d’ensemble des phases

```text
PHASE 0  -> Comprendre le fonctionnement réel du processus
PHASE 1  -> Analyser les fichiers et les données existants
PHASE 2  -> Définir le modèle de données standard
PHASE 3  -> Concevoir l’architecture technique
PHASE 4  -> Mettre en place la base PostgreSQL
PHASE 5  -> Développer le module Banques et comptes
PHASE 6  -> Créer l’import et la normalisation bancaire
PHASE 7  -> Développer la Position Bancaire
PHASE 8  -> Importer les écritures Sage / SI
PHASE 9  -> Créer le tableau des écritures comptables
PHASE 10 -> Développer le rapprochement bancaire
PHASE 11 -> Ajouter le moteur de matching et le scoring
PHASE 12 -> Gérer les écarts et les validations manuelles
PHASE 13 -> Ajouter l’historique et l’audit
PHASE 14 -> Gérer les utilisateurs, rôles et permissions
PHASE 15 -> Développer les prévisions et le dashboard
PHASE 16 -> Réaliser les tests unitaires et métier
PHASE 17 -> Valider avec les données réelles du projet
PHASE 18 -> Déployer en Docker et préparer la production
PHASE 19 -> Mettre en production avec sécurité et monitoring
```

---

## 4. Phases détaillées

### PHASE 0 — Comprendre le fonctionnement réel

Cette phase est la plus importante. Avant de développer, il faut comprendre le flux actuel utilisé par les personnes qui gèrent la trésorerie et la comptabilité.

#### Objectifs

- identifier les fichiers Excel actuellement utilisés ;
- comprendre la logique de calcul de la position bancaire ;
- obtenir les relevés bancaires réels ou anonymisés ;
- comprendre la logique de rapprochement de Mustapha ;
- récupérer les exports Sage / SI réels ;
- documenter les règles métier de validation.

#### Délivrables attendus

- fichier de position bancaire actuel ;
- fichier de rapprochement bancaire actuel ;
- relevés bancaires par banque ;
- export Sage / SI ;
- liste des personnes responsables ;
- règles métier décrites et validées.

#### Questions à clarifier

- quelles banques sont utilisées ?
- quels comptes sont suivis ?
- quels soldes sont pris en compte ?
- comment sont calculés le crédit disponible et la position disponible ?
- comment décide-t-on qu’une opération est rapprochée ?
- quelles sont les exceptions métier ?

---

### PHASE 1 — Analyse des fichiers et des données

Après la compréhension du processus, on étudie les fichiers de manière technique.

#### Objectifs

- repérer les colonnes présentes ;
- identifier les colonnes obligatoires ;
- vérifier les formats de dates et montants ;
- repérer les doublons et lignes vides ;
- identifier les colonnes non standard selon la banque ;
- analyser les différences entre relevés bancaires et écritures comptables.

#### Exemples de données à analyser

- date d’opération ;
- date de valeur ;
- libellé ;
- référence ;
- débit ;
- crédit ;
- solde ;
- compte bancaire ;
- devise ;
- n° pièce ;
- tiers ;
- facture ;
- commentaire.

#### Livrable

- dictionnaire des données ;
- schéma des colonnes ;
- règles de validation des fichiers ;
- liste des écarts de format entre banques.

---

### PHASE 2 — Définir le modèle standard des données

L’objectif est de normaliser les données de manière uniforme, quel que soit l’origine : banque, Excel, Sage, SI.

#### Idée centrale

Les données bancaires et comptables doivent être converties dans un modèle standard interne avant traitement.

#### Exemple de structure standard

```text
BankTransaction
- id
- bank_id
- account_id
- date_operation
- date_valeur
- date_comptable
- libelle
- reference
- debit
- credit
- montant
- solde
- source
- import_id
- status
- created_at
```

#### Exemple de structure comptable

```text
AccountingEntry
- id
- journal
- date
- account
- libelle
- reference
- debit
- credit
- montant
- numero_piece
- tiers
- facture
- source
- status
```

#### Résultat attendu

Une structure commune pour faciliter :

- l’import ;
- le stockage ;
- le rapprochement ;
- l’audit ;
- le reporting.

---

### PHASE 3 — Concevoir l’architecture technique

On pose la base technique de la solution.

#### Stack proposée

- Frontend : Next.js
- Backend : FastAPI
- Base de données : PostgreSQL
- Conteneurs : Docker / Docker Compose
- Contrôle de version : Git

#### Structure logique du projet

```text
simtis/
├── frontend/
├── backend/
├── database/
├── docker-compose.yml
├── .env.example
├── README.md
└── docs/
```

#### Objectif

- créer une architecture claire ;
- séparer les responsabilités entre interface, logique métier et données ;
- préparer le projet pour les développements successifs.

---

### PHASE 4 — Mettre en place la base PostgreSQL

Le cœur du projet repose sur une base de données relationnelle robuste.

#### Tables principales

- banks
- bank_accounts
- bank_statements
- bank_transactions
- accounting_entries
- reconciliation_matches
- reconciliation_rules
- discrepancies
- forecasts
- users
- roles
- permissions
- user_roles
- role_permissions
- audit_logs

#### Relations importantes

- Une banque a plusieurs comptes ;
- un compte a plusieurs relevés ;
- un relevé contient plusieurs mouvements ;
- un mouvement bancaire peut être rapproché avec plusieurs écritures ;
- chaque rapprochement doit être historisé et auditable.

#### Livrable

- schéma PostgreSQL validé ;
- migrations créées ;
- données de test chargées.

---

### PHASE 5 — Développer le module Banques et comptes

#### Objectif

Créer la base métier permettant de gérer les banques et les comptes bancaires.

#### Fonctionnalités

- ajouter une banque ;
- modifier une banque ;
- activer / désactiver une banque ;
- créer un compte bancaire ;
- lier un compte à sa banque ;
- enregistrer la devise ;
- définir le solde ;
- définir le crédit autorisé ;
- calculer le crédit utilisé ;
- calculer le crédit disponible.

#### Exemples de données

- Attijari ;
- BMCE ;
- CIH ;
- Société Générale ;
- compte principal ;
- devise MAD ;
- solde ;
- limite de crédit.

#### Livrable

Module Banques opérationnel et utilisable dans l’interface.

---

### PHASE 6 — Développer l’import et la normalisation des relevés bancaires

C’est la première vraie automatisation du travail Excel.

#### Objectif

Importer les fichiers bancaires, les valider et les convertir dans le modèle standard.

#### Workflow

```text
Upload Excel / CSV
   ↓
Détection des colonnes
   ↓
Mapping des colonnes
   ↓
Prévisualisation des données
   ↓
Validation des règles
   ↓
Normalisation
   ↓
Enregistrement en base
```

#### Contrôles à prévoir

- colonnes obligatoires présentes ;
- format des dates correct ;
- montant valide ;
- relevé appartenant à la bonne banque ;
- doublons détectés ;
- lignes avec données manquantes signalées ;
- libellé standardisé ;
- montant converti selon le bon sens débit / crédit.

#### Livrable

Premier import bancaire fonctionnel avec visualisation des erreurs avant validation.

---

### PHASE 7 — Développer la Position Bancaire

C’est le premier objectif métier fort du projet.

#### Objectif

Reproduire automatiquement la logique de position bancaire utilisée aujourd’hui.

#### Calculs métier

Crédit disponible :

```text
Crédit disponible = Crédit autorisé - Crédit utilisé
```

Position disponible :

```text
Position disponible = Solde bancaire + Crédit disponible
```

#### Exemple

```text
Solde bancaire : 1 000 000 DH
Crédit autorisé : 500 000 DH
Crédit utilisé : 200 000 DH
Crédit disponible : 300 000 DH
Position disponible : 1 300 000 DH
```

#### Résultat attendu

- vue par banque ;
- vue par compte ;
- vue globale ;
- tableau de synthèse ;
- comparaison avec les calculs manuels de l’existant.

#### Livrable

Position bancaire calculée automatiquement, sans recopie manuelle sur Excel.

---

### PHASE 8 — Importer les écritures Sage / SI

#### Objectif

Récupérer les écritures comptables de la comptabilité pour les comparer aux mouvements bancaires.

#### Ce qu’on doit faire

- importer les fichiers exportés de Sage / SI ;
- normaliser les colonnes ;
- enregistrer les écritures dans une table dédiée ;
- conserver la source de l’écriture ;
- repérer les pièces, tiers, factures, journaux.

#### Données à stocker

- date ;
- journal ;
- compte ;
- libellé ;
- référence ;
- débit ;
- crédit ;
- montant ;
- n° pièce ;
- tiers ;
- facture ;
- source.

#### Point important

L’application ne remplace pas la comptabilité. Elle exploite les données existantes pour contrôler et rapprocher.

---

### PHASE 9 — Créer le tableau des écritures comptables

#### Objectif

Mettre en place un tableau structurée qui centralise les écritures comptables importées.

#### Exemple de vue

```text
ID : ECR-00125
Date : 25/09/2026
Journal : BQ
Compte : 512000
Libellé : VIR CLIENT ABC
Référence : VIR45821
Débit : 0
Crédit : 50 000
Montant : 50 000
N° pièce : PC-458
Tiers : ABC
Facture : FAC-1025
Source : Sage
Statut : Rapprochée
```

#### Ce que cette table permet

- filtrer ;
- rechercher ;
- comparer ;
- associer à une transaction bancaire ;
- tracer les changements d’état ;
- suivre les rapprochements réussis ou en attente.

---

### PHASE 10 — Développer le rapprochement bancaire

C’est la deuxième grande étape clé après la position bancaire.

#### Objectif

Comparer les transactions bancaires et les écritures comptables pour détecter les correspondances.

#### Sources à comparer

```text
Transactions bancaires + Écritures comptables
      ↓
Moteur de rapprochement
```

#### Critères de rapprochement

- montant ;
- date ;
- libellé ;
- référence ;
- tiers ;
- sens débit / crédit ;
- n° pièce ;
- numéro de chèque / virement.

#### Cas de matching à traiter

- 1 → 1
- 1 → N
- N → 1
- N → N

#### Valeurs de statut

- Rapprochée
- À vérifier
- Non rapprochée
- Écart

---

### PHASE 11 — Ajouter le moteur de matching avec score

Le moteur de rapprochement ne doit pas se baser sur un seul critère, surtout le montant.

#### Score de rapprochement

Exemple :

- référence exacte : +40
- montant exact : +30
- date proche : +15
- libellé similaire : +10
- tiers correspondant : +5

Total possible : 100

#### Seuils types

- 90–100 : Forte correspondance
- 70–89 : Probable
- 50–69 : À vérifier
- <50 : Non rapprochée

#### Règle importante

Une correspondance ambiguë ne doit pas être validée automatiquement uniquement parce que le montant est identique.

---

### PHASE 12 — Validation manuelle et gestion des exceptions

Tous les cas douteux doivent être soumis à un contrôle humain.

#### Workflow de validation

```text
Écart ou correspondance faible
   ↓
Affichage côte à côte Banque / Sage
   ↓
Validation manuelle
   ↓
Valider / Refuser / Choisir une autre écriture / Créer une écriture
```

#### Interface d’assistance

L’utilisateur voit :

- date banque ;
- date comptable ;
- libellé ;
- montant ;
- référence ;
- statut actuel.

#### Cas à traiter

- commission bancaire sans écriture ;
- écriture comptable sans transaction bancaire ;
- montant different ;
- référence non identique ;
- date différente ;
- doublon potentiel.

---

### PHASE 13 — Gérer les écarts, les doublons et les anomalies

#### Objectif

Suivre les éléments qui ne sont ni validés ni rapprochés.

#### Types d’écarts

- transaction sans écriture ;
- écriture sans transaction ;
- montant différent ;
- date différente ;
- référence différente ;
- transaction inconnue ;
- doublon potentiel.

#### Champs attendus

- type d’écart ;
- transaction concernée ;
- écriture concernée ;
- montant ;
- date ;
- responsable ;
- statut ;
- commentaire ;
- date traitement.

#### Livrable

Une vraie page “Écarts” avec traitement et suivi.

---

### PHASE 14 — Historique du rapprochement et audit

L’historique est indispensable pour le contrôle et la traçabilité.

#### Ce qu’on doit suivre

- import des données ;
- correspondance détectée ;
- score calculé ;
- validation manuelle ;
- rapprochement final ;
- annulation de rapprochement ;
- changement de statut.

#### Exemple de journal d’audit

```text
28/09/2026 - 14:30
Utilisateur : Mustapha
Action : Validation rapprochement
Banque : VIR-45821
Montant : 50 000 DH
Ancien statut : À vérifier
Nouveau statut : Rapprochée
```

#### Livrable

- table audit_logs ;
- historique complet ;
- traçabilité de chaque décision métier.

---

### PHASE 15 — Gestion utilisateurs, rôles et permissions

L’application doit limiter l’accès selon les responsabilités.

#### Rôles possibles

- trésorerie ;
- comptabilité ;
- responsable ;
- direction ;
- administrateur.

#### Permissions

- consulter les relevés ;
- modifier les paramètres ;
- valider les rapprochements ;
- traiter les écarts ;
- gérer les utilisateurs ;
- voir les rapports.

#### Livrable

- authentification ;
- session / JWT ;
- rôles dynamiques ;
- permissions centralisées ;
- sécurité sur les accès API.

---

### PHASE 16 — Prévisions de trésorerie

Une fois la position bancaire stable, on ajoute la capacité de projection.

#### Objectifs

- estimer les encaissements futurs ;
- estimer les décaissements futurs ;
- calculer la position future ;
- distinguer réalisé, prévu, en attente, reporté.

#### Calcul approximatif

```text
Position future = Position actuelle + Encaissements prévus - Décaissements prévus
```

#### Livrable

Tableau de prévisions et projections de trésorerie.

---

### PHASE 17 — Dashboard et KPI

Le dashboard vient après les modules métiers pour afficher des données fiables.

#### KPI principaux

- solde bancaire total ;
- crédit disponible ;
- position disponible ;
- transactions rapprochées ;
- transactions non rapprochées ;
- montant des écarts ;
- encaissements prévus ;
- décaissements prévus ;
- position prévisionnelle.

#### Objectif

donner une vue rapide de la santé financière et de la trésorerie.

---

### PHASE 18 — Tests unitaires et tests métier

#### Objectif

Contrôler la qualité des services et la cohérence des calculs.

#### à tester

- calcul de crédit disponible ;
- calcul de position disponible ;
- import des relevés ;
- normalisation des fichiers ;
- moteur de rapprochement ;
- gestion des écarts ;
- règles de permissions ;
- historique et audit.

#### Cas de tests

- 1 → 1
- 1 → N
- N → 1
- N → N
- montant différent
- date différente
- référence différente
- transaction inconnue

---

### PHASE 19 — Tests avec les données réelles SIMTIS

C’est une phase cruciale. Les tests de développement ne suffisent pas.

#### Objectif

Comparer les résultats de l’application aux données réelles utilisées par Salma et Mustapha.

#### Vérifications

- la position affichée correspond à la position réelle ;
- les rapprochements sont cohérents ;
- les écarts sont correctement identifiés ;
- les résultats sont acceptés par les utilisateurs métier.

#### Livrable

rapport de validation fonctionnelle avec les utilisateurs.

---

### PHASE 20 — Validation par les utilisateurs

Le projet ne doit pas être validé uniquement par le technicien.

#### Tests utilisateurs à prévoir

- Salma : banques, position, prévisions ;
- Mustapha : écritures, rapprochement, écarts ;
- comptabilité : validation, dashboard ;
- direction : decision-making et KPI.

#### Point clé

Les règles métier doivent être validées par les utilisateurs avant mise en production.

---

### PHASE 21 — Dockerisation

#### Objectif

rendre le projet exécutable dans un environnement standardisé.

#### Conteneurs envisagés

- frontend
- backend
- PostgreSQL

#### Livrable

```bash
docker compose up -d
```

---

### PHASE 22 — Déploiement et mise en production

#### À préparer

- HTTPS ;
- authentification ;
- permissions ;
- sauvegardes PostgreSQL ;
- monitoring ;
- logs ;
- variables d’environnement ;
- bonnes pratiques de sécurité.

#### Avant ouverture aux utilisateurs

- vérifier les backups ;
- vérifier les rôles ;
- valider les imports ;
- vérifier les rapprochements ;
- vérifier le dashboard ;
- tester les accès ;
- vérifier les performances.

---

## 5. Ordre recommandé de développement

Pour limiter les risques, il vaut mieux avancer en lots fonctionnels.

### LOT 1 — Fondations

- architecture
- PostgreSQL
- backend et frontend
- base de données

### LOT 2 — Banques et comptes

- banques
- comptes
- relevés bancaires
- normalisation

### LOT 3 — Position bancaire

- soldes
- crédit disponible
- position disponible
- contrôle métier

### LOT 4 — Import comptable

- Sage / SI
- écritures comptables
- tableau d’écritures

### LOT 5 — Rapprochement bancaire

- matching
- scoring
- validation manuelle
- écarts
- historique

### LOT 6 — Utilisateurs et sécurité

- authentification
- rôles
- permissions
- audit

### LOT 7 — Prévisions et dashboard

- encaissements / décaissements
- position future
- KPI
- tableau de bord

### LOT 8 — Tests, validation, production

- tests
- validation par les utilisateurs
- Docker
- mise en production

---

## 6. MVP recommandé

Pour éviter de viser trop grand trop vite, le MVP doit contenir seulement les fonctions indispensables.

### MVP obligatoire

- gestion des banques ;
- gestion des comptes ;
- import de relevés bancaires ;
- validation et normalisation ;
- calcul de la position bancaire ;
- import Sage / SI ;
- rapprochement simple 1 → 1 ;
- validation manuelle ;
- écarts simples ;
- dashboard de base ;
- gestion des utilisateurs et permissions de base.

### Version avancée

- rapprochement 1 → N ;
- N → 1 ;
- N → N ;
- prévisions avancées ;
- alertes ;
- audit complet ;
- reporting avancé.

---

## 7. Règles de conduite du projet

### Règle 1
Ne pas commencer le développement sans comprendre le processus réel.

### Règle 2
Ne pas reconstruire la comptabilité dans l’application ; il faut la consommer et la contrôler.

### Règle 3
Toujours normaliser les données avant les calculs.

### Règle 4
La validation métier doit preceder la mise en production.

### Règle 5
Tout changement important doit être traçable dans l’historique.

---

## 8. Résultat final attendu

À l’issue du projet, SIMTIS doit devenir une plateforme de pilotage financier capable de :

- centraliser les données bancaires, comptables et de trésorerie ;
- calculer automatiquement la position bancaire ;
- rapprocher les mouvements bancaires avec les écritures comptables ;
- identifier les écarts ;
- suivre les validations ;
- sécuriser les accès ;
- proposer un dashboard de suivi ;
- soutenir la décision financière.

---

## 9. Conclusion

Le projet SIMTIS est un projet de type SaaS financier / bancaire, structuré en plusieurs blocs métier qui doivent être développés progressivement, du plus concret au plus avancé :

- compréhension du réel ;
- données ;
- normalisation ;
- position bancaire ;
- comptabilité ;
- rapprochement ;
- écarts ;
- historique ;
- sécurité ;
- prévisions ;
- dashboard ;
- production.

Cette logique de progression permet de limiter les erreurs, de valider les règles métier plus facilement et de livrer une solution robuste et exploitable.
