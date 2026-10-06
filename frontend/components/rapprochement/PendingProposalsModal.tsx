"use client";

import { ArrowDownUp } from "lucide-react";

import { ScoreBadge } from "@/components/rapprochement/Score";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal } from "@/components/ui/Modal";
import { formatDate } from "@/lib/balances";
import { formatAmount } from "@/lib/format";
import { absolute } from "@/lib/reconciliation";
import type { Correspondance, Operation } from "@/types/reconciliation";

type PendingProposalsModalProps = {
  open: boolean;
  correspondances: Correspondance[];
  onClose: () => void;
  /** Clic sur une proposition : son opération est sélectionnée dans le panneau central. */
  onSelect: (operation: Operation) => void;
};

/** L'opération d'une proposition, avec sa correspondance : le panneau central l'affiche. */
export function operationOf(item: Correspondance): Operation {
  return {
    ...item.operation,
    correspondance: {
      id: item.id,
      statut: item.statut,
      origine: item.origine,
      score: item.score,
      ecriture_id: item.ecriture.id,
    },
  };
}

/** Liste des propositions en attente de la période, de la plus forte à la plus faible. */
export function PendingProposalsModal({
  open,
  correspondances,
  onClose,
  onSelect,
}: PendingProposalsModalProps) {
  const sorted = [...correspondances].sort(
    (a, b) => Number(b.score ?? 0) - Number(a.score ?? 0) || a.id - b.id,
  );
  return (
    <Modal open={open} onClose={onClose} title="Propositions en attente">
      {sorted.length === 0 ? (
        <EmptyState message="Aucune proposition en attente sur cette période." />
      ) : (
        <>
          <p className="mb-3 text-simtis-muted">
            Choisissez une proposition pour la vérifier, puis la valider ou la rejeter dans le
            panneau Correspondance.
          </p>
          <ul className="max-h-[60vh] space-y-2 overflow-y-auto pr-1">
            {sorted.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onSelect(operationOf(item))}
                  className="w-full rounded-[12px] border border-simtis-border p-3 text-left transition-colors hover:bg-simtis-light/50 focus-visible:outline-2 focus-visible:outline-simtis-secondary"
                >
                  <span className="flex items-start justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{item.operation.libelle}</span>
                      <span className="block text-xs text-simtis-muted">
                        {formatDate(item.operation.date_operation)} · {item.operation.bank_code}
                      </span>
                    </span>
                    <span className="flex shrink-0 flex-col items-end gap-1">
                      <span className="font-semibold tabular-nums">
                        {formatAmount(absolute(item.operation.montant), "DH")}
                      </span>
                      <ScoreBadge score={item.score} forte={item.forte} />
                    </span>
                  </span>
                  <span className="mt-1.5 flex items-center gap-1.5 text-xs text-simtis-muted">
                    <ArrowDownUp className="h-3.5 w-3.5 shrink-0" aria-hidden />
                    <span className="truncate">
                      {formatDate(item.ecriture.date_ecriture)} · {item.ecriture.libelle}
                      {item.ecriture.numero_piece && ` · Pièce ${item.ecriture.numero_piece}`}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </Modal>
  );
}
