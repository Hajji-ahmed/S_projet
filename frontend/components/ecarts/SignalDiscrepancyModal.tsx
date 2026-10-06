"use client";

import { TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/balances";
import { suggestedType, typeProblem } from "@/lib/discrepancies";
import { formatAmount } from "@/lib/format";
import { absolute } from "@/lib/reconciliation";
import { createDiscrepancy, listResponsables } from "@/services/discrepancies";
import {
  TYPES_ECART,
  type EcartDetail,
  type Responsable,
  type TypeEcart,
} from "@/types/discrepancy";

type Ligne = { id: number; date: string; libelle: string; montant: string };

type SignalDiscrepancyModalProps = {
  companyId: number;
  operation: Ligne | null;
  ecriture: Ligne | null;
  onClose: () => void;
  onCreated: (ecart: EcartDetail) => void;
};

/**
 * Fenêtre « Signaler un écart » : type (proposé selon les lignes sélectionnées), commentaire et
 * responsable facultatifs. Les mêmes règles que l'API indiquent les lignes manquantes avant l'envoi.
 */
export function SignalDiscrepancyModal({
  companyId,
  operation,
  ecriture,
  onClose,
  onCreated,
}: SignalDiscrepancyModalProps) {
  const [type, setType] = useState<TypeEcart>(() => suggestedType(operation, ecriture));
  const [commentaire, setCommentaire] = useState("");
  const [responsableId, setResponsableId] = useState("");
  const [responsables, setResponsables] = useState<Responsable[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listResponsables(companyId).then(
      (list) => {
        if (!cancelled) setResponsables(list);
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  // Lignes envoyées selon le type ; un doublon porte sur une seule ligne (l'opération d'abord)
  const usedOperation = type === "Écriture sans banque" ? null : operation;
  const usedEcriture =
    type === "Banque sans écriture" || (type === "Doublon potentiel" && usedOperation)
      ? null
      : ecriture;
  const problem = typeProblem(type, usedOperation, usedEcriture);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const ecart = await createDiscrepancy({
        type,
        transaction_id: usedOperation?.id ?? null,
        ecriture_id: usedEcriture?.id ?? null,
        commentaire: commentaire.trim() || null,
        responsable_id: responsableId ? Number(responsableId) : null,
      });
      onCreated(ecart);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Signaler un écart"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Annuler
          </Button>
          <Button icon={TriangleAlert} disabled={busy || problem !== null} onClick={submit}>
            Signaler l&apos;écart
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && (
          <p
            role="alert"
            className="rounded-[10px] bg-simtis-danger-bg px-3 py-2 text-simtis-danger-fg"
          >
            {error}
          </p>
        )}
        <Field label="Type d'écart" htmlFor="ecart-type" required>
          <Select
            id="ecart-type"
            value={type}
            options={TYPES_ECART.map((item) => ({ value: item, label: item }))}
            onChange={(event) => setType(event.target.value as TypeEcart)}
          />
        </Field>
        <dl className="space-y-2">
          <LineSummary title="Opération bancaire" ligne={usedOperation} />
          <LineSummary title="Écriture comptable" ligne={usedEcriture} />
        </dl>
        {problem && <p className="text-simtis-warning-fg">{problem}</p>}
        <Field label="Responsable (facultatif)" htmlFor="ecart-responsable">
          <Select
            id="ecart-responsable"
            value={responsableId}
            placeholder="Aucun"
            options={responsables.map((user) => ({ value: String(user.id), label: user.nom }))}
            onChange={(event) => setResponsableId(event.target.value)}
          />
        </Field>
        <Field label="Commentaire (facultatif)" htmlFor="ecart-commentaire">
          <TextInput
            id="ecart-commentaire"
            value={commentaire}
            maxLength={1000}
            onChange={(event) => setCommentaire(event.target.value)}
          />
        </Field>
      </div>
    </Modal>
  );
}

function LineSummary({ title, ligne }: { title: string; ligne: Ligne | null }) {
  return (
    <div className="rounded-[10px] border border-simtis-border bg-simtis-background px-3 py-2">
      <dt className="text-xs font-semibold tracking-wide text-simtis-muted uppercase">{title}</dt>
      <dd>
        {ligne ? (
          <span className="flex items-baseline justify-between gap-3">
            <span className="min-w-0 truncate">
              {formatDate(ligne.date)} · {ligne.libelle}
            </span>
            <span className="shrink-0 font-medium tabular-nums">
              {formatAmount(absolute(ligne.montant), "DH")}
            </span>
          </span>
        ) : (
          <span className="text-simtis-muted">-</span>
        )}
      </dd>
    </div>
  );
}
