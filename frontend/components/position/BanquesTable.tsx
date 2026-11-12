"use client";

import { ChevronDown, ChevronUp, Landmark } from "lucide-react";
import Link from "next/link";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { BankLabel } from "@/components/banks/BankLabel";
import {
  largeurMin,
  GRID_FRAME,
  GRID_HEAD,
  GRID_ROW_HEAD,
  GRID_TABLE,
} from "@/components/position/GridCell";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { finNumero } from "@/lib/accounts";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import { canAccess } from "@/lib/permissions";
import {
  JOURS_AFFICHES,
  formatJour,
  formatTaux,
  noteCellule,
  signTone,
  type Tone,
} from "@/lib/position";
import { lienReleve } from "@/lib/statements";
import { getBanquesTable } from "@/services/position";
import type {
  BanquesTable as Table,
  CelluleBanque,
  CompteCellule,
  LigneBanques,
} from "@/types/position";

type LoadState = "loading" | "error" | "ready";

const NUMBER = "px-3 py-2.5 text-right tabular-nums whitespace-nowrap";
const ROW_HEAD = GRID_ROW_HEAD;
const GRID = cn(GRID_TABLE, "table-fixed");
// Lignes fixées pendant le défilement vertical : fond opaque, au-dessus des jours qui défilent
const STICKY_HAUT = "sticky top-0 z-10 bg-simtis-card";
const STICKY_BAS = "sticky bottom-0 z-10 bg-simtis-card";
// Taux et LIGNE (12/11/2026) : bloc « paramètres » sur fond teal clair, libellés semi-gras, trait
// teal sous LIGNE. Le trait est une ombre intérieure des cellules : une bordure de tableau fusionnée
// ne suit pas toujours l'en-tête fixé pendant le défilement.
const PARAMETRES = "bg-simtis-light";
const PARAMETRE_HEAD = cn(ROW_HEAD, "font-semibold");
const TRAIT_SOUS_LIGNE = "*:shadow-[inset_0_-2px_0_var(--simtis-primary)]";
// Disponible Fc reel : vert > 0, rouge < 0 (tokens de statut, pas le vert du classeur)
const TONES: Record<Tone, string> = {
  positive: "text-simtis-success",
  negative: "text-simtis-danger",
  neutral: "",
};

type BanquesTableProps = {
  companyId: number;
  /** Date de fin du tableau (« AAAA-MM-JJ ») ; l'API ne va jamais au-delà d'aujourd'hui. */
  jour: string;
  /** Réponse chargée, pour le graphique « Évolution de la position » placé en bas de la page. */
  onCharge?: (table: Table) => void;
};

/**
 * Tableau Banques du classeur, calculé par l'API à partir des soldes du jour (lecture seule) :
 * Taux, LIGNE, une ligne « facilité de caisse » par jour (solde du jour, décision du 02/11/2026),
 * Disponible Fc reel (solde + LIGNE).
 */
export function BanquesTable({ companyId, jour, onCharge }: BanquesTableProps) {
  const [table, setTable] = useState<Table | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getBanquesTable(companyId, jour).then(
      (result) => {
        if (cancelled) return;
        setTable(result);
        setState("ready");
        onCharge?.(result);
      },
      () => {
        if (!cancelled) setState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [companyId, jour, retryKey, onCharge]);

  return (
    <Card title="Banques" icon={Landmark}>
      {state === "loading" && <LoadingState rows={4} />}
      {state === "error" && (
        <ErrorState
          message="Impossible de charger le tableau Banques."
          onRetry={() => {
            setState("loading");
            setRetryKey((key) => key + 1);
          }}
        />
      )}
      {state === "ready" && table && <Grid table={table} />}
    </Card>
  );
}

/**
 * Tableau dans un cadre qui défile verticalement (30/10/2026) : seuls les `JOURS_AFFICHES` derniers
 * jours sont visibles, les plus anciens au-dessus ; l'en-tête, Taux et LIGNE restent en haut et
 * Disponible Fc reel en bas.
 */
function Grid({ table }: { table: Table }) {
  const cadre = useRef<HTMLDivElement>(null);
  const tableau = useRef<HTMLTableElement>(null);
  // « Afficher tous les jours » déplie le tableau sans défilement ; non mémorisé (3 jours à
  // l'ouverture de la page)
  const [tout, setTout] = useState(false);
  const repliable = table.jours.length > JOURS_AFFICHES;

  // Hauteur du cadre = en-tête + derniers jours + Disponible Fc reel, mesurés en fractions de pixel
  // (offsetHeight arrondit chaque ligne : sur des centaines de jours, l'écart écrasait le cadre).
  // Recalculée quand le tableau change de taille (largeur de l'écran, logos chargés). Ouvert en
  // bas, sur les jours récents.
  useLayoutEffect(() => {
    const frame = cadre.current;
    const grid = tableau.current;
    if (!frame || !grid) return;
    const ajuster = () => {
      const jours = grid.querySelectorAll<HTMLTableRowElement>("tbody tr");
      const haut = grid.tHead?.getBoundingClientRect();
      const bas = grid.tFoot?.getBoundingClientRect();
      if (tout || jours.length <= JOURS_AFFICHES || !haut || !bas) {
        frame.style.maxHeight = "";
        return;
      }
      const premier = jours[jours.length - JOURS_AFFICHES].getBoundingClientRect();
      const dernier = jours[jours.length - 1].getBoundingClientRect();
      const hauteur = haut.height + (dernier.bottom - premier.top) + bas.height;
      frame.style.maxHeight = `${Math.ceil(hauteur) + 2}px`;
    };
    ajuster();
    frame.scrollTop = frame.scrollHeight;
    const observer = new ResizeObserver(ajuster);
    observer.observe(grid);
    return () => observer.disconnect();
  }, [table, tout]);

  return (
    <>
      {repliable && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm">
          <p className="text-simtis-muted">
            {tout
              ? `${table.jours.length} jours`
              : `${JOURS_AFFICHES} derniers jours sur ${table.jours.length}, les plus anciens en défilant`}
          </p>
          <Button
            variant="ghost"
            icon={tout ? ChevronUp : ChevronDown}
            onClick={() => setTout((value) => !value)}
            aria-expanded={tout}
            className="h-auto min-h-10 px-0 whitespace-normal"
          >
            {tout ? `Réduire à ${JOURS_AFFICHES} jours` : "Afficher tous les jours"}
          </Button>
        </div>
      )}
      {/* GRID_FRAME est relative : le texte des lecteurs d'écran ne doit pas élargir la page */}
      <div ref={cadre} className={cn(GRID_FRAME, "overflow-y-auto")}>
        <table
          ref={tableau}
          className={GRID}
          style={largeurMin(200 + 2 * 150, table.banques.length)}
          aria-label="Banques"
        >
          <colgroup>
            <col className="w-[200px]" />
            {table.banques.map((banque) => (
              <col key={banque.bank_id} />
            ))}
            <col className="w-[150px]" />
            <col className="w-[150px]" />
          </colgroup>
          {/* En-tête, Taux et LIGNE restent en haut pendant le défilement ; Taux et LIGNE en teal
              clair, séparés des jours par un trait */}
          <thead className={STICKY_HAUT}>
            <tr>
              <th scope="col" className={cn(GRID_HEAD, "text-left")}>
                Banque
              </th>
              {table.banques.map((banque) => (
                <th key={banque.bank_id} scope="col" className={GRID_HEAD}>
                  <BankLabel code={banque.code} logo={banque.logo} layout="stacked" />
                </th>
              ))}
              <th scope="col" className={GRID_HEAD}>
                TOTAL
              </th>
              <th scope="col" className={GRID_HEAD}>
                DEPASSEMENT
              </th>
            </tr>
            <tr className={PARAMETRES}>
              <th scope="row" className={PARAMETRE_HEAD}>
                Taux
              </th>
              {table.banques.map((banque) => (
                <td key={banque.bank_id} className={NUMBER}>
                  {formatTaux(banque.taux_pct)}
                </td>
              ))}
              <td />
              <td />
            </tr>
            <tr className={cn(PARAMETRES, TRAIT_SOUS_LIGNE)}>
              <th
                scope="row"
                className={PARAMETRE_HEAD}
                title="LIGNE actuelle du compte, appliquée à tous les jours"
              >
                LIGNE
              </th>
              {table.banques.map((banque) => (
                <td key={banque.bank_id} className={NUMBER}>
                  {formatAmount(banque.ligne)}
                </td>
              ))}
              <td className={NUMBER}>{formatAmount(table.ligne_total)}</td>
              <td />
            </tr>
          </thead>
          <tbody>
            {table.jours.map((day) => (
              <tr key={day.date}>
                <th scope="row" className={ROW_HEAD}>
                  facilité de caisse <span className="tabular-nums">{formatJour(day.date)}</span>
                </th>
                <LineCells line={day} liens />
              </tr>
            ))}
          </tbody>
          {/* Ligne séparée sous les jours, mais dans le même tableau : elle garde les en-têtes de
              colonnes (lecteurs d'écran) et reste en bas pendant le défilement. La rangée vide la
              détache. */}
          <tfoot className={STICKY_BAS}>
            <tr aria-hidden="true">
              <td
                colSpan={table.banques.length + 3}
                className="h-3 border-x-0! border-b-0! bg-simtis-card p-0"
              />
            </tr>
            {/* Comme la ligne Total des autres tableaux : semi-gras sur fond gris très clair */}
            <tr className="bg-simtis-background font-semibold">
              <th scope="row" className={ROW_HEAD}>
                Disponible Fc reel
              </th>
              <LineCells line={table.disponible} colored />
            </tr>
          </tfoot>
        </table>
      </div>
      {table.jours.length === 0 && (
        <p className="mt-3 text-sm text-simtis-muted">Aucun solde enregistré pour cette société.</p>
      )}
    </>
  );
}

function LineCells({
  line,
  colored = false,
  liens = false,
}: {
  line: LigneBanques;
  colored?: boolean;
  /** Lignes « facilité de caisse » : un solde ouvre sa ligne du relevé (09/11/2026). */
  liens?: boolean;
}) {
  const { user } = useAuth();
  // Le lien n'est montré qu'à qui peut ouvrir la page Relevés (l'API reste le vrai contrôle)
  const ouvrir = liens && !!user && canAccess(user.permissions, "/releves");
  const tone = (value: string | null) => (colored ? TONES[signTone(value)] : "");
  return (
    <>
      {line.cellules.map((cellule) => (
        <AmountCell
          key={cellule.bank_id}
          cellule={cellule}
          className={tone(cellule.valeur)}
          liens={ouvrir}
        />
      ))}
      <td className={cn(NUMBER, tone(line.total))}>{formatAmount(line.total)}</td>
      <td className={cn(NUMBER, tone(line.depassement))}>{formatAmount(line.depassement)}</td>
    </>
  );
}

const LIEN =
  "cursor-pointer underline-offset-4 decoration-1 hover:underline focus-visible:underline";

/** Lien vers la ligne du relevé d'un compte, `null` pour un solde saisi à la main. */
function lienCompte(compte: CompteCellule): string | null {
  if (compte.operation_id === null || compte.date_operation === null) return null;
  return lienReleve({
    compte: compte.bank_account_id,
    date: compte.date_operation,
    ligne: compte.operation_id,
  });
}

/** Infobulle du lien : la date de la ligne, et l'écart des opérations en cours (20/10/2026). */
function titreLien(compte: CompteCellule): string {
  const parties = [`Voir la ligne du relevé du ${formatDate(compte.date_operation)}`];
  if (compte.solde_operation !== null && compte.solde_operation !== compte.solde) {
    parties.push(`solde de la ligne ${formatAmount(compte.solde_operation)} + opérations en cours`);
  }
  return parties.join(" · ");
}

/**
 * Montant d'une banque ; un solde repris d'un jour précédent est grisé et daté. Sur une ligne
 * « facilité de caisse », un solde qui vient d'un relevé ouvre sa ligne dans la page Relevés
 * (09/11/2026) ; avec plusieurs comptes, un menu propose le solde de chacun.
 */
function AmountCell({
  cellule,
  className,
  liens,
}: {
  cellule: CelluleBanque;
  className: string;
  liens: boolean;
}) {
  const note = noteCellule(cellule);
  const comptes = liens ? (cellule.comptes ?? []) : [];
  const ouvrables = comptes.filter((compte) => lienCompte(compte) !== null);
  let montant: ReactNode = formatAmount(cellule.valeur);
  if (comptes.length === 1 && ouvrables.length === 1) {
    montant = (
      <Link href={lienCompte(comptes[0])!} className={LIEN} title={titreLien(comptes[0])}>
        {montant}
      </Link>
    );
  } else if (comptes.length > 1 && ouvrables.length > 0) {
    montant = <CompteMenu comptes={comptes}>{montant}</CompteMenu>;
  }
  return (
    <td
      className={cn(NUMBER, cellule.reprise && "text-simtis-muted", className)}
      title={ouvrables.length === 0 ? (note ?? undefined) : undefined}
    >
      {montant}
      {note && <span className="sr-only"> ({note})</span>}
    </td>
  );
}

/**
 * Cellule qui additionne plusieurs comptes : le clic ouvre la liste des comptes avec leur solde,
 * chacun vers sa ligne du relevé. Le menu est en position fixe pour ne pas être coupé par le cadre
 * qui défile ; il se ferme au clic dehors, sur Échap ou au défilement.
 */
function CompteMenu({ comptes, children }: { comptes: CompteCellule[]; children: ReactNode }) {
  const [place, setPlace] = useState<{ top: number; right: number } | null>(null);
  const bouton = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!place) return;
    const fermer = () => setPlace(null);
    const dehors = (event: MouseEvent) => {
      const cible = event.target as Node;
      if (!menu.current?.contains(cible) && !bouton.current?.contains(cible)) fermer();
    };
    const touche = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        fermer();
        bouton.current?.focus();
      }
    };
    document.addEventListener("mousedown", dehors);
    document.addEventListener("keydown", touche);
    window.addEventListener("scroll", fermer, true);
    window.addEventListener("resize", fermer);
    return () => {
      document.removeEventListener("mousedown", dehors);
      document.removeEventListener("keydown", touche);
      window.removeEventListener("scroll", fermer, true);
      window.removeEventListener("resize", fermer);
    };
  }, [place]);

  function basculer() {
    if (place) {
      setPlace(null);
      return;
    }
    const rect = bouton.current?.getBoundingClientRect();
    if (rect) setPlace({ top: rect.bottom + 4, right: window.innerWidth - rect.right });
  }

  return (
    <>
      <button
        ref={bouton}
        type="button"
        onClick={basculer}
        aria-haspopup="menu"
        aria-expanded={place !== null}
        title={`Somme de ${comptes.length} comptes : choisir le relevé à ouvrir`}
        className={cn(LIEN, "tabular-nums")}
      >
        {children}
      </button>
      {place && (
        <div
          ref={menu}
          role="menu"
          style={{ top: place.top, right: place.right }}
          className="fixed z-30 min-w-56 rounded-[10px] border border-simtis-border bg-simtis-card p-1 text-left text-sm font-normal text-simtis-text shadow-simtis-hover"
        >
          {comptes.map((compte) => {
            const href = lienCompte(compte);
            const contenu = (
              <>
                <span>{finNumero(compte.numero)}</span>
                <span className="tabular-nums">{formatAmount(compte.solde)}</span>
              </>
            );
            const ligne = "flex items-center justify-between gap-4 rounded-md px-3 py-2";
            return href ? (
              <Link
                key={compte.bank_account_id}
                href={href}
                role="menuitem"
                title={titreLien(compte)}
                className={cn(ligne, "hover:bg-simtis-light focus-visible:bg-simtis-light")}
              >
                {contenu}
              </Link>
            ) : (
              <span
                key={compte.bank_account_id}
                role="menuitem"
                aria-disabled="true"
                title="Solde saisi à la main : aucune ligne de relevé"
                className={cn(ligne, "text-simtis-muted")}
              >
                {contenu}
              </span>
            );
          })}
        </div>
      )}
    </>
  );
}
