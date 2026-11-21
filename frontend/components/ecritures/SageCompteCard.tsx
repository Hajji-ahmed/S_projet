"use client";

import { CircleAlert, CircleCheck, Upload } from "lucide-react";
import { useState, type ReactNode } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { CheckAllButtons } from "@/components/releves/CheckAllButtons";
import { FilterTile } from "@/components/releves/FilterTile";
import { Button } from "@/components/ui/Button";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Pagination } from "@/components/ui/Pagination";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { finNumero } from "@/lib/accounts";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount, formatNombre } from "@/lib/format";
import {
  basculerGroupe,
  cochable,
  messageConfirmation,
  messagePiecesRepetees,
  pageOf,
  sageLinesFor,
  soldesApresImport,
  supprimable,
  toggleVue,
  totauxCoches,
  type BlocageImport,
  type VueLignes,
} from "@/lib/importLines";
import { cochesParDefaut } from "@/lib/sage";
import type {
  ConfirmationComptable,
  EcritureAbsente,
  LigneComptable,
  SageAnalyseCompte,
} from "@/types/accounting";

type SageCompteCardProps = {
  item: SageAnalyseCompte;
  logo: string | null | undefined;
  coches: ReadonlySet<number>;
  onCoches: (next: Set<number>) => void;
  supprimees: ReadonlySet<number>;
  onSupprimees: (next: Set<number>) => void;
  /** Raison qui empêche la validation, ou null. */
  blocage: BlocageImport | null;
  importe: ConfirmationComptable | undefined;
  erreur: string | null;
  busy: boolean;
  onValider: () => void;
};

function Message({ tone, children }: { tone: "danger" | "warning"; children: ReactNode }) {
  return (
    <div
      role="alert"
      className={cn(
        "mb-3 flex items-start gap-2 rounded-lg px-3 py-2.5 text-sm",
        tone === "danger"
          ? "bg-simtis-danger-bg text-simtis-danger-fg"
          : "bg-simtis-warning-bg text-simtis-warning-fg",
      )}
    >
      <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

/**
 * Grand livre d'un compte lu dans la base Sage (21/11/2026) : informations du compte, lignes à
 * cocher et bouton « Valider ce compte ». Même lecture que l'étape Validation de l'import Excel.
 */
export function SageCompteCard({
  item,
  logo,
  coches,
  onCoches,
  supprimees,
  onSupprimees,
  blocage,
  importe,
  erreur,
  busy,
  onValider,
}: SageCompteCardProps) {
  const { compte, analyse } = item;
  const [vue, setVue] = useState<VueLignes>("toutes");
  const [page, setPage] = useState(1);
  const lignes = analyse.lignes;
  const absentes = analyse.ecritures_absentes ?? [];
  const resume = analyse.resume;
  const nouvelles = lignes.filter((line) => line.statut === "Valide").length;
  const totaux = totauxCoches(lignes, coches);
  const solde = soldesApresImport(resume.par_compte, lignes, coches, absentes, supprimees)[0];
  const piecesRepetees = messagePiecesRepetees(analyse.pieces_repetees ?? []);
  const shown = sageLinesFor(lignes, vue, coches);
  const pageView = pageOf(shown, page);

  function toggle(numero: number, value: boolean) {
    const next = new Set(coches);
    if (value) next.add(numero);
    else next.delete(numero);
    onCoches(next);
  }

  function toggleSuppression(id: number, value: boolean) {
    const next = new Set(supprimees);
    if (value) next.add(id);
    else next.delete(id);
    onSupprimees(next);
  }

  const columns: Column<LigneComptable>[] = [
    {
      key: "choix",
      header: "Importer",
      render: (line) => (
        <input
          type="checkbox"
          aria-label={`Importer la ligne du ${formatDate(line.date_ecriture)} ${line.libelle ?? ""}`}
          title={cochable(line) ? undefined : "Déjà importée : elle ne peut pas être cochée."}
          checked={coches.has(line.numero)}
          disabled={!cochable(line) || !!importe}
          onChange={(event) => toggle(line.numero, event.target.checked)}
        />
      ),
    },
    {
      key: "statut",
      header: "État",
      render: (line) => (
        <span className="block min-w-[130px]">
          <StatusBadge status={line.statut} />
          {line.motifs.map((motif) => (
            <span key={motif} className="mt-1 block text-xs text-simtis-muted">
              {motif}
            </span>
          ))}
        </span>
      ),
    },
    {
      key: "date_ecriture",
      header: "Date",
      render: (line) => <span className="whitespace-nowrap">{formatDate(line.date_ecriture)}</span>,
    },
    { key: "journal", header: "Journal", render: (line) => line.journal ?? "-" },
    { key: "numero_piece", header: "N° pièce", render: (line) => line.numero_piece ?? "-" },
    {
      key: "libelle",
      header: "Libellé",
      render: (line) => <span className="block min-w-[200px]">{line.libelle ?? "-"}</span>,
    },
    {
      key: "echeance",
      header: "Échéance",
      render: (line) => <span className="whitespace-nowrap">{formatDate(line.echeance)}</span>,
    },
    {
      key: "debit",
      header: "Débit",
      align: "right",
      render: (line) => formatAmount(line.debit, "DH", { dashForZero: true }),
    },
    {
      key: "credit",
      header: "Crédit",
      align: "right",
      render: (line) => formatAmount(line.credit, "DH", { dashForZero: true }),
    },
  ];

  const absentesColumns: Column<EcritureAbsente>[] = [
    {
      key: "choix",
      header: "Supprimer",
      render: (absente) => (
        <input
          type="checkbox"
          aria-label={`Supprimer l'écriture du ${formatDate(absente.date_ecriture)} ${absente.libelle ?? ""}`}
          title={
            supprimable(absente)
              ? undefined
              : `Rapprochée (${absente.code_rapprochement}) : annulez d'abord son rapprochement.`
          }
          checked={supprimees.has(absente.id)}
          disabled={!supprimable(absente) || !!importe}
          onChange={(event) => toggleSuppression(absente.id, event.target.checked)}
        />
      ),
    },
    {
      key: "date_ecriture",
      header: "Date",
      render: (absente) => (
        <span className="whitespace-nowrap">{formatDate(absente.date_ecriture)}</span>
      ),
    },
    { key: "journal", header: "Journal", render: (absente) => absente.journal ?? "-" },
    { key: "numero_piece", header: "N° pièce", render: (a) => a.numero_piece ?? "-" },
    {
      key: "libelle",
      header: "Libellé",
      render: (absente) => <span className="block min-w-[200px]">{absente.libelle ?? "-"}</span>,
    },
    {
      key: "debit",
      header: "Débit",
      align: "right",
      render: (absente) => formatAmount(absente.debit, "DH", { dashForZero: true }),
    },
    {
      key: "credit",
      header: "Crédit",
      align: "right",
      render: (absente) => formatAmount(absente.credit, "DH", { dashForZero: true }),
    },
  ];

  const tuiles: [VueLignes, string, number, string][] = [
    ["importer", "Lignes cochées", coches.size, "text-simtis-success"],
    ["erreurs", "Lignes en erreur", resume.nb_erreurs, "text-simtis-danger"],
    ["doublons", "Déjà importées", resume.nb_doublons, "text-simtis-warning"],
  ];

  return (
    <section
      aria-label={`Grand livre ${compte.bank_code} ${finNumero(compte.numero)}`}
      className="rounded-card border border-simtis-border bg-simtis-card p-5 shadow-simtis"
    >
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <BankLabel code={compte.bank_code} logo={logo}>
            <span className="text-[15px] font-semibold text-simtis-text">
              {compte.bank_code} · {compte.libelle} · {finNumero(compte.numero)}
            </span>
          </BankLabel>
          <p className="text-sm text-simtis-muted">
            Journaux {compte.journaux.join(", ")} · Compte {compte.comptes.join(", ")} ·{" "}
            {formatNombre(lignes.length)} ligne{lignes.length > 1 ? "s" : ""} dans Sage, dont{" "}
            {formatNombre(nouvelles)} nouvelle{nouvelles > 1 ? "s" : ""}
          </p>
        </div>
        {importe && (
          <span className="inline-flex items-center gap-2 rounded-full bg-simtis-success-bg px-3 py-1 text-sm font-medium text-simtis-success-fg">
            <CircleCheck className="h-4 w-4" aria-hidden />
            Importé : {formatNombre(importe.nb_importees)} écriture
            {importe.nb_importees > 1 ? "s" : ""}
          </span>
        )}
      </header>

      {erreur && <Message tone="danger">{erreur}</Message>}
      {!importe && piecesRepetees && <Message tone="warning">{piecesRepetees}</Message>}

      <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {tuiles.map(([value, label, count, tone]) => (
          <FilterTile
            key={value}
            label={label}
            value={count}
            tone={tone}
            active={vue === value}
            onClick={() => {
              setVue((current) => toggleVue(current, value));
              setPage(1);
            }}
          />
        ))}
      </div>
      <dl className="mb-4 grid gap-3 sm:grid-cols-2">
        <div className="rounded-[12px] border border-simtis-border bg-simtis-background px-3 py-2">
          <dt className="text-xs text-simtis-muted">Total débit / crédit des lignes cochées</dt>
          <dd className="flex flex-wrap gap-x-6 font-semibold text-simtis-text tabular-nums">
            <span>{formatAmount(totaux.debit, "DH")}</span>
            <span>{formatAmount(totaux.credit, "DH")}</span>
          </dd>
        </div>
        <div className="rounded-[12px] border border-simtis-border bg-simtis-background px-3 py-2">
          <dt className="text-xs text-simtis-muted">
            Solde comptable après import{solde?.date ? ` au ${formatDate(solde.date)}` : ""}
          </dt>
          <dd className="font-semibold text-simtis-text tabular-nums">
            {!solde ? (
              "-"
            ) : solde.solde !== null ? (
              formatAmount(solde.solde, "DH")
            ) : (
              <span className="font-normal text-simtis-warning">
                {solde.raison === "apres"
                  ? "solde d'ouverture daté après la période"
                  : "solde d'ouverture à saisir"}
              </span>
            )}
          </dd>
        </div>
      </dl>

      {absentes.length > 0 && !importe && (
        <div className="mb-4">
          <Message tone="warning">
            {absentes.length} écriture{absentes.length > 1 ? "s" : ""} déjà dans SIMTIS{" "}
            {absentes.length > 1 ? "ne sont" : "n'est"} plus dans Sage sur cette période : supprimée
            {absentes.length > 1 ? "s" : ""} ou modifiée{absentes.length > 1 ? "s" : ""} dans Sage.
            Celles cochées « Supprimer » seront supprimées à la validation.
          </Message>
          <DataTable
            columns={absentesColumns}
            rows={absentes}
            getRowKey={(absente) => String(absente.id)}
            isRowMuted={(absente) => !supprimees.has(absente.id)}
          />
        </div>
      )}

      {!importe && (
        <CheckAllButtons
          checked={coches.size}
          total={cochesParDefaut(lignes).size}
          onCheckAll={() => onCoches(cochesParDefaut(lignes))}
          onUncheckAll={() => onCoches(new Set())}
          selection={coches}
          groupes={[
            {
              label: "Erreurs",
              numeros: lignes.filter((l) => l.statut === "Erreur").map((l) => l.numero),
            },
          ]}
          onGroupe={(numeros, cocher) => onCoches(basculerGroupe(coches, numeros, cocher))}
        />
      )}
      <DataTable
        columns={columns}
        rows={pageView.rows}
        getRowKey={(line) => String(line.numero)}
        isRowMuted={(line) => !coches.has(line.numero)}
        emptyMessage={
          vue === "toutes"
            ? "Aucune écriture de ce compte dans Sage sur cette période."
            : "Aucune ligne dans ce filtre."
        }
      />
      {shown.length > 0 && (
        <Pagination
          label={`Pages du grand livre ${compte.bank_code}`}
          page={pageView.page}
          pages={pageView.pages}
          total={shown.length}
          noun="ligne"
          onPage={setPage}
        />
      )}

      {!importe && (
        <div className="mt-4 flex flex-wrap items-center justify-end gap-3">
          <p
            className={cn(
              "mr-auto flex items-center gap-2 text-sm",
              blocage ? "font-medium text-simtis-danger-fg" : "text-simtis-muted",
            )}
            aria-live="polite"
          >
            {blocage ? (
              <>
                <CircleAlert className="h-4 w-4 shrink-0" aria-hidden />
                {blocage.message}
              </>
            ) : (
              messageConfirmation(coches.size, supprimees.size)
            )}
          </p>
          <Button icon={Upload} onClick={onValider} disabled={busy || blocage !== null}>
            {busy ? "Import en cours..." : "Valider ce compte"}
          </Button>
        </div>
      )}
    </section>
  );
}
