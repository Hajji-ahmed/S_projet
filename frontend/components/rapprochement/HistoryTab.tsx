"use client";

import { Ban, History } from "lucide-react";
import { useEffect, useState } from "react";

import { Pagination } from "@/components/rapprochement/TransactionsPane";
import { ScoreBadge } from "@/components/rapprochement/Score";
import { StatButton } from "@/components/rapprochement/StatButton";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/ErrorState";
import { Field, TextInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { pageCount } from "@/lib/accounting";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import { absolute, toggleStatut, type ReconciliationFilter } from "@/lib/reconciliation";
import { formatDateTime } from "@/lib/statements";
import { cancelMatch, listHistory } from "@/services/reconciliation";
import type { Correspondance, Historique, StatutDecision } from "@/types/reconciliation";

const STATUTS: { statut: StatutDecision; label: string }[] = [
  { statut: "Validée", label: "Validées" },
  { statut: "Rejetée", label: "Rejetées" },
  { statut: "Annulée", label: "Annulées" },
];

// Couleur du statut d'une décision : mêmes familles que les badges de rapprochement
const DECISION_STYLES: Record<StatutDecision, string> = {
  Validée: "bg-simtis-success-bg text-simtis-success-fg",
  Rejetée: "bg-simtis-danger-bg text-simtis-danger-fg",
  Annulée: "bg-simtis-neutral-bg text-simtis-neutral-fg",
};

type HistoryTabProps = {
  companyId: number;
  filter: ReconciliationFilter;
  canValidate: boolean;
  reloadKey: number;
  /** Après une annulation : la vue recharge tout et affiche le message. */
  onChanged: (message: string) => void;
};

/**
 * Onglet « Historique » : toutes les décisions (validées, rejetées, annulées) de la période et du
 * compte choisis, les plus récentes d'abord, avec qui et quand ; annulation d'un rapprochement
 * validé (motif obligatoire). Remonté (key) quand la période ou le compte change.
 */
export function HistoryTab({
  companyId,
  filter,
  canValidate,
  reloadKey,
  onChanged,
}: HistoryTabProps) {
  const [statut, setStatut] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Historique | null>(null);
  const [state, setState] = useState<"loading" | "error" | "ready">("loading");
  const [retryKey, setRetryKey] = useState(0);
  const [cancelling, setCancelling] = useState<Correspondance | null>(null);
  const [motif, setMotif] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listHistory(companyId, filter, {
      statut: (statut || undefined) as StatutDecision | undefined,
      page,
    }).then(
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
  }, [companyId, filter, statut, page, reloadKey, retryKey]);

  function changeStatut(next: string) {
    setState("loading");
    setPage(1);
    setStatut(next);
  }

  async function confirmCancel() {
    if (!cancelling) return;
    setBusy(true);
    setError(null);
    try {
      await cancelMatch(cancelling.id, motif.trim());
      setCancelling(null);
      setMotif("");
      onChanged("Rapprochement annulé.");
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<Correspondance>[] = [
    {
      key: "decide_le",
      header: "Décision",
      render: (row) => (
        <span className="whitespace-nowrap">
          <span className="block">{row.decide_le ? formatDateTime(row.decide_le) : "-"}</span>
          <span className="block text-xs text-simtis-muted">{row.decide_par ?? "-"}</span>
        </span>
      ),
    },
    {
      key: "statut",
      header: "Statut",
      render: (row) => (
        <span
          className={cn(
            "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
            DECISION_STYLES[row.statut as StatutDecision],
          )}
        >
          {row.statut}
        </span>
      ),
    },
    {
      key: "operation",
      header: "Opération",
      render: (row) => (
        <span className="block min-w-[180px]">
          <span className="block">{row.operation.libelle}</span>
          <span className="block text-xs text-simtis-muted">
            {formatDate(row.operation.date_operation)} · {row.operation.bank_code}
          </span>
        </span>
      ),
    },
    {
      key: "ecriture",
      header: "Écriture",
      render: (row) => (
        <span className="block min-w-[180px]">
          <span className="block">{row.ecriture.libelle}</span>
          <span className="block text-xs text-simtis-muted">
            {formatDate(row.ecriture.date_ecriture)}
            {row.ecriture.numero_piece && ` · Pièce ${row.ecriture.numero_piece}`}
          </span>
        </span>
      ),
    },
    {
      key: "montant",
      header: "Montant",
      align: "right",
      render: (row) => formatAmount(absolute(row.operation.montant), "DH"),
    },
    {
      key: "score",
      header: "Score",
      render: (row) => <ScoreBadge score={row.score} forte={row.forte} />,
    },
    { key: "origine", header: "Origine" },
    {
      key: "commentaire",
      header: "Commentaire",
      render: (row) => <span className="block min-w-[140px]">{row.commentaire ?? "-"}</span>,
    },
    ...(canValidate
      ? [
          {
            key: "actions",
            header: "",
            align: "right" as const,
            render: (row: Correspondance) =>
              row.statut === "Validée" && (
                <Button
                  variant="ghost"
                  icon={Ban}
                  onClick={() => {
                    setError(null);
                    setMotif("");
                    setCancelling(row);
                  }}
                  aria-label={`Annuler le rapprochement de ${row.operation.libelle}`}
                >
                  Annuler
                </Button>
              ),
          },
        ]
      : []),
  ];

  const pages = data ? pageCount(data.total, data.taille) : 1;

  return (
    <Card title="Historique des rapprochements" icon={History}>
      <div
        className="mb-4 grid grid-cols-3 gap-2 text-sm sm:max-w-xl"
        role="group"
        aria-label="Filtrer par décision"
      >
        {STATUTS.map(({ statut: value, label }) => (
          <StatButton
            key={value}
            label={label}
            value={data?.par_statut[value]}
            active={statut === value}
            onClick={() => changeStatut(toggleStatut(statut, value))}
          />
        ))}
      </div>

      {state === "loading" && <LoadingState rows={5} />}
      {state === "error" && (
        <ErrorState
          message="Impossible de charger l'historique."
          onRetry={() => {
            setState("loading");
            setRetryKey((key) => key + 1);
          }}
        />
      )}
      {state === "ready" && data && (
        <>
          <DataTable
            columns={columns}
            rows={data.decisions}
            getRowKey={(row) => String(row.id)}
            emptyMessage="Aucune décision sur cette période."
          />
          <Pagination
            label="Pages de l'historique"
            page={data.page}
            pages={pages}
            total={data.total}
            noun="décision"
            onPage={(next) => {
              setState("loading");
              setPage(next);
            }}
          />
        </>
      )}

      <Modal
        open={cancelling !== null}
        onClose={() => setCancelling(null)}
        title="Annuler le rapprochement"
        footer={
          <>
            <Button variant="secondary" onClick={() => setCancelling(null)}>
              Retour
            </Button>
            <Button
              variant="danger"
              icon={Ban}
              disabled={busy || !motif.trim()}
              onClick={confirmCancel}
            >
              Annuler le rapprochement
            </Button>
          </>
        }
      >
        {error && (
          <p
            role="alert"
            className="mb-3 rounded-[10px] bg-simtis-danger-bg px-3 py-2 text-simtis-danger-fg"
          >
            {error}
          </p>
        )}
        <p className="mb-4 text-simtis-muted">
          L&apos;opération et l&apos;écriture redeviennent « Non rapprochée ». L&apos;annulation
          reste dans l&apos;historique.
        </p>
        <Field label="Motif" htmlFor="historique-motif" required>
          <TextInput
            id="historique-motif"
            value={motif}
            maxLength={500}
            onChange={(event) => setMotif(event.target.value)}
          />
        </Field>
      </Modal>
    </Card>
  );
}
