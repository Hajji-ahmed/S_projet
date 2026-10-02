"use client";

import { useState } from "react";

import { Field, Select, TextInput } from "@/components/ui/Field";
import { FormModal } from "@/components/ui/FormModal";
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/balances";
import { formatAmount } from "@/lib/format";
import { updateTransaction } from "@/services/statements";
import type { PointageType, Transaction } from "@/types/statement";

type TransactionEditModalProps = {
  transaction: Transaction;
  pointages: PointageType[];
  suffix: string;
  onClose: () => void;
  onSaved: (updated: Transaction) => void;
};

/**
 * Modification d'une opération importée : seulement Pointage, Lettrage / Escompte et Commentaire
 * (décision métier du 02/10/2026). Dates, libellé et montants restent ceux de la banque.
 */
export function TransactionEditModal({
  transaction,
  pointages,
  suffix,
  onClose,
  onSaved,
}: TransactionEditModalProps) {
  const { toast } = useToast();
  // Prérempli par l'identifiant (jamais par le libellé), et le type actuel reste proposé même s'il
  // est désactivé ou si la liste n'a pas pu être chargée : enregistrer un commentaire n'efface
  // jamais le Pointage par accident.
  const current = transaction.pointage_type_id;
  const [pointage, setPointage] = useState(current === null ? "" : String(current));
  const options = pointages.map((item) => ({ value: String(item.id), label: item.libelle }));
  if (current !== null && !options.some((option) => option.value === String(current))) {
    options.unshift({ value: String(current), label: transaction.pointage ?? "Type actuel" });
  }
  const [lettrage, setLettrage] = useState(transaction.lettrage_escompte ?? "");
  const [commentaire, setCommentaire] = useState(transaction.commentaire ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const updated = await updateTransaction(transaction.id, {
        pointage_type_id: pointage ? Number(pointage) : null,
        lettrage_escompte: lettrage.trim() || null,
        commentaire: commentaire.trim() || null,
      });
      toast("Opération modifiée.");
      onSaved(updated);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Une erreur est survenue.");
      setSubmitting(false);
    }
  }

  return (
    <FormModal
      open
      title={`Modifier l'opération du ${formatDate(transaction.date_operation)}`}
      onClose={onClose}
      onSubmit={submit}
      submitting={submitting}
      error={error}
    >
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-lg bg-simtis-background p-3 text-sm">
        <div className="col-span-2">
          <dt className="text-simtis-muted">Libellé</dt>
          <dd className="font-medium">{transaction.libelle}</dd>
        </div>
        <div>
          <dt className="text-simtis-muted">Débit</dt>
          <dd className="tabular-nums">
            {formatAmount(transaction.debit, suffix, { dashForZero: true })}
          </dd>
        </div>
        <div>
          <dt className="text-simtis-muted">Crédit</dt>
          <dd className="tabular-nums">
            {formatAmount(transaction.credit, suffix, { dashForZero: true })}
          </dd>
        </div>
      </dl>
      <p className="text-xs text-simtis-muted">
        Dates, libellé et montants restent ceux de la banque : seuls ces trois champs se modifient.
      </p>
      <Field label="Pointage" htmlFor="operation-pointage">
        <Select
          id="operation-pointage"
          value={pointage}
          placeholder="Aucun"
          options={options}
          onChange={(event) => setPointage(event.target.value)}
        />
      </Field>
      <Field
        label="Lettrage / Escompte"
        htmlFor="operation-lettrage"
        hint="120 caractères au plus."
      >
        <TextInput
          id="operation-lettrage"
          value={lettrage}
          maxLength={120}
          onChange={(event) => setLettrage(event.target.value)}
        />
      </Field>
      <Field label="Commentaire" htmlFor="operation-commentaire">
        <TextInput
          id="operation-commentaire"
          value={commentaire}
          maxLength={1000}
          onChange={(event) => setCommentaire(event.target.value)}
        />
      </Field>
    </FormModal>
  );
}
