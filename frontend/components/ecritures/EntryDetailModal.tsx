"use client";

import { useEffect, useState, type ReactNode } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { formatDate } from "@/lib/balances";
import { formatAmount } from "@/lib/format";
import { formatDateTime } from "@/lib/statements";
import { getEntry } from "@/services/accounting";
import type { EcritureDetail } from "@/types/accounting";
import type { Status } from "@/types/status";

type EntryDetailModalProps = {
  entryId: number;
  /** Date et libellé de la ligne cliquée : titre affiché avant même le chargement. */
  date: string;
  logos: Map<string, string | null>;
  onClose: () => void;
};

/** Détail d'une écriture importée, en lecture seule : Sage reste la référence. */
export function EntryDetailModal({ entryId, date, logos, onClose }: EntryDetailModalProps) {
  const [entry, setEntry] = useState<EcritureDetail | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getEntry(entryId).then(
      (result) => {
        if (!cancelled) setEntry(result);
      },
      () => {
        if (!cancelled) setFailed(true);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [entryId]);

  const items: [string, ReactNode][] = entry
    ? [
        ["Date", formatDate(entry.date_ecriture)],
        ["Journal", entry.journal ?? "-"],
        ["Compte", entry.compte ?? "-"],
        [
          "Compte bancaire",
          entry.bank_code ? (
            <BankLabel code={entry.bank_code} logo={logos.get(entry.bank_code)} />
          ) : (
            "-"
          ),
        ],
        ["N° pièce", entry.numero_piece ?? "-"],
        ["Référence", entry.reference ?? "-"],
        ["Libellé", entry.libelle],
        ["Débit", formatAmount(entry.debit, "DH", { dashForZero: true })],
        ["Crédit", formatAmount(entry.credit, "DH", { dashForZero: true })],
        ["Échéance", formatDate(entry.echeance)],
        ["Tiers", entry.tiers ?? "-"],
        ["Statut", <StatusBadge key="statut" status={entry.statut as Status} />],
        ["Fichier d'origine", entry.fichier_nom ?? "-"],
        ["Importée le", entry.importe_le ? formatDateTime(entry.importe_le) : "-"],
        ["Par", entry.importe_par ?? "-"],
      ]
    : [];

  return (
    <Modal
      open
      onClose={onClose}
      title={`Écriture du ${formatDate(date)}`}
      footer={
        <Button variant="secondary" onClick={onClose}>
          Fermer
        </Button>
      }
    >
      {failed && <ErrorState message="Impossible de charger cette écriture." />}
      {!failed && !entry && <LoadingState rows={4} />}
      {entry && (
        <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          {items.map(([label, value]) => (
            <div key={label}>
              <dt className="text-simtis-muted">{label}</dt>
              <dd className="font-medium break-words text-simtis-text">{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </Modal>
  );
}
