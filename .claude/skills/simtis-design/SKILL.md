---
name: simtis-design
description: Use when creating, modifying or restyling any page, component, table, chart or UI element of the SIMTIS Finance frontend (Next.js / Tailwind) — dashboard, banques, comptes, relevés, écritures, rapprochement, écarts, position bancaire, prévisions, devises, rapports, administration — or when asked to apply the SIMTIS design system, teal palette or logo.
---

# SIMTIS Finance — Design System

## Vue d'ensemble

SIMTIS Finance est une plateforme SaaS de trésorerie et de rapprochement bancaire. L'interface doit ressembler à une **vraie application financière d'entreprise** : sobre, lisible, aérée, en **Teal + Turquoise + Blanc + Gris clair**.

**Référence visuelle** : `reference-dashboard.png` dans ce dossier. Ouvre-la avec l'outil Read avant tout travail sur le layout ou le dashboard.

## Règles absolues

1. **Design uniquement** : ne modifie jamais la logique métier, les calculs financiers, les appels API, les routes ni la structure fonctionnelle. Si un changement visuel semble exiger un changement de logique, arrête-toi et demande.
2. **Analyse avant de coder** : inventorie les pages, composants, la configuration Tailwind/CSS et les librairies UI/graphiques existantes. Réutilise ce qui existe, ne duplique pas.
3. **Tokens uniquement** : aucune couleur en dur hors `tokens.css`. Utilise les variables `--simtis-*` ou les classes Tailwind qui en dérivent.
4. **Tableaux Banques, Devises et Prévisions** : leur structure est imposée par le classeur `docs/specs/SIMTIS_tableaux_complets.xlsx` (voir `pages.md` §Tableaux imposés). Ne renomme, n'ajoute, ne supprime ni ne déplace aucune colonne ou ligne, et ne les remplace jamais par des cartes ou des graphiques. Les libellés sont ceux du classeur (« LIGNE », « Disponible Fc reel », « facilité de caisse », « Exp DH convertible »). Les colonnes de banques viennent de l'API, affichées par code (AWB, BMCE, BP, CIH, BMCI).
5. **Logo** : utilise le vrai fichier du logo SIMTIS (`frontend/public/logo-simtis.png`) et ceux des banques (`frontend/public/banques/`). Ne les recrée pas, ne les recolore pas, ne les déforme pas. S'il est absent, demande-le.
6. **Aucun emoji**. Icônes = Lucide React.

## Référence rapide

| Élément | Valeur |
|---|---|
| Primary / Primary dark | `#006B70` / `#004F54` (sidebar, titres, boutons principaux, élément actif) |
| Secondary | `#18B7C8` (accents, graphiques, indicateur actif) |
| Light | `#E6F7F7` (fond des icônes, en-têtes de tableau, sélection) |
| Background / Card | `#F5F8FA` / `#FFFFFF` |
| Text / Muted / Border | `#17324D` / `#64748B` / `#D9E3E8` |
| Success / Warning / Danger | `#16A66A` / `#F59E0B` / `#E5484D` |
| Police | Inter (ou celle déjà présente) |
| Titre de page / KPI / Titre de carte / Tableau | 28-32px / 26-32px / 15-17px / 13-14px |
| Radius | cartes 12-16px · boutons 8-10px · inputs 8px · badges 9999px |
| Ombre | `0 2px 10px rgba(0,0,0,0.04)` uniquement |
| Espacements | 4 · 8 · 12 · 16 · 20 · 24 · 32px ; padding de carte 20-24px ; gap 16-20px ; sections 24-32px |
| Animations | 150-250ms, hover / dropdown / sidebar / transitions uniquement |
| Sidebar / Header | 240-260px teal foncé / 70px blanc |
| Montants | alignés à droite, `tabular-nums`, format `2 450 000 DH` |

## Fichiers de ce skill

| Fichier | Quand le lire |
|---|---|
| `tokens.css` | Mise en place ou vérification du thème (variables CSS + mapping Tailwind) |
| `components.md` | Création ou modification d'un composant : layout, KpiCard, DataTable, StatusBadge, boutons, formulaires, graphiques, états UI |
| `pages.md` | Travail sur une page précise, ou sur les 3 tableaux imposés |
| `reference-dashboard.png` | Tout travail sur le layout ou le dashboard |

## Priorité visuelle

Position financière → Alertes / écarts → Rapprochement → Prévisions → Transactions → Détails.
Le dashboard doit répondre immédiatement à 7 questions : position bancaire, disponible, crédit disponible, taux de rapprochement, écarts, position future, actions en attente.

## Erreurs courantes

| Erreur | Correction |
|---|---|
| Couleur Tailwind brute (`bg-blue-600`, `text-purple-500`) | Token `simtis-*` |
| Gradients, glassmorphism, néons, grosses ombres ou bordures épaisses | Fond uni, ombre légère, bordure `--simtis-border` 1px |
| Montants alignés à gauche ou en format `2450000.00` | `text-right tabular-nums` + `formatAmount()` |
| Tableau Banques/Devises/Prévisions « amélioré » en cartes | Garder la structure exacte de la maquette |
| Page sans état chargement / vide / erreur | `LoadingState` / `EmptyState` / `ErrorState` |
| Composant recréé alors qu'il existe déjà | Réutiliser et restyler l'existant |
| Couleur de statut inventée | Utiliser la table des badges dans `components.md` |
| Appel API ou calcul modifié « au passage » | Annuler : design uniquement |

## Vérification avant de terminer

- [ ] Toutes les routes s'affichent sans erreur
- [ ] Aucun appel API, calcul ou route modifié (relire le diff)
- [ ] Aucune couleur hors tokens (`grep` des classes `bg-`/`text-` brutes et des codes hex)
- [ ] Rendu vérifié en desktop, tablette (sidebar repliable) et mobile (menu, tableaux scrollables)
