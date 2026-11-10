"use client";

import { Ban, Check, Undo2, X } from "lucide-react";
import { useEffect, useState } from "react";

import { CodeBadge } from "@/components/rapprochement/CodeBadge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/ErrorState";
import { Field, TextInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import { absolute, montantEcriture, uniteEcriture } from "@/lib/reconciliation";
import {
  cancelPaireImpaye,
  listPairesImpayes,
  rejectMatches,
  validateMatches,
} from "@/services/reconciliation";
import type { PaireImpaye } from "@/types/reconciliation";
import type { Ecriture } from "@/types/accounting";

type Vue = "Proposée" | "Validée";
type LoadState = "loading" | "error" | "ready";

const VUES: { value: Vue; label: string }[] = [
  { value: "Proposée", label: "À valider" },
  { value: "Validée", label: "Rapprochés" },
];

function EcritureCell({ ecriture }: { ecriture: Ecriture }) {
  return (
    <div className="min-w-56">
      <p className="text-xs text-simtis-muted tabular-nums">{formatDate(ecriture.date_ecriture)}</p>
      <p className="text-simtis-text">{ecriture.libelle}</p>
    </div>
  );
}

/**
 * Impayés Sage ↔ écritures d'origine (décision du 09/11/2026) : après le rapprochement avec la
 * banque, le moteur propose de rapprocher entre elles deux écritures restées libres, un impayé
 * (« IMP … ») et le chèque ou l'effet qu'il annule (même compte, même n°, montant opposé). Un
 * humain valide : les deux écritures passent « Rapprochée » avec un code.
 */
export function ImpayesOriginesCard({
  companyId,
  bankAccountId,
  from,
  to,
  canValidate,
  reloadKey,
  onChanged,
}: {
  companyId: number;
  bankAccountId?: number;
  /** Période de la date de l'impayé (10/11/2026). */
  from?: string;
  to?: string;
  canValidate: boolean;
  reloadKey: number;
  onChanged: (message: string) => void;
}) {
  const { toast } = useToast();
  const [vue, setVue] = useState<Vue>("Proposée");
  const [paires, setPaires] = useState<PaireImpaye[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [retryKey, setRetryKey] = useState(0);
  const [cochees, setCochees] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [aAnnuler, setAAnnuler] = useState<PaireImpaye | null>(null);
  const [motif, setMotif] = useState("");

  useEffect(() => {
    let cancelled = false;
    listPairesImpayes(companyId, vue, { bankAccountId, from, to }).then(
      (result) => {
        if (cancelled) return;
        setPaires(result.paires);
        setCochees(new Set());
        setState("ready");
      },
      () => {
        if (!cancelled) setState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [companyId, vue, bankAccountId, from, to, reloadKey, retryKey]);

  function changerVue(value: Vue) {
    if (value === vue) return;
    setState("loading");
    setVue(value);
  }

  function basculer(id: number) {
    setCochees((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function decider(action: "valider" | "rejeter") {
    const ids = [...cochees];
    setBusy(true);
    try {
      if (action === "valider") {
        const { nb_validees } = await validateMatches(ids);
        onChanged(
          `${nb_validees} impayé${nb_validees > 1 ? "s" : ""} rapproché(s) avec l'origine.`,
        );
      } else {
        const { nb_traitees } = await rejectMatches(ids);
        onChanged(`${nb_traitees} proposition${nb_traitees > 1 ? "s" : ""} rejetée(s).`);
      }
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Action impossible.", "error");
    } finally {
      setBusy(false);
    }
  }

  async function annuler() {
    if (!aAnnuler) return;
    setBusy(true);
    try {
      await cancelPaireImpaye(aAnnuler.id, motif.trim());
      setAAnnuler(null);
      setMotif("");
      onChanged("Rapprochement annulé : les deux écritures sont de nouveau libres.");
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Annulation impossible.", "error");
    } finally {
      setBusy(false);
    }
  }

  const decision = vue === "Proposée" && canValidate;
  const toutes = paires.length > 0 && paires.every((paire) => cochees.has(paire.id));
  const columns: Column<PaireImpaye>[] = [
    ...(decision
      ? [
          {
            key: "choix",
            header: "",
            render: (row: PaireImpaye) => (
              <input
                type="checkbox"
                checked={cochees.has(row.id)}
                disabled={busy}
                onChange={() => basculer(row.id)}
                aria-label={`Sélectionner ${row.impaye.libelle}`}
                className="h-4 w-4 accent-simtis-primary"
              />
            ),
          },
        ]
      : []),
    {
      key: "impaye",
      header: "Impayé",
      render: (row) => <EcritureCell ecriture={row.impaye} />,
    },
    {
      key: "origine",
      header: "Écriture d'origine",
      render: (row) => <EcritureCell ecriture={row.origine} />,
    },
    {
      key: "montant",
      header: "Montant",
      align: "right",
      render: (row) => (
        <span className="whitespace-nowrap tabular-nums">
          {formatAmount(absolute(montantEcriture(row.impaye)), uniteEcriture(row.impaye))}
        </span>
      ),
    },
    {
      key: "banque",
      header: "Banque",
      render: (row) => row.impaye.bank_code ?? "-",
    },
    {
      key: "ecart",
      header: "Écart",
      align: "right",
      render: (row) => (row.ecart_jours === null ? "-" : `${row.ecart_jours} j`),
    },
    ...(vue === "Validée"
      ? [
          {
            key: "code",
            header: "Code",
            render: (row: PaireImpaye) => <CodeBadge code={row.code} />,
          },
          {
            key: "valide_par",
            header: "Validé par",
            render: (row: PaireImpaye) => (
              <span className="whitespace-nowrap">
                {row.valide_par ?? "-"}
                {row.valide_le && (
                  <span className="block text-xs text-simtis-muted">
                    {formatDate(row.valide_le.slice(0, 10))}
                  </span>
                )}
              </span>
            ),
          },
          ...(canValidate
            ? [
                {
                  key: "annuler",
                  header: "",
                  render: (row: PaireImpaye) => (
                    <Button
                      variant="ghost"
                      icon={Undo2}
                      onClick={() => setAAnnuler(row)}
                      disabled={busy}
                    >
                      Annuler
                    </Button>
                  ),
                },
              ]
            : []),
        ]
      : []),
  ];

  return (
    <Card
      title="Impayés ↔ écritures d'origine"
      icon={Undo2}
      headerExtra={
        <div className="flex gap-1" role="tablist" aria-label="Impayés : vue">
          {VUES.map((item) => (
            <button
              key={item.value}
              type="button"
              role="tab"
              aria-selected={vue === item.value}
              onClick={() => changerVue(item.value)}
              className={cn(
                "rounded-full px-3 py-1 text-sm font-medium transition-colors duration-150",
                vue === item.value
                  ? "bg-simtis-primary text-white"
                  : "bg-simtis-surface text-simtis-muted hover:text-simtis-primary",
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
      }
    >
      <p className="mb-4 text-sm text-simtis-muted">
        Après le rapprochement avec la banque, un impayé Sage resté libre est proposé avec le chèque
        ou l&apos;effet qu&apos;il annule : même compte, même numéro, montant opposé, origine datée
        avant l&apos;impayé.
      </p>
      {state === "loading" && <LoadingState rows={3} />}
      {state === "error" && (
        <ErrorState
          message="Impossible de charger les impayés."
          onRetry={() => {
            setState("loading");
            setRetryKey((key) => key + 1);
          }}
        />
      )}
      {state === "ready" && (
        <>
          {decision && paires.length > 0 && (
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Button
                variant="secondary"
                onClick={() =>
                  setCochees(toutes ? new Set() : new Set(paires.map((paire) => paire.id)))
                }
                disabled={busy}
              >
                {toutes ? "Tout décocher" : "Tout cocher"}
              </Button>
              <Button
                icon={Check}
                onClick={() => decider("valider")}
                disabled={busy || cochees.size === 0}
              >
                Valider la sélection ({cochees.size})
              </Button>
              <Button
                variant="danger"
                icon={Ban}
                onClick={() => decider("rejeter")}
                disabled={busy || cochees.size === 0}
              >
                Rejeter la sélection ({cochees.size})
              </Button>
            </div>
          )}
          <DataTable
            columns={columns}
            rows={paires}
            getRowKey={(row) => String(row.id)}
            isRowSelected={decision ? (row) => cochees.has(row.id) : undefined}
            emptyMessage={
              vue === "Proposée"
                ? "Aucun impayé à rapprocher avec son origine : lancez le rapprochement."
                : "Aucun impayé rapproché avec son origine."
            }
          />
        </>
      )}
      <Modal
        open={aAnnuler !== null}
        onClose={() => setAAnnuler(null)}
        title="Annuler le rapprochement"
        footer={
          <>
            <Button variant="secondary" icon={X} onClick={() => setAAnnuler(null)}>
              Retour
            </Button>
            <Button
              variant="danger"
              icon={Undo2}
              disabled={busy || motif.trim() === ""}
              onClick={annuler}
            >
              Annuler le rapprochement
            </Button>
          </>
        }
      >
        <Field label="Motif" htmlFor="motif-annulation-impaye" required>
          <TextInput
            id="motif-annulation-impaye"
            value={motif}
            maxLength={500}
            onChange={(event) => setMotif(event.target.value)}
          />
        </Field>
      </Modal>
    </Card>
  );
}
