"use client";

import { CheckCheck, Play, Scale } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { BankLabel } from "@/components/banks/BankLabel";
import { useCompany } from "@/components/company/CompanyProvider";
import { AccountButton } from "@/components/ecritures/EntriesCard";
import { EntriesPane } from "@/components/rapprochement/EntriesPane";
import { MatchPanel } from "@/components/rapprochement/MatchPanel";
import { TransactionsPane } from "@/components/rapprochement/TransactionsPane";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DateInput, Field } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { PageHeader } from "@/components/ui/PageHeader";
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api";
import { businessToday } from "@/lib/balances";
import {
  formatScore,
  defaultPeriod,
  fortes,
  type ReconciliationFilter,
} from "@/lib/reconciliation";
import { PERMISSIONS, hasAnyPermission } from "@/lib/permissions";
import { listAccounts } from "@/services/accounts";
import { listProposals, runReconciliation, validateMatches } from "@/services/reconciliation";
import type { Account } from "@/types/account";
import type { Ecriture, StatutRapprochement } from "@/types/accounting";
import type { Correspondances, Operation, OperationsPage } from "@/types/reconciliation";

/**
 * Page Rapprochement (P11) : le moteur propose des correspondances 1→1 entre les opérations
 * bancaires et les écritures Sage de la société active ; un utilisateur autorisé valide, rejette ou
 * rapproche à la main. Rien n'est validé automatiquement.
 */
export function RapprochementView() {
  const { company } = useCompany();
  // Changer de société repart d'une page vierge : rien ne se mélange entre deux sociétés
  return company ? <Rapprochement key={company.id} companyId={company.id} /> : null;
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n > 1 ? "s" : ""}`;
}

function Rapprochement({ companyId }: { companyId: number }) {
  const { user } = useAuth();
  const { toast } = useToast();
  const canValidate =
    !!user && hasAnyPermission(user.permissions, [PERMISSIONS.RECONCILIATION_VALIDATE]);

  const [filter, setFilter] = useState<ReconciliationFilter>(() => defaultPeriod(businessToday()));
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [reloadKey, setReloadKey] = useState(0);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [entry, setEntry] = useState<Ecriture | null>(null);
  const [parStatut, setParStatut] = useState<Record<StatutRapprochement, number> | null>(null);
  const [pending, setPending] = useState<Correspondances | null>(null);
  const [running, setRunning] = useState(false);
  const [confirmBatch, setConfirmBatch] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);

  const periodError =
    filter.from && filter.to && filter.from > filter.to
      ? "La date de début doit précéder la date de fin."
      : !filter.from || !filter.to
        ? "Choisissez une période."
        : null;

  useEffect(() => {
    let cancelled = false;
    listAccounts(companyId, { actif: true }).then(
      (list) => {
        if (!cancelled) setAccounts(list.filter((account) => account.journal_sage));
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  useEffect(() => {
    if (periodError) return;
    let cancelled = false;
    listProposals(companyId, filter).then(
      (result) => {
        if (!cancelled) setPending(result);
      },
      () => {
        if (!cancelled) setPending(null);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [companyId, filter, reloadKey, periodError]);

  // Les volets rechargés : la sélection suit les nouvelles valeurs (statut, correspondance)
  const handleOperations = useCallback((page: OperationsPage) => {
    setParStatut(page.par_statut);
    setOperation((current) =>
      current ? (page.operations.find((row) => row.id === current.id) ?? current) : current,
    );
  }, []);
  const handleEntries = useCallback((rows: Ecriture[]) => {
    setEntry((current) =>
      current ? (rows.find((row) => row.id === current.id) ?? current) : current,
    );
  }, []);

  function changeFilter(next: Partial<ReconciliationFilter>) {
    setOperation(null);
    setEntry(null);
    setFilter((current) => ({ ...current, ...next }));
  }

  function reload(message: string) {
    toast(message);
    setReloadKey((key) => key + 1);
  }

  async function run() {
    setRunning(true);
    try {
      const result = await runReconciliation(companyId, filter);
      const parts = [
        `${plural(result.nb_propositions, "proposition")}, dont ${plural(result.nb_fortes, "forte")}`,
      ];
      if (result.nb_operations_ambigues > 0) {
        parts.push(`${plural(result.nb_operations_ambigues, "opération")} ambiguë(s) à vérifier`);
      }
      reload(`Rapprochement lancé : ${parts.join(" ; ")}.`);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Le rapprochement a échoué.", "error");
    } finally {
      setRunning(false);
    }
  }

  const strongIds = pending ? fortes(pending.correspondances) : [];

  async function validateStrong() {
    setBatchBusy(true);
    try {
      const result = await validateMatches(strongIds);
      setConfirmBatch(false);
      reload(`${plural(result.nb_validees, "rapprochement")} validé(s).`);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "La validation a échoué.", "error");
    } finally {
      setBatchBusy(false);
    }
  }

  const filterKey = `${filter.bankAccountId ?? "tous"}|${filter.from}|${filter.to}`;

  return (
    <>
      <PageHeader
        title="Rapprochement"
        description="Rapprochement des transactions bancaires et des écritures comptables"
        actions={
          canValidate && (
            <Button icon={Play} disabled={running || !!periodError} onClick={run}>
              {running ? "Rapprochement en cours…" : "Lancer le rapprochement"}
            </Button>
          )
        }
      />

      <Card>
        <div className="space-y-4">
          <div
            className="flex gap-2 overflow-x-auto pb-1"
            role="group"
            aria-label="Compte bancaire"
          >
            <AccountButton
              active={filter.bankAccountId === undefined}
              onClick={() => changeFilter({ bankAccountId: undefined })}
            >
              Tous les comptes
            </AccountButton>
            {accounts.map((account) => (
              <AccountButton
                key={account.id}
                active={filter.bankAccountId === account.id}
                onClick={() => changeFilter({ bankAccountId: account.id })}
              >
                <BankLabel code={account.bank_code} logo={account.bank_logo}>
                  {account.bank_code} · {account.journal_sage}
                </BankLabel>
              </AccountButton>
            ))}
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <div className="w-full max-w-[170px]">
              <Field label="Du" htmlFor="rapprochement-du">
                <DateInput
                  id="rapprochement-du"
                  value={filter.from}
                  onChange={(event) => changeFilter({ from: event.target.value })}
                />
              </Field>
            </div>
            <div className="w-full max-w-[170px]">
              <Field label="Au" htmlFor="rapprochement-au">
                <DateInput
                  id="rapprochement-au"
                  value={filter.to}
                  onChange={(event) => changeFilter({ to: event.target.value })}
                />
              </Field>
            </div>
            {periodError && (
              <p role="alert" className="pb-2 text-sm text-simtis-danger-fg">
                {periodError}
              </p>
            )}
          </div>

          {!periodError && (
            <div className="flex flex-wrap items-center justify-between gap-4 border-t border-simtis-border pt-4">
              <dl
                className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm sm:grid-cols-4"
                aria-label="Résumé du rapprochement"
              >
                <Stat label="Rapprochées" value={parStatut?.["Rapprochée"]} />
                <Stat label="À vérifier" value={parStatut?.["À vérifier"]} />
                <Stat label="Non rapprochées" value={parStatut?.["Non rapprochée"]} />
                <Stat label="Propositions en attente" value={pending?.correspondances.length} />
              </dl>
              {canValidate && strongIds.length > 0 && (
                <Button variant="secondary" icon={CheckCheck} onClick={() => setConfirmBatch(true)}>
                  Valider les fortes correspondances ({strongIds.length})
                </Button>
              )}
            </div>
          )}
        </div>
      </Card>

      {!periodError && (
        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(300px,360px)_minmax(0,1fr)]">
          <TransactionsPane
            key={`tx-${filterKey}`}
            companyId={companyId}
            filter={filter}
            reloadKey={reloadKey}
            selectedId={operation?.id ?? null}
            onSelect={setOperation}
            onLoaded={handleOperations}
          />
          <div className="xl:sticky xl:top-4">
            <MatchPanel
              key={operation?.id ?? "aucune"}
              operation={operation}
              entry={entry}
              canValidate={canValidate}
              reloadKey={reloadKey}
              onChanged={reload}
            />
          </div>
          <EntriesPane
            key={`ec-${filterKey}`}
            companyId={companyId}
            filter={filter}
            reloadKey={reloadKey}
            selectedId={entry?.id ?? null}
            onSelect={setEntry}
            onLoaded={handleEntries}
          />
        </div>
      )}

      <Modal
        open={confirmBatch}
        onClose={() => setConfirmBatch(false)}
        title="Valider les fortes correspondances"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmBatch(false)}>
              Retour
            </Button>
            <Button icon={CheckCheck} disabled={batchBusy} onClick={validateStrong}>
              Valider {plural(strongIds.length, "rapprochement")}
            </Button>
          </>
        }
      >
        <p>
          {plural(strongIds.length, "correspondance")} de la période ont un score d&apos;au moins{" "}
          {formatScore(pending?.seuil_fort ?? null)}. Chacune sera validée en votre nom et tracée
          dans l&apos;historique.
        </p>
        <p className="mt-2 flex items-center gap-2 text-simtis-muted">
          <Scale className="h-4 w-4" aria-hidden />
          Les propositions plus faibles restent à vérifier une par une.
        </p>
      </Modal>
    </>
  );
}

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div>
      <dt className="text-simtis-muted">{label}</dt>
      <dd className="text-[17px] font-semibold text-simtis-primary-dark tabular-nums">
        {value ?? "-"}
      </dd>
    </div>
  );
}
