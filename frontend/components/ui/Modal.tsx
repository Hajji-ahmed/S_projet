"use client";

import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

type ModalProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Boutons d'action alignés à droite en bas (secondaire d'abord, puis primaire). */
  footer?: ReactNode;
};

/** Fenêtre modale basée sur `<dialog>` : focus piégé et fermeture par Échap gérés par le navigateur. */
export function Modal({ open, onClose, title, children, footer }: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      // Un clic sur le fond (le <dialog> lui-même, pas son contenu) ferme la fenêtre
      onClick={(event) => {
        if (event.target === dialogRef.current) onClose();
      }}
      aria-labelledby="modal-title"
      className="m-auto w-[calc(100%-2rem)] max-w-lg rounded-[14px] border border-simtis-border bg-simtis-card p-0 text-simtis-text shadow-simtis backdrop:bg-simtis-text/30"
    >
      <div className="p-6">
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 id="modal-title" className="text-[17px] font-semibold">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fermer"
            className="rounded-lg p-1 text-simtis-muted transition-colors hover:bg-simtis-light hover:text-simtis-primary"
          >
            <X className="h-5 w-5" aria-hidden />
          </button>
        </div>
        <div className="text-sm">{children}</div>
        {footer && <div className="mt-6 flex justify-end gap-3">{footer}</div>}
      </div>
    </dialog>
  );
}
