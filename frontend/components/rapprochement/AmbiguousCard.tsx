"use client";

import { Ban, ExternalLink, Link2, Shuffle, TriangleAlert } from "lucide-react";

import { BankLabel } from "@/components/banks/BankLabel";
import { ScoreBadge } from "@/components/rapprochement/Score";
import { Button } from "@/components/ui/Button";
import { formatDate } from "@/lib/balances";
import { formatAmount } from "@/lib/format";
import {
  montantEcriture,
  unite,
  uniteEcriture,
  absolute,
  rapprochable,
  sensBanque,
  sensSage,
} from "@/lib/reconciliation";
import type { Ambigue, Candidat } from "@/types/reconciliation";

type AmbiguousCardProps = {
  item: Ambigue;
  logo: string | null | undefined;
  seuilFort: string;
  canValidate: boolean;
  canSignal: boolean;
  busy: boolean;
  /** Rapprochement manuel avec l'écriture choisie (validé d'emblée, tracé). */
  onChoose: (candidat: Candidat) => void;
  onSignal: () => void;
  onOpen: () => void;
  /** Aucune écriture ne correspond : toutes les candidates sont écartées (15/10/2026). */
  onAucune?: () => void;
  /** Sélection pour « Aucune correspondance » en lot (15/10/2026). */
  selection?: { checked: boolean; onToggle: () => void };
};

/**
 * Opération ambiguë : le moteur a trouvé plusieurs écritures aussi proches et n'en a proposé
 * aucune. L'utilisateur choisit la bonne parmi les candidates (même montant exigé).
 */
export function AmbiguousCard({
  item,
  logo,
  seuilFort,
  canValidate,
  canSignal,
  busy,
  onChoose,
  onSignal,
  onOpen,
  onAucune,
  selection,
}: AmbiguousCardProps) {
  const { operation, candidats } = item;
  return (
    <article
      aria-label={`Opération ambiguë : ${operation.libelle}`}
      className="rounded-card border border-l-4 border-simtis-border border-l-simtis-warning bg-simtis-card p-4 shadow-simtis"
    >
      {selection && (
        <label className="mb-3 flex w-fit cursor-pointer items-center gap-2 text-xs font-medium text-simtis-muted">
          <input
            type="checkbox"
            checked={selection.checked}
            disabled={busy}
            onChange={selection.onToggle}
            className="h-4 w-4 accent-simtis-primary"
          />
          Sélectionner pour « Aucune correspondance »
        </label>
      )}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-simtis-warning-fg uppercase">
            <Shuffle className="h-3.5 w-3.5" aria-hidden />
            Ambiguë : {candidats.length} écritures aussi proches
          </p>
          <p className="text-[22px] leading-tight font-bold text-simtis-primary-dark tabular-nums">
            {formatAmount(absolute(operation.montant), unite(operation.devise))}{" "}
            <span className="text-xs font-normal text-simtis-muted lowercase">
              {sensBanque(operation.montant)}
            </span>
          </p>
          <p className="font-medium">{operation.libelle}</p>
          <p className="flex flex-wrap items-center gap-x-2 text-xs text-simtis-muted">
            <span>{formatDate(operation.date_operation)}</span>
            <BankLabel code={operation.bank_code} logo={logo} />
            {operation.reference && <span>Réf. {operation.reference}</span>}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" icon={ExternalLink} disabled={busy} onClick={onOpen}>
            Ouvrir dans le rapprochement
          </Button>
          {canValidate && onAucune && (
            <Button variant="secondary" icon={Ban} disabled={busy} onClick={onAucune}>
              Aucune écriture ne correspond
            </Button>
          )}
          {canSignal && (
            <Button variant="secondary" icon={TriangleAlert} disabled={busy} onClick={onSignal}>
              Signaler un écart
            </Button>
          )}
        </div>
      </div>

      <p className="mt-3 mb-2 text-xs font-semibold tracking-wide text-simtis-muted uppercase">
        Choisissez l&apos;écriture qui correspond
      </p>
      {candidats.length === 0 ? (
        <p className="text-sm text-simtis-muted">
          Plus aucune écriture candidate : ouvrez l&apos;opération dans le rapprochement.
        </p>
      ) : (
        <ul className="space-y-2">
          {candidats.map((candidat) => {
            const ok = rapprochable(operation.montant, montantEcriture(candidat.ecriture));
            return (
              <li
                key={candidat.ecriture.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-[12px] border border-simtis-border bg-simtis-background p-3 text-sm"
              >
                <div className="min-w-0 space-y-0.5">
                  <p className="font-semibold tabular-nums">
                    {formatAmount(
                      absolute(montantEcriture(candidat.ecriture)),
                      uniteEcriture(candidat.ecriture),
                    )}{" "}
                    <span className="text-xs font-normal text-simtis-muted">
                      {sensSage(candidat.ecriture.montant)}
                    </span>
                  </p>
                  <p>{candidat.ecriture.libelle}</p>
                  <p className="text-xs text-simtis-muted">
                    {formatDate(candidat.ecriture.date_ecriture)}
                    {candidat.ecriture.numero_piece && ` · Pièce ${candidat.ecriture.numero_piece}`}
                    {candidat.ecriture.tiers && ` · ${candidat.ecriture.tiers}`}
                  </p>
                  {candidat.proposee_ailleurs && (
                    <p className="text-xs text-simtis-warning-fg">
                      Proposée pour une autre opération : la choisir rejette cette proposition.
                    </p>
                  )}
                  {!ok && (
                    <p className="text-xs text-simtis-muted">
                      Montant différent : rapprochement impossible.
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <ScoreBadge
                    score={candidat.score}
                    forte={Number(candidat.score) >= Number(seuilFort)}
                  />
                  {canValidate && (
                    <Button icon={Link2} disabled={busy || !ok} onClick={() => onChoose(candidat)}>
                      Rapprocher
                    </Button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </article>
  );
}
