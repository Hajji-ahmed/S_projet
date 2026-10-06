"use client";

import { CircleCheck, History, Save, TriangleAlert, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api";
import { currencySuffix, formatDate } from "@/lib/balances";
import { changedFields, eventLabel, nextStatuses } from "@/lib/discrepancies";
import { formatAmount } from "@/lib/format";
import { absolute } from "@/lib/reconciliation";
import { formatDateTime } from "@/lib/statements";
import { closeDiscrepancy, getDiscrepancy, updateDiscrepancy } from "@/services/discrepancies";
import type { EcartDetail, Responsable } from "@/types/discrepancy";

type DiscrepancyPanelProps = {
  ecartId: number;
  canManage: boolean;
  responsables: Responsable[];
  logos: Map<string, string | null>;
  onClose: () => void;
  /** Après une modification : la liste et les compteurs sont rechargés. */
  onChanged: (message: string) => void;
};

function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.message : "Une erreur est survenue.";
}

/**
 * Panneau latéral d'un écart : lignes concernées, montant et différence, responsable, statut,
 * commentaire, historique complet ; actions de traitement (avancer le statut, assigner, commenter,
 * clôturer avec un commentaire obligatoire). Remonté (key) pour chaque écart.
 */
export function DiscrepancyPanel({
  ecartId,
  canManage,
  responsables,
  logos,
  onClose,
  onChanged,
}: DiscrepancyPanelProps) {
  const [ecart, setEcart] = useState<EcartDetail | null>(null);
  const [failed, setFailed] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [commentaire, setCommentaire] = useState<string | null>(null);
  const [closing, setClosing] = useState(false);
  const [closingComment, setClosingComment] = useState("");

  useEffect(() => {
    let cancelled = false;
    getDiscrepancy(ecartId).then(
      (result) => {
        if (cancelled) return;
        setEcart(result);
        setFailed(false);
      },
      () => {
        if (!cancelled) setFailed(true);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [ecartId, retryKey]);

  async function act(action: () => Promise<EcartDetail>, message: string) {
    setBusy(true);
    setError(null);
    try {
      setEcart(await action());
      setCommentaire(null);
      setClosing(false);
      setClosingComment("");
      onChanged(message);
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setBusy(false);
    }
  }

  const closeButton = (
    <button
      type="button"
      onClick={onClose}
      aria-label="Fermer le détail de l'écart"
      className="rounded-lg p-1 text-simtis-muted transition-colors hover:bg-simtis-light hover:text-simtis-primary"
    >
      <X className="h-5 w-5" aria-hidden />
    </button>
  );

  if (failed) {
    return (
      <Card title="Écart" icon={TriangleAlert}>
        <ErrorState
          message="Impossible de charger l'écart."
          onRetry={() => {
            setFailed(false);
            setRetryKey((key) => key + 1);
          }}
        />
      </Card>
    );
  }
  if (!ecart) {
    return (
      <Card title="Écart" icon={TriangleAlert}>
        <LoadingState rows={4} />
      </Card>
    );
  }

  const open = ecart.statut !== "Clôturé";
  const editable = canManage && open;
  const devise = currencySuffix(ecart.devise ?? "MAD");
  const draft = commentaire ?? ecart.commentaire ?? "";

  return (
    <section
      aria-label={`Écart n° ${ecart.id}`}
      className="rounded-[14px] border border-simtis-border bg-simtis-card p-5 shadow-simtis"
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs text-simtis-muted">Écart n° {ecart.id}</p>
          <h2 className="text-[16px] font-semibold text-simtis-text">{ecart.type}</h2>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={ecart.statut} />
          {closeButton}
        </div>
      </div>

      <div className="space-y-4 text-sm">
        {error && (
          <p
            role="alert"
            className="rounded-[10px] bg-simtis-danger-bg px-3 py-2 text-simtis-danger-fg"
          >
            {error}
          </p>
        )}

        <dl className="grid grid-cols-2 gap-3">
          <Info label="Montant">
            <span className="font-semibold tabular-nums">
              {formatAmount(ecart.montant, devise)}
            </span>
          </Info>
          <Info label="Différence">
            <span className="font-semibold tabular-nums">
              {ecart.difference === null ? "-" : formatAmount(ecart.difference, devise)}
            </span>
          </Info>
          <Info label="Date">{formatDate(ecart.date_ecart)}</Info>
          <Info label="Banque">
            {ecart.bank_code ? (
              <BankLabel code={ecart.bank_code} logo={logos.get(ecart.bank_code)} />
            ) : (
              "-"
            )}
          </Info>
        </dl>

        <Block title="Transaction bancaire">
          {ecart.operation ? (
            <>
              <p className="font-medium tabular-nums">
                {formatAmount(absolute(ecart.operation.montant), devise)}{" "}
                <span className="text-xs font-normal text-simtis-muted">
                  {ecart.operation.montant.startsWith("-") ? "débit" : "crédit"}
                </span>
              </p>
              <p>{ecart.operation.libelle}</p>
              <p className="text-xs text-simtis-muted">
                {formatDate(ecart.operation.date_operation)}
                {ecart.operation.reference && ` · Réf. ${ecart.operation.reference}`}
              </p>
            </>
          ) : (
            <p className="text-simtis-muted">Aucune</p>
          )}
        </Block>
        <Block title="Écriture comptable">
          {ecart.ecriture ? (
            <>
              <p className="font-medium tabular-nums">
                {formatAmount(absolute(ecart.ecriture.montant), devise)}{" "}
                <span className="text-xs font-normal text-simtis-muted">
                  {ecart.ecriture.montant.startsWith("-") ? "crédit Sage" : "débit Sage"}
                </span>
              </p>
              <p>{ecart.ecriture.libelle}</p>
              <p className="text-xs text-simtis-muted">
                {formatDate(ecart.ecriture.date_ecriture)}
                {ecart.ecriture.numero_piece && ` · Pièce ${ecart.ecriture.numero_piece}`}
                {ecart.ecriture.tiers && ` · ${ecart.ecriture.tiers}`}
              </p>
            </>
          ) : (
            <p className="text-simtis-muted">Aucune</p>
          )}
        </Block>

        {editable ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Responsable" htmlFor="ecart-panel-responsable">
                <Select
                  id="ecart-panel-responsable"
                  value={ecart.responsable_id === null ? "" : String(ecart.responsable_id)}
                  placeholder="Aucun"
                  disabled={busy}
                  options={responsables.map((user) => ({
                    value: String(user.id),
                    label: user.nom,
                  }))}
                  onChange={(event) =>
                    act(
                      () =>
                        updateDiscrepancy(ecart.id, {
                          responsable_id: event.target.value ? Number(event.target.value) : null,
                        }),
                      "Responsable enregistré.",
                    )
                  }
                />
              </Field>
              <div>
                <p className="mb-1.5 text-sm font-medium text-simtis-text">Statut</p>
                <div className="flex flex-wrap gap-2">
                  {nextStatuses(ecart.statut).map((statut) => (
                    <Button
                      key={statut}
                      variant="secondary"
                      disabled={busy}
                      onClick={() =>
                        act(
                          () => updateDiscrepancy(ecart.id, { statut: statut as "En cours" }),
                          `Écart passé « ${statut} ».`,
                        )
                      }
                    >
                      Passer « {statut} »
                    </Button>
                  ))}
                </div>
              </div>
            </div>
            <form
              className="space-y-2"
              onSubmit={(event) => {
                event.preventDefault();
                void act(
                  () => updateDiscrepancy(ecart.id, { commentaire: draft.trim() || null }),
                  "Commentaire enregistré.",
                );
              }}
            >
              <Field label="Commentaire" htmlFor="ecart-panel-commentaire">
                <TextInput
                  id="ecart-panel-commentaire"
                  value={draft}
                  maxLength={1000}
                  onChange={(event) => setCommentaire(event.target.value)}
                />
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="submit"
                  variant="secondary"
                  icon={Save}
                  disabled={busy || commentaire === null}
                >
                  Enregistrer le commentaire
                </Button>
                <Button
                  icon={CircleCheck}
                  disabled={busy}
                  onClick={() => {
                    setClosingComment(draft);
                    setClosing(true);
                  }}
                >
                  Clôturer l&apos;écart
                </Button>
              </div>
            </form>
          </>
        ) : (
          <dl className="grid grid-cols-2 gap-3">
            <Info label="Responsable">{ecart.responsable ?? "-"}</Info>
            <Info label="Statut">{ecart.statut}</Info>
            <div className="col-span-2">
              <Info label="Commentaire">{ecart.commentaire ?? "-"}</Info>
            </div>
            {ecart.cloture_le && (
              <div className="col-span-2">
                <Info label="Clôture">
                  Le {formatDateTime(ecart.cloture_le)} par {ecart.cloture_par ?? "-"}
                </Info>
              </div>
            )}
          </dl>
        )}

        <div>
          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-simtis-muted uppercase">
            <History className="h-3.5 w-3.5" aria-hidden />
            Historique
          </p>
          <ol className="space-y-2 border-l border-simtis-border pl-3">
            {ecart.historique.map((event, index) => {
              const fields = changedFields(event.avant, event.apres);
              return (
                <li key={index} className="text-[13px]">
                  <p className="font-medium">{eventLabel(event.action, event.apres)}</p>
                  <p className="text-xs text-simtis-muted">
                    {formatDateTime(event.le)} · {event.auteur ?? "Système"}
                    {fields.length > 0 && ` · ${fields.join(", ")}`}
                  </p>
                </li>
              );
            })}
          </ol>
        </div>
      </div>

      <Modal
        open={closing}
        onClose={() => setClosing(false)}
        title="Clôturer l'écart"
        footer={
          <>
            <Button variant="secondary" onClick={() => setClosing(false)}>
              Retour
            </Button>
            <Button
              icon={CircleCheck}
              disabled={busy || !closingComment.trim()}
              onClick={() =>
                act(() => closeDiscrepancy(ecart.id, closingComment.trim()), "Écart clôturé.")
              }
            >
              Clôturer
            </Button>
          </>
        }
      >
        <p className="mb-4 text-simtis-muted">
          Indiquez comment l&apos;écart a été traité. Ses lignes redeviennent « Non rapprochée » et
          peuvent de nouveau être rapprochées. Un écart clôturé ne se modifie plus.
        </p>
        <Field label="Commentaire de clôture" htmlFor="ecart-cloture" required>
          <TextInput
            id="ecart-cloture"
            value={closingComment}
            maxLength={1000}
            onChange={(event) => setClosingComment(event.target.value)}
          />
        </Field>
      </Modal>
    </section>
  );
}

function Info({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-simtis-muted">{label}</dt>
      <dd className="mt-0.5">{children}</dd>
    </div>
  );
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-0.5 rounded-[12px] border border-simtis-border bg-simtis-background p-3">
      <p className="text-xs font-semibold tracking-wide text-simtis-muted uppercase">{title}</p>
      {children}
    </div>
  );
}
