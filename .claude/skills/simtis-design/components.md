# SIMTIS — Composants

Les classes supposent que les tokens de `tokens.css` sont exposés dans Tailwind (`bg-simtis-primary`, etc.).
Si un composant équivalent existe déjà dans le projet, **restyle-le** au lieu d'en créer un nouveau.

Composants à avoir (une seule implémentation chacun) :
`AppSidebar · AppHeader · PageHeader · KpiCard · BankCard · DataTable · StatusBadge · SearchBar · DateRangePicker · ChartCard · FilterBar · Modal · Toast · EmptyState · LoadingState · ErrorState · NotificationCenter`

---

## 1. Layout général

```text
┌──────────┬─────────────────────────────────────────────┐
│ SIDEBAR  │ HEADER (70px, blanc)                        │
│ 252px    ├─────────────────────────────────────────────┤
│ teal     │ CONTENU (bg #F5F8FA, padding 24-32px)       │
│ fixe     │                                             │
└──────────┴─────────────────────────────────────────────┘
```

```tsx
<div className="min-h-screen bg-simtis-background">
  <AppSidebar />                       {/* fixed left-0 top-0 h-screen w-[252px] */}
  <div className="lg:pl-[252px]">
    <AppHeader />                      {/* sticky top-0 h-[70px] */}
    <main className="p-6 lg:p-8 space-y-6">{children}</main>
  </div>
</div>
```

## 2. AppSidebar

- Fond `bg-simtis-primary-dark`, texte `text-white/80`, largeur 240-260px, fixe.
- En haut : vrai logo SIMTIS sur une zone blanche (comme dans la maquette), puis « SIMTIS Finance ».
- En bas : `SIMTIS Finance` + `v1.0.0` en `text-white/60 text-xs`.
- Tablette : repliable (icônes seules) ; mobile : tiroir ouvert par un bouton menu dans le header.

| Entrée | Route | Icône Lucide |
|---|---|---|
| Dashboard | `/dashboard` | `LayoutDashboard` |
| Banques | `/banques` | `Landmark` |
| Comptes | `/comptes` | `WalletCards` |
| Relevés | `/releves` | `FileSpreadsheet` |
| Écritures comptables | `/ecritures` | `BookText` |
| Rapprochement | `/rapprochement` | `GitCompare` |
| Écarts | `/ecarts` | `AlertTriangle` |
| Position bancaire | `/position-bancaire` | `TrendingUp` |
| Prévisions | `/previsions` | `ChartLine` (ou `LineChart` selon la version) |
| Devises | `/devises` | `CircleDollarSign` |
| Rapports | `/rapports` | `FileText` |
| Administration | `/administration` | `Settings` |

> Garde les routes déjà existantes du projet si elles diffèrent : ne renomme jamais une route.

```tsx
// Item de navigation
<Link
  href={href}
  className={cn(
    "relative flex items-center gap-3 rounded-[10px] px-4 py-2.5 text-[15px] transition-colors duration-200",
    active
      ? "bg-white/10 text-white before:absolute before:left-0 before:top-2 before:bottom-2 before:w-[3px] before:rounded-full before:bg-simtis-secondary"
      : "text-white/75 hover:bg-white/5 hover:text-white"
  )}
>
  <Icon className="h-5 w-5 shrink-0" strokeWidth={1.75} />
  <span>{label}</span>
</Link>
```

## 3. AppHeader

- `h-[70px] bg-white border-b border-simtis-border px-6 flex items-center justify-between`
- À gauche, `SearchBar` : placeholder « Rechercher un compte, une transaction, un relevé... », icône `Search`, fond `bg-simtis-background`, bordure légère, `rounded-[20px]`, largeur max ~520px.
- À droite : cloche `Bell` avec badge rouge (compteur), avatar rond `bg-simtis-primary text-white` (initiale), nom en gras + rôle en `text-simtis-muted text-xs`, chevron `ChevronDown` (menu déroulant).

## 4. PageHeader

```tsx
<div className="flex flex-wrap items-start justify-between gap-4">
  <div>
    <h1 className="text-[30px] font-bold text-simtis-text leading-tight">Dashboard</h1>
    <p className="mt-1 text-[15px] text-simtis-muted">
      Vue d'ensemble de la position bancaire, du rapprochement et des prévisions
    </p>
  </div>
  {/* actions : DateRangePicker, bouton primaire... */}
</div>
```

## 5. Carte (base de KpiCard, ChartCard, tableaux)

```tsx
<section className="rounded-[14px] border border-simtis-border bg-white p-5 lg:p-6 shadow-simtis">
  <header className="mb-4 flex items-center justify-between">
    <div className="flex items-center gap-3">
      <span className="grid h-9 w-9 place-items-center rounded-lg bg-simtis-light text-simtis-primary">
        <Icon className="h-5 w-5" />
      </span>
      <h2 className="text-base font-semibold text-simtis-text">Position bancaire par banque</h2>
    </div>
    <Link href="..." className="flex items-center gap-1 text-sm font-medium text-simtis-primary hover:underline">
      Voir tout <ArrowRight className="h-4 w-4" />
    </Link>
  </header>
  {children}
</section>
```

## 6. KpiCard

Contenu : icône dans un carré `bg-simtis-light`, titre secondaire, **valeur** (26-32px, bold, `text-simtis-primary`), variation (`▲ +5.2%` en success, `▼` en danger) + « vs mois précédent » en muted. Variante « Opérations rapprochées » : petit donut de progression à droite (anneau `--simtis-primary`, piste `--simtis-light`, % au centre).

Grille : `grid gap-5 sm:grid-cols-2 xl:grid-cols-4`.

## 7. DataTable

| Partie | Style |
|---|---|
| Conteneur | `overflow-x-auto rounded-[12px] border border-simtis-border` |
| En-tête | `bg-simtis-light/60 text-simtis-primary-dark text-[13px] font-semibold` |
| Cellules | `px-4 py-3 text-[13.5px] text-simtis-text border-b border-simtis-border/70` |
| Ligne | `bg-white hover:bg-simtis-light/40 transition-colors` |
| Montants | `text-right tabular-nums whitespace-nowrap` |
| Ligne Total | `font-semibold bg-simtis-background` |
| Crédit disponible / montants positifs mis en avant | `text-simtis-success` |
| Position disponible | `text-simtis-primary font-medium` |

Prévoir : tri, pagination, sélection multiple (rapprochement), état vide intégré.

### Format des montants

```ts
// lib/format.ts — séparateur de milliers = espace, pas de décimales si entières
export function formatAmount(value: number | string, currency?: string) {
  const n = typeof value === "string" ? Number(value) : value;
  const s = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 0, maximumFractionDigits: 2 })
    .format(n)
    .replace(/ | /g, " ");
  return currency ? `${s} ${currency}` : s;
}
// formatAmount(2450000, "DH") → "2 450 000 DH"   ·   valeur nulle affichée "-"
```

> Ne change pas la façon dont les montants sont **calculés** ou reçus de l'API : seulement leur affichage.

## 8. StatusBadge

`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium`

| Statut | Fond | Texte |
|---|---|---|
| Rapprochée · Réalisé · Conforme · Actif · Valide | `--simtis-success-bg` | `--simtis-success-fg` |
| À vérifier · En attente · Doublon | `--simtis-warning-bg` | `--simtis-warning-fg` |
| Non rapprochée · À traiter · Erreur | `--simtis-danger-bg` | `--simtis-danger-fg` |
| Écart · En cours | `--simtis-orange-bg` | `--simtis-orange-fg` |
| Prévu | `--simtis-light` | `--simtis-primary` |
| Reporté · Clôturé · Traité · Annulé | `--simtis-neutral-bg` | `--simtis-neutral-fg` |

Centralise le mapping statut → style dans un seul objet ; n'invente pas de nouvelle couleur.

## 9. Boutons

| Variante | Classes | Usage |
|---|---|---|
| Primary | `bg-simtis-primary text-white hover:bg-simtis-primary-dark` | « + Importer un relevé », « Valider le rapprochement » |
| Secondary | `bg-simtis-light text-simtis-primary-dark hover:bg-simtis-light/70` | Annuler, Exporter, Filtrer |
| Danger | `bg-simtis-danger text-white hover:opacity-90` | Actions destructrices uniquement |
| Ghost / lien | `text-simtis-primary hover:underline` | « Voir tout → » |

Communs : `h-10 px-4 rounded-[10px] text-sm font-medium inline-flex items-center gap-2 transition-colors duration-200 disabled:opacity-50`.

## 10. Formulaires

```tsx
<label className="mb-1.5 block text-sm font-medium text-simtis-text" htmlFor="banque">Banque</label>
<select
  id="banque"
  className="h-[42px] w-full rounded-lg border border-simtis-border bg-white px-3 text-sm text-simtis-text
             focus:border-simtis-primary focus:outline-none focus:ring-2 focus:ring-simtis-primary/15"
>
  <option>Sélectionner une banque</option>
</select>
```

Montants saisis : alignés à droite, suffixe « DH » ou devise. Dates au format `jj/mm/aaaa`.

## 11. Graphiques

Utilise la librairie déjà présente (sinon Recharts).

| Graphique | Couleurs |
|---|---|
| Répartition des soldes (donut) | `chart-1` → `chart-4` dans l'ordre ; total au centre (« 2 450 000 / DH ») ; légende à droite avec % et montant |
| Statut du rapprochement (donut) | Rapprochées = success, À vérifier = warning, Non rapprochées = danger, Écarts = `chart-4` ; total « opérations » au centre |
| Prévisions (barres + ligne) | Encaissements = `#1FB88A` (vert-turquoise), Décaissements = `chart-1`, Position prévisionnelle = ligne `chart-2` avec points |
| Évolution de la position | Aire ou ligne `chart-1`, remplissage `--simtis-light` |

Grille horizontale seulement, en `--simtis-border` ; axes et labels en `text-simtis-muted 12px` ; pas d'ombre, pas de 3D ; infobulle sur carte blanche.

## 12. États UI (obligatoires sur chaque page)

| État | Rendu |
|---|---|
| Chargement | Skeletons `animate-pulse bg-simtis-light/60 rounded` aux dimensions du contenu final |
| Vide | Icône muted + message (ex. « Aucun relevé bancaire disponible. ») + action primaire si pertinente |
| Erreur | « Une erreur est survenue. » + bouton secondaire « Réessayer » |
| Succès | Toast discret en bas à droite, bordure gauche success, disparaît après ~4s |

## 13. Modal / panneau latéral

Overlay `bg-simtis-text/30`, carte blanche `rounded-[14px] shadow-simtis`, titre 17px semibold, actions à droite en bas (Secondary puis Primary). Les panneaux de détail (Écarts) glissent depuis la droite (largeur ~480px).

## 14. Responsive

Ordre de priorité : Desktop → Laptop → Tablette → Mobile.
- `lg` et plus : sidebar fixe.
- `md` : sidebar repliée en icônes.
- `< md` : sidebar en tiroir ; KPI en 1 ou 2 colonnes ; tous les tableaux en `overflow-x-auto`.
