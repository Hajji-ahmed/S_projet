"use client";

import { Ban, Download, History, Search, X } from "lucide-react";
import { useEffect, useState } from "react";

import { ScoreBadge } from "@/components/rapprochement/Score";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { CodeBadge } from "@/components/rapprochement/CodeBadge";
import { ErrorState } from "@/components/ui/ErrorState";
import { Field, TextInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { Pagination } from "@/components/ui/Pagination";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { normalizeAmountInput } from "@/lib/accounts";
import { pageCount } from "@/lib/accounting";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/balances";
import { formatAmount, formatNombre } from "@/lib/format";
import {
  unite,
  lettrageFilename,
  absolute,
  montantBanque,
  nbEcritures,
  nbOperations,
  type ReconciliationFilter,
} from "@/lib/reconciliation";
import { formatDateTime, saveFile } from "@/lib/statements";
import { cancelMatch, exportLettrage, listHistory } from "@/services/reconciliation";
import type { Correspondance, Historique } from "@/types/reconciliation";

/** Filtres de l'historique (17/11/2026) : texte et montant (total des opérations). */
type Recherche = { q: string; montant: string };
const SANS_FILTRE: Recherche = { q: "", montant: "" };

type HistoryTabProps = {
  companyId: number;
  filter: ReconciliationFilter;
  canValidate: boolean;
  reloadKey: number;
  /** Après une annulation : la vue recharge tout et affiche le message. */
  onChanged: (message: string) => void;
};

/**
 * Onglet « Historique » : les rapprochements validés de la période et du compte choisis, les plus
 * récents d'abord, avec qui et quand (rejets et annulations ne sont plus montrés, 17/11/2026) ;
 * recherche (code, libellé, pièce, référence) et montant ; annulation d'un rapprochement validé
 * (motif obligatoire). Remonté (key) quand la période ou le compte change.
 */
export function HistoryTab({
  companyId,
  filter,
  canValidate,
  reloadKey,
  onChanged,
}: HistoryTabProps) {
  const [recherche, setRecherche] = useState<Recherche>(SANS_FILTRE);
  const [saisie, setSaisie] = useState<Recherche>(SANS_FILTRE);
  const [montantInvalide, setMontantInvalide] = useState(false);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Historique | null>(null);
  const [state, setState] = useState<"loading" | "error" | "ready">("loading");
  const [retryKey, setRetryKey] = useState(0);
  const [cancelling, setCancelling] = useState<Correspondance | null>(null);
  const [motif, setMotif] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    let cancelled = false;
    listHistory(companyId, filter, {
      statut: "Validée",
      q: recherche.q || undefined,
      montant: recherche.montant || undefined,
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
  }, [companyId, filter, recherche, page, reloadKey, retryKey]);

  async function exporter() {
    setExporting(true);
    try {
      saveFile(await exportLettrage(companyId, filter), lettrageFilename(filter));
    } catch (failure) {
      toast(failure instanceof ApiError ? failure.message : "L'export a échoué.", "error");
    } finally {
      setExporting(false);
    }
  }

  function rechercher() {
    const texte = saisie.montant.trim();
    const montant = texte ? normalizeAmountInput(texte) : "";
    if (montant === null) {
      setMontantInvalide(true);
      return;
    }
    setMontantInvalide(false);
    setState("loading");
    setPage(1);
    setRecherche({ q: saisie.q.trim(), montant });
  }

  function effacer() {
    setSaisie(SANS_FILTRE);
    setMontantInvalide(false);
    setState("loading");
    setPage(1);
    setRecherche(SANS_FILTRE);
  }

  const filtre = recherche.q !== "" || recherche.montant !== "";

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
    { key: "code", header: "Code", render: (row) => <CodeBadge code={row.code} /> },
    {
      key: "operation",
      header: "Opération",
      render: (row) => (
        <span className="block min-w-[180px]">
          <span className="block">{row.operation.libelle}</span>
          <span className="block text-xs text-simtis-muted">
            {formatDate(row.operation.date_operation)} · {row.operation.bank_code}
            {nbOperations(row) > 1 && ` · groupe de ${nbOperations(row)} opérations`}
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
            {nbEcritures(row) > 1 && ` · ${nbEcritures(row)} écritures`}
          </span>
        </span>
      ),
    },
    {
      key: "montant",
      header: "Montant",
      align: "right",
      render: (row) => formatAmount(absolute(montantBanque(row)), unite(row.operation.devise)),
    },
    {
      key: "score",
      header: "Score",
      render: (row) => <ScoreBadge score={row.score} forte={row.forte} />,
    },
    { key: "origine", header: "Origine" },
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
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-simtis-muted">
          Le lettrage exporte tous les rapprochements validés de la période et du compte choisis.
        </p>
        <Button
          variant="secondary"
          icon={Download}
          disabled={exporting || !data?.par_statut["Validée"]}
          onClick={exporter}
        >
          {exporting ? "Export en cours…" : "Exporter le lettrage"}
        </Button>
      </div>
      <form
        className="mb-4 flex flex-wrap items-end gap-3"
        aria-label="Filtrer les rapprochements validés"
        onSubmit={(event) => {
          event.preventDefault();
          rechercher();
        }}
      >
        <div className="w-full max-w-[280px]">
          <Field label="Recherche" htmlFor="historique-recherche">
            <TextInput
              id="historique-recherche"
              value={saisie.q}
              maxLength={100}
              placeholder="Code, libellé, pièce, référence"
              onChange={(event) => setSaisie({ ...saisie, q: event.target.value })}
            />
          </Field>
        </div>
        <div className="w-full max-w-[180px]">
          <Field
            label="Montant"
            htmlFor="historique-montant"
            error={montantInvalide ? "Montant invalide, ex. 10 000,00" : undefined}
          >
            <TextInput
              id="historique-montant"
              inputMode="decimal"
              value={saisie.montant}
              placeholder="10 000,00"
              invalid={montantInvalide}
              onChange={(event) => setSaisie({ ...saisie, montant: event.target.value })}
            />
          </Field>
        </div>
        <Button type="submit" variant="secondary" icon={Search}>
          Rechercher
        </Button>
        {filtre && (
          <Button variant="ghost" icon={X} onClick={effacer}>
            Effacer les filtres
          </Button>
        )}
      </form>
      {state === "ready" && data && (
        <p className="mb-3 text-sm text-simtis-muted">
          <span className="font-semibold text-simtis-text tabular-nums">
            {formatNombre(data.total)}
          </span>{" "}
          {data.total > 1 ? "rapprochements validés" : "rapprochement validé"}
        </p>
      )}

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
            emptyMessage={
              filtre
                ? "Aucun rapprochement validé ne correspond à ces filtres."
                : "Aucun rapprochement validé sur cette période."
            }
          />
          <Pagination
            label="Pages de l'historique"
            page={data.page}
            pages={pages}
            total={data.total}
            noun="rapprochement"
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
