"use client";

import { BookText, ChevronLeft, ChevronRight, Eye, Plus, Search, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";

import { AccountChipLabel } from "@/components/banks/AccountChipLabel";
import { BankLabel } from "@/components/banks/BankLabel";
import { CodeBadge } from "@/components/rapprochement/CodeBadge";
import { EntryDetailModal } from "@/components/ecritures/EntryDetailModal";
import { ManualEntryModal } from "@/components/ecritures/ManualEntryModal";
import { DeleteImportModal } from "@/components/imports/DeleteImportModal";
import { useToast } from "@/components/ui/Toast";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/ErrorState";
import { DateInput, Field, Select, TextInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { STATUTS_RAPPROCHEMENT, pageCount, type EntriesFilter } from "@/lib/accounting";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import { unite } from "@/lib/reconciliation";
import { listEntries, supprimerEcriture } from "@/services/accounting";
import type { Account } from "@/types/account";
import type { Ecriture, EcrituresPage } from "@/types/accounting";
import type { Status } from "@/types/status";

type EntriesCardProps = {
  companyId: number;
  /** Comptes qui ont un journal Sage : un bouton de filtre chacun. */
  accounts: Account[];
  logos: Map<string, string | null>;
  /** Incrémenté après un import : la liste est rechargée. */
  reloadKey: number;
  /** Permission « Import Sage » : saisie et suppression d'une écriture (24/10/2026). */
  canEdit?: boolean;
};

/**
 * Écritures importées de Sage, en lecture seule : filtres (compte, période, statut, recherche),
 * 50 par page de la plus récente à la plus ancienne (pagination par l'API), détail d'une écriture.
 */
export function EntriesCard({
  companyId,
  accounts,
  logos,
  reloadKey,
  canEdit = false,
}: EntriesCardProps) {
  const { toast } = useToast();
  const [ajout, setAjout] = useState(false);
  const [aSupprimer, setASupprimer] = useState<Ecriture | null>(null);
  const [filter, setFilter] = useState<EntriesFilter>({ page: 1 });
  const [search, setSearch] = useState("");
  const [data, setData] = useState<EcrituresPage | null>(null);
  const [state, setState] = useState<"loading" | "error" | "ready">("loading");
  const [retryKey, setRetryKey] = useState(0);
  const [detail, setDetail] = useState<Ecriture | null>(null);

  useEffect(() => {
    let cancelled = false;
    listEntries(companyId, filter).then(
      (result) => {
        if (cancelled) return;
        setData(result);
        setState("ready");
      },
      () => {
        if (!cancelled) setState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [companyId, filter, reloadKey, retryKey]);

  /** Changer un filtre revient à la première page. */
  function change(next: Partial<EntriesFilter>) {
    setState("loading");
    setFilter((current) => ({ ...current, ...next, page: next.page ?? 1 }));
  }

  const pages = data ? pageCount(data.total, data.taille) : 1;
  const filtered =
    filter.bankAccountId !== undefined ||
    !!filter.from ||
    !!filter.to ||
    !!filter.statut ||
    !!filter.q;

  const columns: Column<Ecriture>[] = [
    {
      key: "date_ecriture",
      header: "Date",
      render: (row) => <span className="whitespace-nowrap">{formatDate(row.date_ecriture)}</span>,
    },
    { key: "journal", header: "Journal", render: (row) => row.journal ?? "-" },
    {
      key: "bank_code",
      header: "Compte bancaire",
      render: (row) =>
        row.bank_code ? <BankLabel code={row.bank_code} logo={logos.get(row.bank_code)} /> : "-",
    },
    {
      key: "numero_piece",
      header: "N° pièce",
      render: (row) => <span className="whitespace-nowrap">{row.numero_piece ?? "-"}</span>,
    },
    {
      key: "libelle",
      header: "Libellé",
      render: (row) => (
        <span className="block min-w-[220px]">
          <span className="block">{row.libelle}</span>
          {row.reference && (
            <span className="block text-xs text-simtis-muted">Réf. {row.reference}</span>
          )}
          {row.origine === "Manuelle" && (
            <span className="block text-xs font-medium text-simtis-warning-fg">
              Saisie manuelle
            </span>
          )}
        </span>
      ),
    },
    {
      key: "debit",
      header: "Débit",
      align: "right",
      render: (row) => formatAmount(row.debit, "DH", { dashForZero: true }),
    },
    {
      key: "credit",
      header: "Crédit",
      align: "right",
      render: (row) => formatAmount(row.credit, "DH", { dashForZero: true }),
    },
    {
      key: "montant_devise",
      header: "Devise",
      align: "right",
      // Compte en devise : colonne « Devise » de Sage, rapprochée du relevé (14/10/2026)
      render: (row) =>
        row.montant_devise != null ? formatAmount(row.montant_devise, unite(row.devise)) : "-",
    },
    {
      key: "echeance",
      header: "Échéance",
      render: (row) => <span className="whitespace-nowrap">{formatDate(row.echeance)}</span>,
    },
    { key: "tiers", header: "Tiers", render: (row) => row.tiers ?? "-" },
    {
      key: "statut",
      header: "Statut",
      render: (row) => <StatusBadge status={row.statut as Status} />,
    },
    {
      key: "code_rapprochement",
      header: "Code rapprochement",
      render: (row) => <CodeBadge code={row.code_rapprochement} />,
    },
    {
      key: "actions",
      header: "Détail",
      align: "right",
      render: (row) => (
        <span className="inline-flex gap-1">
          <button
            type="button"
            onClick={() => setDetail(row)}
            aria-label={`Voir l'écriture du ${formatDate(row.date_ecriture)} ${row.libelle}`}
            className="rounded-lg p-2 text-simtis-muted transition-colors hover:bg-simtis-light hover:text-simtis-primary"
          >
            <Eye className="h-4 w-4" aria-hidden />
          </button>
          {canEdit && row.origine !== "SIMTIS" && (
            <button
              type="button"
              onClick={() => setASupprimer(row)}
              disabled={row.statut === "Rapprochée"}
              aria-label={`Supprimer l'écriture du ${formatDate(row.date_ecriture)} ${row.libelle}`}
              title={
                row.statut === "Rapprochée"
                  ? "Écriture rapprochée : annulez d'abord son rapprochement"
                  : "Supprimer cette écriture"
              }
              className="rounded-lg p-2 text-simtis-danger-fg transition-colors hover:bg-simtis-danger-bg disabled:pointer-events-none disabled:opacity-40"
            >
              <Trash2 className="h-4 w-4" aria-hidden />
            </button>
          )}
        </span>
      ),
    },
  ];

  return (
    <Card title="Écritures" icon={BookText}>
      {canEdit && accounts.length > 0 && (
        <div className="mb-3 flex justify-end">
          <Button variant="secondary" icon={Plus} onClick={() => setAjout(true)}>
            Ajouter une écriture
          </Button>
        </div>
      )}
      {ajout && (
        <ManualEntryModal
          accounts={accounts}
          compteInitial={filter.bankAccountId}
          onClose={() => setAjout(false)}
          onSaved={() => {
            setAjout(false);
            toast("Écriture ajoutée.");
            setRetryKey((key) => key + 1);
          }}
        />
      )}
      {aSupprimer && (
        <DeleteImportModal
          titre="Supprimer cette écriture ?"
          bouton="Supprimer l'écriture"
          avertissement="Cette ligne sera supprimée (refusé si elle est rapprochée : annulez d'abord son rapprochement). Ses propositions en attente sont retirées. La suppression est tracée dans l'Historique."
          fichier={aSupprimer.libelle}
          resume={`${formatDate(aSupprimer.date_ecriture)} · ${aSupprimer.journal ?? "-"} · ${formatAmount(aSupprimer.montant, "DH")}`}
          onClose={() => setASupprimer(null)}
          onConfirm={async (motif) => {
            await supprimerEcriture(aSupprimer.id, motif);
            setASupprimer(null);
            toast("Écriture supprimée.");
            setRetryKey((key) => key + 1);
          }}
        />
      )}
      {/* Compte bancaire : une seule ligne qui défile sur mobile */}
      <div
        className="mb-4 flex gap-2 overflow-x-auto pb-1"
        role="group"
        aria-label="Compte bancaire"
      >
        <AccountButton
          active={filter.bankAccountId === undefined}
          onClick={() => change({ bankAccountId: undefined })}
        >
          Tous les comptes
        </AccountButton>
        {accounts.map((account) => (
          <AccountButton
            key={account.id}
            active={filter.bankAccountId === account.id}
            onClick={() => change({ bankAccountId: account.id })}
          >
            <AccountChipLabel account={account} />
          </AccountButton>
        ))}
      </div>

      <form
        className="mb-4 flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          change({ q: search.trim() || undefined });
        }}
      >
        <div className="w-full max-w-[170px]">
          <Field label="Du" htmlFor="ecritures-du">
            <DateInput
              id="ecritures-du"
              value={filter.from ?? ""}
              onChange={(event) => change({ from: event.target.value || undefined })}
            />
          </Field>
        </div>
        <div className="w-full max-w-[170px]">
          <Field label="Au" htmlFor="ecritures-au">
            <DateInput
              id="ecritures-au"
              value={filter.to ?? ""}
              onChange={(event) => change({ to: event.target.value || undefined })}
            />
          </Field>
        </div>
        <div className="w-full max-w-[190px]">
          <Field label="Statut" htmlFor="ecritures-statut">
            <Select
              id="ecritures-statut"
              value={filter.statut ?? ""}
              placeholder="Tous les statuts"
              options={STATUTS_RAPPROCHEMENT.map((statut) => ({ value: statut, label: statut }))}
              onChange={(event) => change({ statut: event.target.value || undefined })}
            />
          </Field>
        </div>
        <div className="w-full max-w-[260px]">
          <Field label="Recherche" htmlFor="ecritures-recherche">
            <TextInput
              id="ecritures-recherche"
              value={search}
              maxLength={100}
              placeholder="Libellé, pièce, référence, tiers, code"
              onChange={(event) => setSearch(event.target.value)}
            />
          </Field>
        </div>
        <Button type="submit" variant="secondary" icon={Search}>
          Rechercher
        </Button>
        {filtered && (
          <Button
            variant="ghost"
            icon={X}
            onClick={() => {
              setSearch("");
              setState("loading");
              setFilter({ page: 1 });
            }}
          >
            Effacer les filtres
          </Button>
        )}
      </form>

      {state === "loading" && <LoadingState rows={5} />}
      {state === "error" && (
        <ErrorState
          message="Impossible de charger les écritures."
          onRetry={() => {
            setState("loading");
            setRetryKey((key) => key + 1);
          }}
        />
      )}
      {state === "ready" && data && (
        <>
          <dl
            className="mb-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-3"
            aria-label="Résumé des écritures"
          >
            <div>
              <dt className="text-simtis-muted">Écritures</dt>
              <dd className="font-medium tabular-nums">{data.total}</dd>
            </div>
            <div>
              <dt className="text-simtis-muted">Total débit</dt>
              <dd className="font-medium tabular-nums">{formatAmount(data.total_debit, "DH")}</dd>
            </div>
            <div>
              <dt className="text-simtis-muted">Total crédit</dt>
              <dd className="font-medium tabular-nums">{formatAmount(data.total_credit, "DH")}</dd>
            </div>
          </dl>
          <DataTable
            columns={columns}
            rows={data.ecritures}
            getRowKey={(row) => String(row.id)}
            emptyMessage="Aucune écriture sur ces critères."
          />
          {data.total > data.taille && (
            <nav
              aria-label="Pages des écritures"
              className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm"
            >
              <p className="text-simtis-muted">
                Page {data.page} sur {pages}
              </p>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  icon={ChevronLeft}
                  disabled={data.page <= 1}
                  onClick={() => change({ page: data.page - 1 })}
                >
                  Précédent
                </Button>
                <Button
                  variant="secondary"
                  icon={ChevronRight}
                  disabled={data.page >= pages}
                  onClick={() => change({ page: data.page + 1 })}
                >
                  Suivant
                </Button>
              </div>
            </nav>
          )}
        </>
      )}
      {detail && (
        <EntryDetailModal
          entryId={detail.id}
          date={detail.date_ecriture}
          logos={logos}
          onClose={() => setDetail(null)}
        />
      )}
    </Card>
  );
}

/** Bouton de filtre par compte bancaire (aussi utilisé par l'écran Rapprochement). */
export function AccountButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "shrink-0 rounded-[10px] border px-3 py-2 text-sm font-medium transition-colors duration-200",
        active
          ? "border-simtis-primary bg-simtis-light text-simtis-primary-dark"
          : "border-simtis-border bg-simtis-card text-simtis-text hover:bg-simtis-light/50",
      )}
    >
      {children}
    </button>
  );
}
