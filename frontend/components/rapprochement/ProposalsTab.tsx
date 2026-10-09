"use client";

import { CheckCheck, ListChecks, X } from "lucide-react";
import { useState } from "react";

import { SignalDiscrepancyModal } from "@/components/ecarts/SignalDiscrepancyModal";
import { AmbiguousCard } from "@/components/rapprochement/AmbiguousCard";
import { ProposalCard } from "@/components/rapprochement/ProposalCard";
import { StatButton } from "@/components/rapprochement/StatButton";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field, TextInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { ApiError } from "@/lib/api";
import { formatAmount } from "@/lib/format";
import {
  defaultSelection,
  filterProposals,
  LOT_MAX,
  formatScore,
  selectionSummary,
  validable,
  type ProposalsFilter,
} from "@/lib/reconciliation";
import {
  matchManually,
  rejectMatch,
  validateMatch,
  validateMatches,
} from "@/services/reconciliation";
import type { Ambigues, Correspondance, Correspondances, Operation } from "@/types/reconciliation";

type ProposalsTabProps = {
  companyId: number;
  /** Propositions en attente de la période, chargées par la vue (null : en cours). */
  pending: Correspondances | null;
  logos: Map<string, string | null>;
  canValidate: boolean;
  canManageDiscrepancies: boolean;
  /** Après une décision : la vue recharge tout et affiche le message. */
  onChanged: (message: string) => void;
  /** Ouvre la proposition dans l'onglet Rapprochement. */
  onOpen: (item: Correspondance) => void;
  /** Opérations ambiguës (à vérifier sans proposition), chargées par la vue (null : en cours). */
  ambigues: Ambigues | null;
  /** Page des opérations ambiguës (50 par page). */
  onAmbiguPage: (page: number) => void;
  /** Ouvre une opération ambiguë dans l'onglet Rapprochement. */
  onOpenOperation: (operation: Operation) => void;
};

type LignesEcart = {
  operation: { id: number; date: string; libelle: string; montant: string };
  ecriture: { id: number; date: string; libelle: string; montant: string } | null;
};

/** Filtres de l'onglet ; le seuil « forte » vient du serveur (80 depuis le 08/10/2026). */
function filtres(seuil: string): { value: ProposalsFilter; label: string }[] {
  return [
    { value: "toutes", label: "Toutes" },
    { value: "fortes", label: `Fortes (≥ ${seuil})` },
    { value: "a_verifier", label: `À vérifier (< ${seuil})` },
    { value: "ambigues", label: "Ambiguës" },
  ];
}

function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.message : "Une erreur est survenue.";
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n > 1 ? "s" : ""}`;
}

/**
 * Onglet « Propositions » : chaque proposition en grand (transaction | score | écriture), avec
 * Valider / Rejeter, et une barre en bas pour valider la sélection. Seules les fortes sont cochées
 * d'office ; une faible ne l'est que par l'utilisateur, après vérification (décision du 07/10/2026).
 */
export function ProposalsTab({
  companyId,
  pending,
  logos,
  canValidate,
  canManageDiscrepancies,
  onChanged,
  onOpen,
  ambigues,
  onAmbiguPage,
  onOpenOperation,
}: ProposalsTabProps) {
  const items = pending?.correspondances ?? null;
  const [filtre, setFiltre] = useState<ProposalsFilter>("toutes");
  // La sélection repart des fortes à chaque nouvelle liste (après une décision, un rechargement)
  const [selection, setSelection] = useState<{ source: Correspondance[] | null; ids: Set<number> }>(
    () => ({ source: items, ids: items ? defaultSelection(items) : new Set() }),
  );
  if (selection.source !== items) {
    setSelection({ source: items, ids: items ? defaultSelection(items) : new Set() });
  }
  const selected = selection.ids;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [rejecting, setRejecting] = useState<Correspondance | null>(null);
  const [comment, setComment] = useState("");
  const [signaling, setSignaling] = useState<LignesEcart | null>(null);

  if (!items || !ambigues) {
    return (
      <Card title="Propositions en attente" icon={ListChecks}>
        <LoadingState rows={4} />
      </Card>
    );
  }

  const shown = filterProposals(items, filtre);
  const summary = selectionSummary(items, selected);
  const nbFortes = items.filter((item) => item.forte).length;
  const ambiguous = ambigues.ambigues;
  const seuil = formatScore(pending?.seuil_fort ?? ambigues.seuil_fort);
  const shownAmbiguous = filtre === "toutes" || filtre === "ambigues" ? ambiguous : [];
  const nothing = shown.length === 0 && shownAmbiguous.length === 0;

  function setIds(update: (ids: Set<number>) => Set<number>) {
    setSelection((current) => ({ ...current, ids: update(new Set(current.ids)) }));
  }

  async function act(action: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setConfirming(false);
      setRejecting(null);
      setComment("");
      onChanged(message);
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card title="Propositions en attente" icon={ListChecks}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div
            className="grid grid-cols-2 gap-2 text-sm sm:max-w-2xl sm:grid-cols-4"
            role="group"
            aria-label="Filtrer les propositions"
          >
            {filtres(seuil).map(({ value, label }) => (
              <StatButton
                key={value}
                label={label}
                value={
                  value === "toutes"
                    ? items.length + ambigues.total
                    : value === "fortes"
                      ? nbFortes
                      : value === "a_verifier"
                        ? items.length - nbFortes
                        : ambigues.total
                }
                active={filtre === value}
                onClick={() => setFiltre(value)}
              />
            ))}
          </div>
          <p className="max-w-md text-sm text-simtis-muted">
            Les fortes correspondances sont cochées d&apos;office. Cochez une proposition à vérifier
            seulement après l&apos;avoir contrôlée. Une opération ambiguë se rapproche en
            choisissant son écriture.
          </p>
        </div>
        {error && (
          <p
            role="alert"
            className="mt-4 rounded-[10px] bg-simtis-danger-bg px-3 py-2 text-sm text-simtis-danger-fg"
          >
            {error}
          </p>
        )}
      </Card>

      {nothing ? (
        <Card>
          <EmptyState
            icon={ListChecks}
            message={
              items.length + ambigues.total === 0
                ? "Rien à vérifier : lancez le rapprochement sur la période."
                : "Rien dans ce filtre."
            }
          />
        </Card>
      ) : (
        <ul className="space-y-3">
          {shown.map((item) => (
            <li key={item.id}>
              <ProposalCard
                item={item}
                logo={logos.get(item.operation.bank_code)}
                checked={selected.has(item.id)}
                canValidate={canValidate}
                canSignal={canManageDiscrepancies}
                busy={busy}
                onToggle={() =>
                  setIds((ids) => {
                    if (ids.has(item.id)) ids.delete(item.id);
                    else ids.add(item.id);
                    return ids;
                  })
                }
                onValidate={() => act(() => validateMatch(item.id), "Rapprochement validé.")}
                onReject={() => {
                  setComment("");
                  setRejecting(item);
                }}
                onSignal={() =>
                  setSignaling({
                    operation: {
                      id: item.operation.id,
                      date: item.operation.date_operation,
                      libelle: item.operation.libelle,
                      montant: item.operation.montant,
                    },
                    ecriture: {
                      id: item.ecriture.id,
                      date: item.ecriture.date_ecriture,
                      libelle: item.ecriture.libelle,
                      montant: item.ecriture.montant,
                    },
                  })
                }
                onOpen={() => onOpen(item)}
              />
            </li>
          ))}
          {shownAmbiguous.map((item) => (
            <li key={`ambigue-${item.operation.id}`}>
              <AmbiguousCard
                item={item}
                logo={logos.get(item.operation.bank_code)}
                seuilFort={ambigues.seuil_fort}
                canValidate={canValidate}
                canSignal={canManageDiscrepancies}
                busy={busy}
                onChoose={(candidat) =>
                  act(
                    () => matchManually(item.operation.id, candidat.ecriture.id),
                    "Rapprochement enregistré.",
                  )
                }
                onSignal={() =>
                  setSignaling({
                    operation: {
                      id: item.operation.id,
                      date: item.operation.date_operation,
                      libelle: item.operation.libelle,
                      montant: item.operation.montant,
                    },
                    ecriture: null,
                  })
                }
                onOpen={() => onOpenOperation(item.operation)}
              />
            </li>
          ))}
        </ul>
      )}
      {shownAmbiguous.length > 0 && ambigues.total > ambigues.taille && (
        <Pagination
          label="Pages des opérations ambiguës"
          page={ambigues.page}
          pages={Math.ceil(ambigues.total / ambigues.taille)}
          total={ambigues.total}
          noun="opération"
          onPage={onAmbiguPage}
        />
      )}

      {canValidate && items.length > 0 && (
        <div className="sticky bottom-0 z-10 -mx-1 rounded-[14px] border border-simtis-border bg-simtis-card p-4 shadow-simtis">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm">
              <span className="font-semibold">
                {summary.nb} sélectionnée{summary.nb > 1 ? "s" : ""}
              </span>{" "}
              sur {items.length} ·{" "}
              <span className="font-semibold tabular-nums">
                {formatAmount(summary.total, "DH")}
              </span>
              {summary.faibles > 0 && (
                <span className="text-simtis-warning-fg">
                  {" "}
                  · dont {plural(summary.faibles, "proposition")} à vérifier
                </span>
              )}
              {summary.nb > LOT_MAX && (
                <span role="alert" className="block text-simtis-danger-fg">
                  Sélection trop grande ({summary.nb}) : {LOT_MAX} au plus par validation. Filtrez
                  par compte ou par période.
                </span>
              )}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() =>
                  setIds(() => new Set(shown.filter(validable).map((item) => item.id)))
                }
              >
                Tout sélectionner
              </Button>
              <Button
                variant="ghost"
                icon={X}
                disabled={busy || summary.nb === 0}
                onClick={() => setIds(() => new Set())}
              >
                Tout désélectionner
              </Button>
              <Button
                icon={CheckCheck}
                disabled={busy || summary.nb === 0 || summary.nb > LOT_MAX}
                onClick={() => setConfirming(true)}
              >
                Valider la sélection ({summary.nb})
              </Button>
            </div>
          </div>
        </div>
      )}

      <Modal
        open={confirming}
        onClose={() => setConfirming(false)}
        title="Valider la sélection"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirming(false)}>
              Retour
            </Button>
            <Button
              icon={CheckCheck}
              disabled={busy}
              onClick={() =>
                act(
                  () => validateMatches([...selected]),
                  `${plural(summary.nb, "rapprochement")} validé${summary.nb > 1 ? "s" : ""}.`,
                )
              }
            >
              Valider {plural(summary.nb, "rapprochement")}
            </Button>
          </>
        }
      >
        <p>
          {plural(summary.nb, "proposition")} pour un total de{" "}
          <strong className="tabular-nums">{formatAmount(summary.total, "DH")}</strong> vont être
          validées en votre nom. Chaque validation est tracée dans l&apos;historique.
        </p>
        {summary.faibles > 0 && (
          <p className="mt-2 text-simtis-warning-fg">
            Dont {plural(summary.faibles, "proposition")} à vérifier (score inférieur à {seuil}) :
            confirmez que vous les avez contrôlées.
          </p>
        )}
        {error && (
          <p role="alert" className="mt-2 text-simtis-danger-fg">
            {error}
          </p>
        )}
      </Modal>

      <Modal
        open={rejecting !== null}
        onClose={() => setRejecting(null)}
        title="Rejeter la proposition"
        footer={
          <>
            <Button variant="secondary" onClick={() => setRejecting(null)}>
              Retour
            </Button>
            <Button
              variant="danger"
              icon={X}
              disabled={busy}
              onClick={() =>
                rejecting && act(() => rejectMatch(rejecting.id, comment), "Proposition rejetée.")
              }
            >
              Rejeter
            </Button>
          </>
        }
      >
        <p className="mb-4 text-simtis-muted">
          Cette écriture ne sera plus proposée pour cette opération.
        </p>
        <Field label="Commentaire (facultatif)" htmlFor="proposition-rejet">
          <TextInput
            id="proposition-rejet"
            value={comment}
            maxLength={500}
            onChange={(event) => setComment(event.target.value)}
          />
        </Field>
      </Modal>

      {signaling && (
        <SignalDiscrepancyModal
          companyId={companyId}
          operation={signaling.operation}
          ecriture={signaling.ecriture}
          onClose={() => setSignaling(null)}
          onCreated={(ecart) => {
            setSignaling(null);
            onChanged(`Écart n° ${ecart.id} « ${ecart.type} » signalé.`);
          }}
        />
      )}
    </div>
  );
}
