"use client";

import { CircleAlert, Landmark, Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { BankCard } from "@/components/banks/BankCard";
import { BankFormModal } from "@/components/banks/BankFormModal";
import { useCompany } from "@/components/company/CompanyProvider";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { PageHeader } from "@/components/ui/PageHeader";
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api";
import { PERMISSIONS, hasAnyPermission } from "@/lib/permissions";
import { listBanks, setBankStatus } from "@/services/banks";
import type { Bank } from "@/types/bank";

type LoadState = "loading" | "error" | "ready";
// Fenêtre de formulaire : fermée, création, ou modification d'une banque
type FormState = null | { mode: "create" } | { mode: "edit"; bank: Bank };

const GRID = "grid gap-5 sm:grid-cols-2 xl:grid-cols-3";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Une erreur est survenue.";
}

export function BanksView() {
  const { user } = useAuth();
  const { toast } = useToast();
  // Le nombre de comptes de chaque carte est celui de la société active
  const companyId = useCompany().company?.id;
  const canManage = !!user && hasAnyPermission(user.permissions, [PERMISSIONS.BANKS_MANAGE]);

  const [banks, setBanks] = useState<Bank[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [form, setForm] = useState<FormState>(null);
  const [toDeactivate, setToDeactivate] = useState<Bank | null>(null);
  const [deactivateError, setDeactivateError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Incrémentée par « Réessayer » pour relancer le chargement
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (companyId === undefined) return;
    let cancelled = false;
    listBanks(companyId).then(
      (data) => {
        if (cancelled) return;
        setBanks(data);
        setLoadState("ready");
      },
      () => {
        if (!cancelled) setLoadState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [reloadKey, companyId]);

  function retry() {
    setLoadState("loading");
    setReloadKey((key) => key + 1);
  }

  function replace(saved: Bank) {
    setBanks((current) => {
      const exists = current.some((bank) => bank.id === saved.id);
      const next = exists
        ? current.map((bank) => (bank.id === saved.id ? saved : bank))
        : [...current, saved];
      return next.sort(
        (a, b) => a.ordre_affichage - b.ordre_affichage || a.code.localeCompare(b.code),
      );
    });
  }

  function handleSaved(saved: Bank, mode: "create" | "edit") {
    replace(saved);
    setForm(null);
    toast(mode === "create" ? `Banque ${saved.code} créée.` : `Banque ${saved.code} modifiée.`);
  }

  async function reactivate(bank: Bank) {
    try {
      replace(await setBankStatus(bank.id, true));
      toast(`Banque ${bank.code} réactivée.`);
    } catch (error) {
      toast(errorMessage(error), "error");
    }
  }

  async function confirmDeactivation() {
    if (!toDeactivate) return;
    setBusy(true);
    setDeactivateError(null);
    try {
      replace(await setBankStatus(toDeactivate.id, false));
      toast(`Banque ${toDeactivate.code} désactivée.`);
      setToDeactivate(null);
    } catch (error) {
      setDeactivateError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  function closeDeactivation() {
    setToDeactivate(null);
    setDeactivateError(null);
  }

  return (
    <>
      <PageHeader
        title="Banques"
        description="Gestion des banques et comptes bancaires"
        actions={
          canManage && (
            <Button icon={Plus} onClick={() => setForm({ mode: "create" })}>
              Nouvelle banque
            </Button>
          )
        }
      />

      {loadState === "loading" && (
        <div className={GRID} role="status" aria-busy="true">
          <span className="sr-only">Chargement des banques...</span>
          {Array.from({ length: 3 }, (_, index) => (
            <Skeleton key={index} className="h-[188px] rounded-[14px]" />
          ))}
        </div>
      )}

      {loadState === "error" && (
        <Card>
          <ErrorState message="Impossible de charger les banques." onRetry={retry} />
        </Card>
      )}

      {loadState === "ready" && banks.length === 0 && (
        <Card>
          <EmptyState icon={Landmark} message="Aucune banque enregistrée." />
        </Card>
      )}

      {loadState === "ready" && banks.length > 0 && (
        <div className={GRID}>
          {banks.map((bank) => (
            <BankCard
              key={bank.id}
              bank={bank}
              canManage={canManage}
              onEdit={(selected) => setForm({ mode: "edit", bank: selected })}
              onToggleStatus={(selected) =>
                selected.actif ? setToDeactivate(selected) : reactivate(selected)
              }
            />
          ))}
        </div>
      )}

      {form && (
        <BankFormModal
          bank={form.mode === "edit" ? form.bank : undefined}
          onClose={() => setForm(null)}
          onSaved={handleSaved}
        />
      )}

      {toDeactivate && (
        <Modal
          open
          title={`Désactiver la banque ${toDeactivate.code} ?`}
          onClose={closeDeactivation}
          footer={
            <>
              <Button variant="secondary" onClick={closeDeactivation} disabled={busy}>
                Annuler
              </Button>
              <Button variant="danger" onClick={confirmDeactivation} disabled={busy}>
                {busy ? "Désactivation..." : "Désactiver"}
              </Button>
            </>
          }
        >
          {deactivateError && (
            <div
              role="alert"
              className="mb-4 flex items-start gap-2 rounded-lg bg-simtis-danger-bg px-3 py-2.5 text-simtis-danger-fg"
            >
              <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>{deactivateError}</span>
            </div>
          )}
          <p className="text-simtis-text">
            {toDeactivate.nom} ne pourra plus recevoir de nouveaux comptes. Son historique est
            conservé et elle peut être réactivée à tout moment.
          </p>
        </Modal>
      )}
    </>
  );
}
