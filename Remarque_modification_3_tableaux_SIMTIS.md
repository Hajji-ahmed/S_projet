# Remarque importante — Modification des 3 tableaux SIMTIS

## ⚠️ Consigne générale

Je veux modifier uniquement la structure des 3 tableaux suivants :

1. Prévisions
2. Devises
3. Banques

**NE CHANGE PAS** le design général de l'application, les couleurs, le sidebar, le header, les composants ou les autres modules.

---

## 1. Tableau « Prévisions »

Conserver les informations existantes, mais modifier la structure comme suit :

- La colonne **« Date »** doit être **une seule colonne verticale à gauche**.
- Toutes les dates doivent être regroupées dans cette même colonne.
- Les lignes d'événements doivent rester :
  - Encaissement 24/09
  - Encaissement 25/09
  - Encaissement 29/09
  - La paie
  - Refinancement
  - Douane
  - CHQ1
  - CHQ2
  - CHQ3
- Garder les colonnes :
  - Encaissement
  - Escompte
  - Douane
- Ne pas créer plusieurs colonnes pour les dates.
- La structure doit rester proche de la maquette fournie.

---

## 2. Tableau « Devises »

Conserver uniquement les devises affichées dans la maquette :

- UAR
- USD
- Ex rh convertible

Supprimer toute colonne ou information supplémentaire qui n'existe pas dans la maquette.

---

## 3. Tableau « Banques »

Conserver les colonnes :

- Banque
- CIH
- TIJARI
- BMCE
- BP
- Totale
- Dépassement

Conserver les lignes :

- Taux
- Linge
- Date

### Ajouter obligatoirement à la fin du tableau

**Disposition FC réel**

Cette ligne doit être placée **sous le tableau**, comme dans la maquette de référence, et s'étendre sous la partie correspondante des colonnes bancaires.

---

## ⚠️ RÈGLE ABSOLUE

Les trois tableaux doivent respecter **la structure des maquettes fournies**.

### Ne pas :

- redesign le tableau ;
- changer les intitulés ;
- ajouter des colonnes ;
- supprimer des colonnes existantes ;
- déplacer les informations ;
- modifier la logique métier ;
- remplacer les tableaux par des cartes ou des graphiques.

Modifier **uniquement** ce qui est demandé ci-dessus.

Les autres parties de l'application doivent rester **totalement inchangées**.
