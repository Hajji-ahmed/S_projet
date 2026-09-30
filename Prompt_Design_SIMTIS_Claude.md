# Prompt Claude — Design UI/UX SIMTIS Finance

## Objectif

Je veux que tu refondes **uniquement le DESIGN / UI / UX** de ma plateforme **SIMTIS Finance** afin qu'elle corresponde au style de l'image de référence fournie.

L'identité visuelle doit être basée sur le logo **SIMTIS — Printing & Weaving** et sur une esthétique moderne de plateforme SaaS financière / bancaire.

> **IMPORTANT :** ne modifie pas la logique métier, les calculs, les APIs, les routes ou l'architecture fonctionnelle existante.

---

## 1. Contraintes principales

Avant toute modification :

1. Analyse la structure actuelle du frontend.
2. Identifie les composants existants.
3. Identifie le système CSS / Tailwind.
4. Identifie les pages existantes.
5. Réutilise les composants qui sont déjà corrects.
6. Ne recrée pas inutilement toute l'application.
7. Ne casse aucune API.
8. Ne casse aucune route.
9. Ne modifie aucune logique métier.
10. Ne modifie aucun calcul financier.
11. Ne modifie pas la structure fonctionnelle.
12. Travaille principalement sur le frontend et le Design System.

Le résultat doit conserver toutes les fonctionnalités actuelles.

---

## 2. Identité visuelle SIMTIS

Utilise le logo SIMTIS fourni comme référence principale.

La plateforme doit reprendre principalement :

- Teal / bleu-vert
- Turquoise
- Blanc
- Gris clair

### Palette recommandée

```css
--simtis-primary: #006B70;
--simtis-primary-dark: #004F54;
--simtis-secondary: #18B7C8;
--simtis-light: #E6F7F7;
--simtis-background: #F5F8FA;
--simtis-card: #FFFFFF;
--simtis-text: #17324D;
--simtis-muted: #64748B;
--simtis-border: #D9E3E8;
--simtis-success: #16A66A;
--simtis-warning: #F59E0B;
--simtis-danger: #E5484D;
```

Utilisation :

- Primary : sidebar, titres, boutons principaux, navigation active
- Secondary : graphiques, accents, icônes
- Light : backgrounds d'icônes et éléments sélectionnés
- Background : fond principal
- Card : cartes et tableaux
- Success / Warning / Danger : statuts

Ne pas utiliser trop de couleurs. La plateforme doit rester principalement **Teal + Turquoise + Blanc + Gris clair**.

---

## 3. Style global

Je veux un style :

- SaaS professionnel
- Enterprise
- Finance / Banking
- moderne
- minimaliste
- premium mais sobre
- très lisible
- beaucoup d'espace blanc
- cartes légèrement arrondies
- ombres très discrètes
- tableaux propres
- graphiques modernes
- hiérarchie visuelle claire

Éviter :

- gradients excessifs
- glassmorphism excessif
- néons
- grosses ombres
- grosses bordures
- trop de couleurs
- animations excessives
- éléments décoratifs inutiles
- design trop chargé

L'interface doit donner l'impression d'une vraie application financière professionnelle.

---

## 4. Structure générale

Structure Desktop :

```text
┌────────────────────────────────────────────────────────────┐
│ SIDEBAR │ HEADER                                           │
│         │--------------------------------------------------│
│         │                                                  │
│         │              CONTENU PRINCIPAL                   │
│         │                                                  │
└────────────────────────────────────────────────────────────┘
```

- Sidebar fixe à gauche
- Header horizontal en haut
- Contenu principal à droite

---

## 5. Sidebar

Largeur : **240px à 260px**

Background : **Dark Teal SIMTIS**

En haut :

- vrai logo SIMTIS
- `SIMTIS Finance`

Navigation :

```text
Dashboard
Banques
Comptes
Relevés
Écritures comptables
Rapprochement
Écarts
Position bancaire
Prévisions
Devises
Rapports
Administration
```

Chaque entrée :

- icône
- label
- hover
- état actif

Utiliser **Lucide Icons** ou la bibliothèque déjà présente.

Ne pas utiliser d'emoji.

### Élément actif

- background légèrement plus clair
- accent turquoise
- texte blanc
- icône blanche
- éventuellement petite ligne turquoise à gauche

En bas :

```text
SIMTIS Finance
v1.0.0
```

---

## 6. Header

Header blanc, hauteur environ **70px**.

À gauche : barre de recherche :

```text
Rechercher un compte, une transaction, un relevé...
```

- icône Search
- fond légèrement gris/bleu
- border très légère
- radius ~20px

À droite :

- notifications
- badge notification
- avatar
- nom utilisateur
- rôle
- dropdown

Exemple :

```text
[S] Salma
    Trésorerie
       ˅
```

---

## 7. Dashboard

Titre :

```text
Dashboard
```

Sous-titre :

```text
Vue d’ensemble de la position bancaire, du rapprochement et des prévisions
```

À droite :

```text
01/09/2026 - 30/09/2026
```

avec icône calendrier.

---

## 8. KPI Cards

Créer 4 cartes :

### Carte 1

```text
Total soldes bancaires
2 450 000 DH
▲ +5.2%
vs mois précédent
```

### Carte 2

```text
Crédit disponible
1 200 000 DH
▲ +3.1%
vs mois précédent
```

### Carte 3

```text
Position disponible
3 650 000 DH
▲ +4.8%
vs mois précédent
```

### Carte 4

```text
Opérations rapprochées
1 520
85%
```

avec petit donut/progress.

Chaque carte :

- fond blanc
- border légère
- radius 12-16px
- shadow légère
- icône dans un carré light teal
- valeur importante
- titre secondaire
- variation

---

## 9. Position bancaire

Créer une grande card :

```text
Position bancaire par banque
```

À droite :

```text
Voir tout →
```

Tableau :

```text
Banque
Solde bancaire
Crédit autorisé
Crédit utilisé
Crédit disponible
Position disponible
```

Banques de démonstration :

```text
CIH
BP
Attijariwafa
BMCE
```

Afficher une ligne Total.

Montants alignés à droite.

---

## 10. Répartition des soldes

À côté du tableau :

```text
Répartition des soldes
```

Donut chart.

Centre :

```text
2 450 000
DH
```

Légende :

```text
CIH          49%
BP           27%
Attijariwafa 16%
BMCE          8%
```

Utiliser principalement :

- teal foncé
- turquoise
- light turquoise
- gris bleuté

---

## 11. Transactions récentes

Card :

```text
Transactions récentes
```

Tableau :

```text
Date
Banque
Libellé
Débit
Crédit
Solde
```

Utiliser une typographie compacte mais lisible.

---

## 12. Statut du rapprochement

Card :

```text
Statut du rapprochement
```

Donut chart :

```text
Rapprochées
À vérifier
Non rapprochées
Écarts
```

Couleurs :

- Rapprochées → vert
- À vérifier → orange
- Non rapprochées → rouge
- Écarts → gris/rouge clair

Afficher le nombre total et le pourcentage.

---

## 13. Prévisions de trésorerie

Card :

```text
Prévisions de trésorerie
```

Graphique combiné :

- Encaissements prévus
- Décaissements prévus
- Position prévisionnelle

Axe X :

```text
24/09
25/09
26/09
27/09
28/09
29/09
30/09
01/10
02/10
03/10
```

Style :

- encaissements → vert/turquoise
- décaissements → teal foncé
- position → ligne turquoise

Graphique très lisible.

---

## 14. Écarts à traiter

Card :

```text
Écarts à traiter
```

Tableau :

```text
Date
Banque
Libellé
Montant
Statut
```

Les statuts utilisent des badges modernes :

- À traiter
- En cours
- À vérifier
- Clôturé

---

## 15. Tables

Toutes les tables doivent utiliser le même Design System.

Header :

- background light teal / gris
- texte dark teal

Rows :

- blanc
- hover léger turquoise

Borders :

- très discrètes

Padding :

```text
12px - 16px
```

Radius :

```text
10px - 12px
```

Montants alignés à droite.

---

## 16. Status badges

Créer des badges cohérents :

```text
Rapprochée      → vert clair
À vérifier      → orange clair
Non rapprochée  → rouge clair
Écart            → rouge/orange
Prévu            → turquoise clair
Réalisé          → vert clair
En attente       → gris/orange
Reporté          → gris
```

---

## 17. Boutons

Primary :

```text
+ Importer un relevé
```

Dark Teal + texte blanc.

Secondary :

```text
Annuler
Exporter
Filtrer
```

Light Teal + texte dark teal.

Danger : rouge uniquement pour les actions dangereuses.

Tous les boutons :

- radius 8-10px
- hauteur confortable
- hover subtil

---

## 18. Formulaires

Inputs :

```css
background: white;
border: #D9E3E8;
border-radius: 8px;
height: 42px;
```

Focus :

```text
border: SIMTIS teal
```

Exemple :

```text
Banque
[ Sélectionner une banque ]

Compte
[ Sélectionner un compte ]

Date
[ 24/09/2026 ]

Montant
[ 50 000 DH ]
```

---

## 19. Page Banques

Titre :

```text
Banques
```

Sous-titre :

```text
Gestion des banques et comptes bancaires
```

Créer une card par banque avec :

- logo/icône
- nom
- nombre de comptes
- solde
- crédit disponible
- position disponible
- dernière mise à jour

---

## 20. Page Position bancaire

Filtres :

```text
Banque
Compte
Devise
Date
Période
```

Tableau :

```text
Banque
Compte
Devise
Solde
Crédit autorisé
Crédit utilisé
Crédit disponible
Position disponible
Dépassement
Date de mise à jour
```

Ajouter un graphique d'évolution de la position.

---

## 21. Page Relevés

Titre :

```text
Relevés bancaires
```

Bouton :

```text
+ Importer un relevé
```

Zone Drag & Drop :

```text
Glissez votre fichier Excel ou CSV ici

ou

Choisir un fichier
```

Après upload :

```text
Détection des colonnes
        ↓
Mapping
        ↓
Validation
```

Exemple :

```text
Colonne fichier
Date opération

↓

Champ SIMTIS
Date d'opération
```

---

## 22. Page Rapprochement

Interface en deux parties.

### Transactions bancaires

```text
Date
Libellé
Débit
Crédit
```

### Écritures comptables

```text
Date
Libellé
Débit
Crédit
N° pièce
Échéance
```

Entre les deux :

```text
Correspondance proposée
```

Exemple :

```text
Transaction bancaire
50 000 DH

        ↕

Écriture comptable
50 000 DH

[ Valider le rapprochement ]
```

Prévoir :

- filtres
- recherche
- statut
- pagination
- validation
- rejet
- sélection multiple

---

## 23. Page Écarts

Titre :

```text
Écarts
```

KPI :

```text
Écarts à traiter
Écarts en cours
Écarts clôturés
Montant total
```

Lorsqu'un écart est ouvert, afficher un panneau/modal :

```text
Type
Transaction bancaire
Écriture comptable
Montant
Différence
Commentaire
Responsable
Statut
```

---

## 24. Page Prévisions

Titre :

```text
Prévisions de trésorerie
```

KPI :

```text
Position actuelle
Encaissements prévus
Décaissements prévus
Position future
```

Tableau :

```text
Date
Encaissement
Escompte
Douane
Paie
Refinancement
Chèques
Position prévisionnelle
```

Bouton :

```text
+ Nouvelle prévision
```

---

## 25. Page Devises

Titre :

```text
Devises
```

Afficher :

```text
MAD
EUR
USD
Compte convertible
```

Pour chaque devise :

- montant
- taux
- équivalent MAD
- date

Filtres :

```text
Banque
Compte
Devise
Date
```

---

## 26. Typographie

Utiliser :

```text
Inter
```

ou :

```text
Manrope
```

ou la police déjà présente.

Hiérarchie :

```text
Titre page       28-32px
Sous-titre       14-16px
Titre card       15-17px
KPI              26-32px
Table            13-14px
Secondaire       12-13px
```

---

## 27. Icônes

Utiliser Lucide React si disponible.

Exemples :

```text
Dashboard       → LayoutDashboard
Banques         → Landmark
Comptes         → WalletCards
Relevés         → FileSpreadsheet
Rapprochement   → GitCompare
Écarts          → AlertTriangle
Position        → TrendingUp
Prévisions      → ChartLine
Devises         → CircleDollarSign
Administration  → Settings
```

Ne pas utiliser d'emoji.

---

## 28. Logo

Utiliser le vrai logo SIMTIS fourni.

Ne pas :

- modifier ses proportions
- changer sa couleur
- appliquer un filtre
- recréer le logo
- déformer le logo

Le logo doit rester visible mais ne doit pas prendre trop de place.

---

## 29. Design System

Créer des variables globales :

```css
--simtis-primary
--simtis-primary-dark
--simtis-secondary
--simtis-light
--simtis-background
--simtis-card
--simtis-text
--simtis-muted
--simtis-success
--simtis-warning
--simtis-danger
--simtis-border
```

Toutes les pages doivent utiliser ce Design System.

---

## 30. Espacements

Utiliser :

```text
4px
8px
12px
16px
20px
24px
32px
```

Cards :

```text
padding: 20-24px
```

Gap :

```text
16-20px
```

Sections :

```text
24-32px
```

---

## 31. Border radius

```text
Cards    → 12-16px
Buttons  → 8-10px
Inputs   → 8px
Badges   → 9999px
```

---

## 32. Ombres

Utiliser uniquement des ombres très légères :

```css
box-shadow: 0 2px 10px rgba(0,0,0,0.04);
```

---

## 33. Animations

Animations très légères uniquement :

- hover
- dropdown
- sidebar
- loading
- transitions

Durée :

```text
150-250ms
```

Pas d'animations excessives.

---

## 34. Responsive

Priorité :

```text
Desktop
Laptop
Tablet
Mobile
```

Tablette :

- sidebar collapsible

Mobile :

- sidebar devient menu mobile

Les tableaux doivent être scrollables horizontalement.

---

## 35. UX

L'utilisateur doit comprendre immédiatement :

1. Quelle est la position bancaire ?
2. Combien est disponible ?
3. Quel est le crédit disponible ?
4. Combien d'opérations sont rapprochées ?
5. Quels sont les écarts ?
6. Quelle est la position future ?
7. Quelles actions nécessitent son attention ?

Le Dashboard doit répondre à ces questions immédiatement.

---

## 36. Priorité visuelle

```text
1. Position financière
2. Alertes / écarts
3. Rapprochement
4. Prévisions
5. Transactions
6. Détails
```

---

## 37. États UI

Chaque page doit prévoir :

### Loading

Skeletons modernes.

### Empty

Exemple :

```text
Aucun relevé bancaire disponible.
```

### Error

```text
Une erreur est survenue.

[ Réessayer ]
```

### Success

Toast discret.

---

## 38. Composants réutilisables

Créer ou réutiliser :

```text
AppSidebar
AppHeader
PageHeader
KpiCard
BankCard
DataTable
StatusBadge
SearchBar
DateRangePicker
ChartCard
EmptyState
LoadingState
ErrorState
NotificationCenter
FilterBar
Modal
Toast
```

Ne pas dupliquer inutilement les composants.

---

## 39. Cohérence globale

Toutes les pages doivent utiliser exactement le même :

- Header
- Sidebar
- système de couleurs
- typographie
- cards
- tableaux
- badges
- boutons
- filtres
- modals
- notifications
- états loading
- états empty
- états error

Créer un véritable **Design System SIMTIS** réutilisable.

---

## 40. Résultat visuel attendu

L'interface finale doit reprendre l'esprit de l'image de référence :

```text
SIDEBAR TEAL
       +
HEADER BLANC
       +
LOGO SIMTIS
       +
DASHBOARD FINANCE
       +
KPI CARDS
       +
POSITION BANCAIRE
       +
GRAPHIQUES
       +
TRANSACTIONS
       +
RAPPROCHEMENT
       +
ÉCARTS
       +
PRÉVISIONS
```

Le résultat doit être :

- professionnel
- moderne
- simple
- premium
- lisible
- cohérent
- enterprise
- finance / banking
- fidèle à l'identité SIMTIS

---

## 41. Règle finale

Ne copie pas exactement les données fictives de l'image.

Reproduis :

- le style
- la palette
- la hiérarchie visuelle
- la structure
- les espacements
- les composants
- l'UX
- l'identité SIMTIS

Mais conserve les vraies données et fonctionnalités de la plateforme.

---

# Instruction finale à Claude

Avant de coder :

1. Analyse le frontend actuel.
2. Fais l'inventaire des pages.
3. Fais l'inventaire des composants.
4. Identifie Tailwind/CSS.
5. Identifie les dépendances UI/chart.
6. Propose les changements de Design System.
7. Applique ensuite le nouveau design.
8. Vérifie que toutes les routes fonctionnent.
9. Vérifie que les appels API n'ont pas été modifiés.
10. Vérifie que la logique métier et les calculs financiers sont inchangés.

**Objectif final : transformer le frontend actuel en une plateforme SIMTIS Finance moderne, cohérente et professionnelle, visuellement proche de l'image de référence, sans modifier le fonctionnement métier de l'application.**
