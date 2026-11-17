"use client";

import { CircleAlert, Pencil, Plus, Power, PowerOff } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api";
import { listAllCompanies, updateCompany } from "@/services/referentiel";
import type { CompanyAdmin } from "@/types/company";

type SocietesModalProps = {
  onClose: () => void;
  onAdd: () => void;
  onEdit: (societe: CompanyAdmin) => void;
  /** Après une (dés)activation : le sélecteur relit sa liste. */
  onChanged: () => void;
};

/** « Gérer les sociétés » : toutes les sociétés, y compris désactivées (17/11/2026). */
export function SocietesModal({ onClose, onAdd, onEdit, onChanged }: SocietesModalProps) {
  const [societes, setSocietes] = useState<CompanyAdmin[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const fetchSocietes = useCallback(
    (isCancelled: () => boolean = () => false) =>
      listAllCompanies().then(
        (list) => {
          if (!isCancelled()) setSocietes(list);
        },
        () => {
          if (!isCancelled()) setLoadError(true);
        },
      ),
    [],
  );

  useEffect(() => {
    let cancelled = false;
    void fetchSocietes(() => cancelled);
    return () => {
      cancelled = true;
    };
  }, [fetchSocietes]);

  function retry() {
    setLoadError(false);
    void fetchSocietes();
  }

  async function toggle(societe: CompanyAdmin) {
    setActionError(null);
    setBusyId(societe.id);
    try {
      const saved = await updateCompany(societe.id, { actif: !societe.actif });
      setSocietes((list) => list?.map((item) => (item.id === saved.id ? saved : item)) ?? null);
      onChanged();
    } catch (error) {
      setActionError(
        error instanceof ApiError ? error.message : "Modification impossible. Réessayez.",
      );
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Modal
      open
      title="Sociétés"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Fermer
          </Button>
          <Button icon={Plus} onClick={onAdd}>
            Ajouter une société
          </Button>
        </>
      }
    >
      {actionError && (
        <div
          role="alert"
          className="mb-3 flex items-start gap-2 rounded-[10px] bg-simtis-danger-bg px-3 py-2.5 text-sm text-simtis-danger-fg"
        >
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>{actionError}</span>
        </div>
      )}
      {loadError ? (
        <ErrorState message="Impossible de charger les sociétés." onRetry={retry} />
      ) : !societes ? (
        <LoadingState rows={2} />
      ) : (
        <ul className="divide-y divide-simtis-border rounded-[12px] border border-simtis-border">
          {societes.map((societe) => (
            <li key={societe.id} className="flex items-center gap-3 px-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-simtis-text">{societe.nom}</p>
                <p className="font-mono text-xs text-simtis-muted">{societe.code}</p>
              </div>
              <StatusBadge status={societe.actif ? "Actif" : "Inactif"} />
              <button
                type="button"
                onClick={() => onEdit(societe)}
                aria-label={`Renommer ${societe.nom}`}
                title="Renommer"
                className="rounded-[10px] p-1.5 text-simtis-muted transition-colors hover:bg-simtis-surface hover:text-simtis-primary"
              >
                <Pencil className="h-4 w-4" aria-hidden />
              </button>
              <button
                type="button"
                onClick={() => toggle(societe)}
                disabled={busyId !== null}
                aria-label={`${societe.actif ? "Désactiver" : "Réactiver"} ${societe.nom}`}
                title={societe.actif ? "Désactiver" : "Réactiver"}
                className="rounded-[10px] p-1.5 text-simtis-muted transition-colors hover:bg-simtis-surface hover:text-simtis-primary disabled:opacity-50"
              >
                {societe.actif ? (
                  <PowerOff className="h-4 w-4" aria-hidden />
                ) : (
                  <Power className="h-4 w-4" aria-hidden />
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-simtis-muted">
        Une société désactivée disparaît du sélecteur ; ses données sont conservées.
      </p>
    </Modal>
  );
}
