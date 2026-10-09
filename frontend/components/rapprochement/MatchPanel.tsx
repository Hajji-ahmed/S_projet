"use client";

import {
  ArrowDownUp,
  Ban,
  Check,
  GitCompareArrows,
  Link2,
  ListFilter,
  MousePointerClick,
  TriangleAlert,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { SignalDiscrepancyModal } from "@/components/ecarts/SignalDiscrepancyModal";
import { ScoreBadge, ScoreDetail } from "@/components/rapprochement/Score";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Field, TextInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { ECARTS_ACTIFS } from "@/lib/features";
import { formatAmount } from "@/lib/format";
import {
  absolute,
  ecartManuel,
  rapprochable,
  sensBanque,
  sensSage,
  trierCandidats,
} from "@/lib/reconciliation";
import { formatDateTime } from "@/lib/statements";
import {
  cancelMatch,
  getMatch,
  listCandidates,
  matchManually,
  rejectMatch,
  validateMatch,
} from "@/services/reconciliation";
import type { Ecriture } from "@/types/accounting";
import type { Candidat, Candidats, Correspondance, Operation } from "@/types/reconciliation";

type MatchPanelProps = {
  companyId: number;
  operation: Operation | null;
  entry: Ecriture | null;
  canValidate: boolean;
  /** Permission `discrepancies.manage` : bouton « Signaler un écart » (P12). */
  canManageDiscrepancies: boolean;
  reloadKey: number;
  /** Après une décision : la vue recharge les volets et affiche le message. */
  onChanged: (message: string) => void;
};

function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.message : "Une erreur est survenue.";
}

/** Sens Sage d'une écriture : un débit du compte banque correspond à un crédit en banque. */
function sensSageOf(entry: Ecriture): string {
  return sensSage(entry.montant);
}

/**
 * Panneau central « Correspondance » : la proposition de l'opération sélectionnée (score et détail
 * des critères), les décisions (Valider, Rejeter, Annuler), les autres écritures candidates et le
 * rapprochement manuel avec l'écriture sélectionnée à droite. Rien n'est validé sans un clic.
 */
export function MatchPanel({
  companyId,
  operation,
  entry,
  canValidate,
  canManageDiscrepancies,
  reloadKey,
  onChanged,
}: MatchPanelProps) {
  const matchId = operation?.correspondance?.id ?? null;
  const operationId = operation?.id ?? null;
  // Le panneau est remonté (key) à chaque nouvelle opération : son état repart de zéro
  const [loadedMatch, setLoadedMatch] = useState<Correspondance | null>(null);
  const [matchFailed, setMatchFailed] = useState<number | null>(null);
  const [showCandidates, setShowCandidates] = useState(false);
  const [candidates, setCandidates] = useState<Candidats | null>(null);
  const [candidatesFailed, setCandidatesFailed] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [comment, setComment] = useState("");
  const [motif, setMotif] = useState("");
  const [manualComment, setManualComment] = useState("");
  const [signaling, setSignaling] = useState(false);

  const wantsCandidates = operationId !== null && (matchId === null || showCandidates);
  // Une correspondance chargée pour une autre valeur (rejetée entre-temps...) n'est plus montrée
  const match = matchId !== null && loadedMatch?.id === matchId ? loadedMatch : null;
  const matchState: "loading" | "error" | "ready" = match
    ? "ready"
    : matchFailed === matchId
      ? "error"
      : "loading";
  const candidatesState: "loading" | "error" | "ready" = candidatesFailed
    ? "error"
    : candidates
      ? "ready"
      : "loading";

  useEffect(() => {
    if (matchId === null) return;
    let cancelled = false;
    getMatch(matchId).then(
      (result) => {
        if (cancelled) return;
        setLoadedMatch(result);
        setMatchFailed(null);
      },
      () => {
        if (!cancelled) setMatchFailed(matchId);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [matchId, reloadKey, retryKey]);

  useEffect(() => {
    if (!wantsCandidates || operationId === null) return;
    let cancelled = false;
    listCandidates(operationId).then(
      (result) => {
        if (cancelled) return;
        setCandidates(result);
        setCandidatesFailed(false);
      },
      () => {
        if (!cancelled) setCandidatesFailed(true);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [wantsCandidates, operationId, reloadKey, retryKey]);

  function retry() {
    setMatchFailed(null);
    setCandidatesFailed(false);
    setRetryKey((key) => key + 1);
  }

  async function act(action: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setRejecting(false);
      setCancelling(false);
      setComment("");
      setMotif("");
      setManualComment("");
      setShowCandidates(false);
      onChanged(message);
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setBusy(false);
    }
  }

  function manual(ecritureId: number, commentaire?: string) {
    if (!operation) return;
    void act(
      () => matchManually(operation.id, ecritureId, commentaire),
      "Rapprochement manuel enregistré.",
    );
  }

  if (!operation && !entry) {
    return (
      <Card title="Correspondance" icon={GitCompareArrows}>
        <EmptyState
          icon={MousePointerClick}
          message="Sélectionnez une transaction bancaire pour voir la correspondance proposée."
        />
      </Card>
    );
  }

  const pending = match?.statut === "Proposée";
  const validated = match?.statut === "Validée";
  const manualEntry = operation && entry && entry.id !== match?.ecriture.id ? entry : null;
  // Écart : l'écriture sélectionnée à droite, sinon celle de la proposition en attente
  const ecartEntry = entry ?? (pending ? (match?.ecriture ?? null) : null);
  const canSignal =
    canManageDiscrepancies &&
    !validated &&
    operation?.statut !== "Écart" &&
    ecartEntry?.statut !== "Écart" &&
    ecartEntry?.statut !== "Rapprochée";

  return (
    <Card title="Correspondance" icon={GitCompareArrows}>
      <div className="space-y-4">
        {error && (
          <p
            role="alert"
            className="rounded-[10px] bg-simtis-danger-bg px-3 py-2 text-sm text-simtis-danger-fg"
          >
            {error}
          </p>
        )}

        {operation ? (
          <Side title="Transaction bancaire">
            <Amount value={operation.montant} sens={sensBanque(operation.montant).toLowerCase()} />
            <p className="text-sm">{operation.libelle}</p>
            <p className="text-xs text-simtis-muted">
              {formatDate(operation.date_operation)} · {operation.bank_code}
              {operation.reference && ` · Réf. ${operation.reference}`}
            </p>
          </Side>
        ) : (
          <p className="text-sm text-simtis-muted">
            Sélectionnez la transaction bancaire correspondant à cette écriture.
          </p>
        )}

        {ECARTS_ACTIFS && operation?.ecart_id && (
          <p className="flex items-center gap-2 rounded-[10px] bg-simtis-orange-bg px-3 py-2 text-sm text-simtis-orange-fg">
            <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden />
            <span>
              Opération en écart :{" "}
              <Link
                href={`/ecarts?ecart=${operation.ecart_id}`}
                className="font-medium underline underline-offset-2"
              >
                voir l&apos;écart n° {operation.ecart_id}
              </Link>
            </span>
          </p>
        )}

        {matchId !== null && matchState === "loading" && <LoadingState rows={3} />}
        {matchId !== null && matchState === "error" && (
          <ErrorState message="Impossible de charger la correspondance." onRetry={retry} />
        )}

        {match && matchState === "ready" && (
          <>
            <div className="flex items-center justify-center gap-3">
              <ArrowDownUp className="h-4 w-4 text-simtis-muted" aria-hidden />
              <ScoreBadge score={match.score} forte={match.forte} />
              {validated ? (
                <StatusBadge status="Rapprochée" />
              ) : (
                <span className="text-xs text-simtis-muted">Proposée</span>
              )}
            </div>
            <Side title="Écriture comptable">
              <Amount value={match.ecriture.montant} sens={sensSageOf(match.ecriture)} />
              <p className="text-sm">{match.ecriture.libelle}</p>
              <p className="text-xs text-simtis-muted">
                {formatDate(match.ecriture.date_ecriture)}
                {match.ecriture.numero_piece && ` · Pièce ${match.ecriture.numero_piece}`}
                {match.ecriture.tiers && ` · ${match.ecriture.tiers}`}
              </p>
            </Side>
            <div>
              <p className="mb-2 text-xs font-semibold tracking-wide text-simtis-muted uppercase">
                Détail du score
              </p>
              <ScoreDetail criteres={match.criteres} />
            </div>
            {match.origine === "Manuelle" && (
              <p className="text-xs text-simtis-muted">Rapprochement manuel.</p>
            )}
            {validated && match.valide_le && (
              <p className="text-xs text-simtis-muted">
                Validé par {match.valide_par ?? "-"} le {formatDateTime(match.valide_le)}.
              </p>
            )}
            {match.commentaire && <p className="text-xs">« {match.commentaire} »</p>}

            {canValidate && pending && (
              <div className="flex flex-col gap-2">
                <Button
                  icon={Check}
                  disabled={busy}
                  onClick={() => act(() => validateMatch(match.id), "Rapprochement validé.")}
                >
                  Valider le rapprochement
                </Button>
                <Button
                  variant="secondary"
                  icon={X}
                  disabled={busy}
                  onClick={() => setRejecting(true)}
                >
                  Rejeter
                </Button>
                {!showCandidates && (
                  <Button
                    variant="ghost"
                    icon={ListFilter}
                    disabled={busy}
                    onClick={() => setShowCandidates(true)}
                  >
                    Choisir une autre écriture
                  </Button>
                )}
              </div>
            )}
            {canValidate && validated && (
              <Button
                variant="secondary"
                icon={Ban}
                disabled={busy}
                onClick={() => setCancelling(true)}
              >
                Annuler le rapprochement
              </Button>
            )}
          </>
        )}

        {wantsCandidates && (
          <CandidatesList
            operation={operation}
            data={candidates}
            state={candidatesState}
            canValidate={canValidate}
            busy={busy}
            hasMatch={matchId !== null}
            onRetry={retry}
            onChoose={(ecritureId) => manual(ecritureId)}
          />
        )}

        {manualEntry && operation && (
          <ManualMatch
            operation={operation}
            entry={manualEntry}
            canValidate={canValidate && !validated}
            busy={busy}
            comment={manualComment}
            onComment={setManualComment}
            onConfirm={() => manual(manualEntry.id, manualComment)}
          />
        )}

        {canSignal && (
          <Button
            variant="ghost"
            icon={TriangleAlert}
            disabled={busy}
            onClick={() => setSignaling(true)}
          >
            Signaler un écart
          </Button>
        )}
      </div>

      {signaling && (
        <SignalDiscrepancyModal
          companyId={companyId}
          operation={
            operation && {
              id: operation.id,
              date: operation.date_operation,
              libelle: operation.libelle,
              montant: operation.montant,
            }
          }
          ecriture={
            ecartEntry && {
              id: ecartEntry.id,
              date: ecartEntry.date_ecriture,
              libelle: ecartEntry.libelle,
              montant: ecartEntry.montant,
            }
          }
          onClose={() => setSignaling(false)}
          onCreated={(ecart) => {
            setSignaling(false);
            onChanged(`Écart n° ${ecart.id} « ${ecart.type} » signalé.`);
          }}
        />
      )}

      {match && (
        <Modal
          open={rejecting}
          onClose={() => setRejecting(false)}
          title="Rejeter la proposition"
          footer={
            <>
              <Button variant="secondary" onClick={() => setRejecting(false)}>
                Retour
              </Button>
              <Button
                variant="danger"
                icon={X}
                disabled={busy}
                onClick={() => act(() => rejectMatch(match.id, comment), "Proposition rejetée.")}
              >
                Rejeter
              </Button>
            </>
          }
        >
          <p className="mb-4 text-simtis-muted">
            Cette écriture ne sera plus proposée pour cette opération.
          </p>
          <Field label="Commentaire (facultatif)" htmlFor="rejet-commentaire">
            <TextInput
              id="rejet-commentaire"
              value={comment}
              maxLength={500}
              onChange={(event) => setComment(event.target.value)}
            />
          </Field>
        </Modal>
      )}

      {match && (
        <Modal
          open={cancelling}
          onClose={() => setCancelling(false)}
          title="Annuler le rapprochement"
          footer={
            <>
              <Button variant="secondary" onClick={() => setCancelling(false)}>
                Retour
              </Button>
              <Button
                variant="danger"
                icon={Ban}
                disabled={busy || !motif.trim()}
                onClick={() =>
                  act(() => cancelMatch(match.id, motif.trim()), "Rapprochement annulé.")
                }
              >
                Annuler le rapprochement
              </Button>
            </>
          }
        >
          <p className="mb-4 text-simtis-muted">
            L&apos;opération et l&apos;écriture redeviennent « Non rapprochée ». L&apos;annulation
            reste tracée dans l&apos;historique.
          </p>
          <Field label="Motif" htmlFor="annulation-motif" required>
            <TextInput
              id="annulation-motif"
              value={motif}
              maxLength={500}
              onChange={(event) => setMotif(event.target.value)}
            />
          </Field>
        </Modal>
      )}
    </Card>
  );
}

function Side({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-1 rounded-[12px] border border-simtis-border bg-simtis-background p-3">
      <p className="text-xs font-semibold tracking-wide text-simtis-muted uppercase">{title}</p>
      {children}
    </div>
  );
}

function Amount({ value, sens }: { value: string; sens: string }) {
  return (
    <p className="text-[20px] font-semibold text-simtis-primary-dark tabular-nums">
      {formatAmount(absolute(value), "DH")}{" "}
      <span className="text-xs font-normal text-simtis-muted">{sens}</span>
    </p>
  );
}

function CandidatesList({
  operation,
  data,
  state,
  canValidate,
  busy,
  hasMatch,
  onRetry,
  onChoose,
}: {
  operation: Operation | null;
  data: Candidats | null;
  state: "loading" | "error" | "ready";
  canValidate: boolean;
  busy: boolean;
  hasMatch: boolean;
  onRetry: () => void;
  onChoose: (ecritureId: number) => void;
}) {
  // 09/10/2026 : seules les écritures utiles sont dépliées (même montant ou score au seuil)
  const { utiles, autres } =
    data && operation
      ? trierCandidats(operation.montant, data.candidats, data.seuil_proposition)
      : { utiles: [], autres: [] };

  function renderCandidat(candidat: Candidat) {
    if (!operation || !data) return null;
    const ok = rapprochable(operation.montant, candidat.ecriture.montant);
    const forte = Number(candidat.score) >= Number(data.seuil_fort);
    return (
      <li
        key={candidat.ecriture.id}
        className="space-y-1 rounded-[12px] border border-simtis-border p-3"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm font-medium tabular-nums">
              {formatAmount(absolute(candidat.ecriture.montant), "DH")}
            </p>
            <p className="truncate text-sm">{candidat.ecriture.libelle}</p>
            <p className="text-xs text-simtis-muted">
              {formatDate(candidat.ecriture.date_ecriture)}
              {candidat.ecriture.numero_piece && ` · Pièce ${candidat.ecriture.numero_piece}`}
            </p>
          </div>
          <ScoreBadge score={candidat.score} forte={forte} />
        </div>
        {candidat.rejetee && (
          <p className="text-xs text-simtis-warning-fg">Déjà rejetée pour cette opération.</p>
        )}
        {candidat.proposee_ailleurs && (
          <p className="text-xs text-simtis-warning-fg">
            Proposée pour une autre opération : la choisir rejette cette proposition.
          </p>
        )}
        {!ok && (
          <p className="text-xs text-simtis-muted">
            Montant différent : écart de{" "}
            {formatAmount(
              absolute(ecartManuel(operation.montant, candidat.ecriture.montant)),
              "DH",
            )}
            .
          </p>
        )}
        {canValidate && (
          <Button
            variant="secondary"
            icon={Link2}
            disabled={busy || !ok || candidat.ecriture.statut === "Rapprochée"}
            onClick={() => onChoose(candidat.ecriture.id)}
            className="w-full"
          >
            Rapprocher avec cette écriture
          </Button>
        )}
      </li>
    );
  }

  return (
    <div>
      <p className="mb-2 text-xs font-semibold tracking-wide text-simtis-muted uppercase">
        {hasMatch ? "Autres écritures possibles" : "Écritures possibles"}
      </p>
      {state === "loading" && <LoadingState rows={3} />}
      {state === "error" && (
        <ErrorState message="Impossible de charger les écritures possibles." onRetry={onRetry} />
      )}
      {state === "ready" && data && operation && (
        <>
          {utiles.length === 0 ? (
            <p className="text-sm text-simtis-muted">
              Aucune écriture Sage de {formatAmount(absolute(operation.montant), "DH")} à ± 10 jours
              sur ce compte. L&apos;écriture n&apos;est peut-être pas encore importée.
            </p>
          ) : (
            <ul className="space-y-2">{utiles.map(renderCandidat)}</ul>
          )}
          {autres.length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-sm font-medium text-simtis-primary">
                Voir les autres écritures proches ({autres.length})
              </summary>
              <ul className="mt-2 space-y-2">{autres.map(renderCandidat)}</ul>
            </details>
          )}
        </>
      )}
    </div>
  );
}

function ManualMatch({
  operation,
  entry,
  canValidate,
  busy,
  comment,
  onComment,
  onConfirm,
}: {
  operation: Operation;
  entry: Ecriture;
  canValidate: boolean;
  busy: boolean;
  comment: string;
  onComment: (value: string) => void;
  onConfirm: () => void;
}) {
  const ecart = ecartManuel(operation.montant, entry.montant);
  const ok = rapprochable(operation.montant, entry.montant);
  return (
    <div className="space-y-3 rounded-[12px] border border-simtis-secondary/40 bg-simtis-light/40 p-3">
      <p className="text-xs font-semibold tracking-wide text-simtis-primary-dark uppercase">
        Rapprochement manuel
      </p>
      <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-[13px]">
        <dt className="text-simtis-muted">Transaction ({sensBanque(operation.montant)})</dt>
        <dd className="text-right tabular-nums">
          {formatAmount(absolute(operation.montant), "DH")}
        </dd>
        <dt className="text-simtis-muted">Écriture ({sensSageOf(entry)})</dt>
        <dd className="text-right tabular-nums">{formatAmount(absolute(entry.montant), "DH")}</dd>
        <dt className="font-medium">Écart restant</dt>
        <dd
          className={cn(
            "text-right font-semibold tabular-nums",
            ok ? "text-simtis-success-fg" : "text-simtis-danger-fg",
          )}
        >
          {ok ? formatAmount("0", "DH") : formatAmount(absolute(ecart), "DH")}
        </dd>
      </dl>
      {!ok && (
        <p className="text-xs text-simtis-muted">
          {operation.montant.startsWith("-") === entry.montant.startsWith("-")
            ? "Même sens : un crédit en banque se rapproche d'un débit dans Sage."
            : "Les montants doivent être égaux pour un rapprochement 1→1."}
        </p>
      )}
      {entry.statut === "Rapprochée" && (
        <p className="text-xs text-simtis-muted">Cette écriture est déjà rapprochée.</p>
      )}
      {canValidate && (
        <>
          <Field label="Commentaire (facultatif)" htmlFor="manuel-commentaire">
            <TextInput
              id="manuel-commentaire"
              value={comment}
              maxLength={500}
              onChange={(event) => onComment(event.target.value)}
            />
          </Field>
          <Button
            icon={Link2}
            disabled={busy || !ok || entry.statut === "Rapprochée"}
            onClick={onConfirm}
            className="w-full"
          >
            Rapprocher manuellement
          </Button>
        </>
      )}
    </div>
  );
}
