"use client";

import { CircleAlert } from "lucide-react";
import { useId, type FormEvent, type ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";

type FormModalProps = {
  open: boolean;
  title: string;
  onClose: () => void;
  onSubmit: () => void;
  submitLabel?: string;
  submitting?: boolean;
  /** Erreur globale (ex. message de l'API), affichée en haut du formulaire. */
  error?: string | null;
  children: ReactNode;
};

/** Fenêtre de formulaire : Annuler / Enregistrer, état d'envoi, erreur de l'API. */
export function FormModal({
  open,
  title,
  onClose,
  onSubmit,
  submitLabel = "Enregistrer",
  submitting = false,
  error,
  children,
}: FormModalProps) {
  const formId = useId();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!submitting) onSubmit();
  }

  return (
    <Modal
      open={open}
      title={title}
      onClose={() => {
        if (!submitting) onClose();
      }}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Annuler
          </Button>
          <Button type="submit" form={formId} disabled={submitting}>
            {submitting ? "Enregistrement..." : submitLabel}
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={handleSubmit} noValidate className="space-y-4">
        {error && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg bg-simtis-danger-bg px-3 py-2.5 text-sm text-simtis-danger-fg"
          >
            <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>{error}</span>
          </div>
        )}
        {children}
      </form>
    </Modal>
  );
}
