"use client";

import { Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { ApiError } from "@/lib/api";

/**
 * Confirmation de la suppression d'un import (23/10/2026), relevé ou export Sage : résumé du fichier
 * et motif obligatoire. L'API vérifie tout (ligne rapprochée, dernier import du compte).
 */
export function DeleteImportModal({
  fichier,
  resume,
  onConfirm,
  onClose,
}: {
  fichier: string;
  resume: ReactNode;
  onConfirm: (motif: string) => Promise<void>;
  onClose: () => void;
}) {
  const [motif, setMotif] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const valide = motif.trim().length >= 3;

  async function confirmer() {
    setEnvoi(true);
    setErreur(null);
    try {
      await onConfirm(motif.trim());
    } catch (error) {
      setErreur(error instanceof ApiError ? error.message : "Suppression impossible.");
      setEnvoi(false);
    }
  }

  return (
    <Modal
      open
      title="Supprimer cet import ?"
      onClose={() => !envoi && onClose()}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={envoi}>
            Annuler
          </Button>
          <Button variant="danger" icon={Trash2} onClick={confirmer} disabled={envoi || !valide}>
            {envoi ? "Suppression..." : "Supprimer l'import"}
          </Button>
        </>
      }
    >
      <p className="font-medium text-simtis-text">{fichier}</p>
      <div className="mt-1 text-sm text-simtis-muted">{resume}</div>
      <p className="mt-3 text-sm text-simtis-muted">
        Toutes les lignes de ce fichier seront supprimées. Le fichier reste au journal avec le
        statut « Annulé » et pourra être importé de nouveau. La suppression est tracée dans
        l&apos;Historique.
      </p>
      <div className="mt-4">
        <Field label="Motif" htmlFor="motif-suppression" required error={erreur ?? undefined}>
          <TextInput
            id="motif-suppression"
            value={motif}
            maxLength={500}
            placeholder="Ex. fichier erroné, mauvaise période"
            onChange={(event) => setMotif(event.target.value)}
            autoFocus
          />
        </Field>
      </div>
    </Modal>
  );
}
