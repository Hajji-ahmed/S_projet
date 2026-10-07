"use client";

import { GitCompareArrows, History, ListChecks, Play } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { BankLabel } from "@/components/banks/BankLabel";
import { useCompany } from "@/components/company/CompanyProvider";
import { AccountButton } from "@/components/ecritures/EntriesCard";
import { EntriesPane } from "@/components/rapprochement/EntriesPane";
import { HistoryTab } from "@/components/rapprochement/HistoryTab";
import { MatchPanel } from "@/components/rapprochement/MatchPanel";
import { ProposalsTab } from "@/components/rapprochement/ProposalsTab";
import { StatButton } from "@/components/rapprochement/StatButton";
import { TransactionsPane } from "@/components/rapprochement/TransactionsPane";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DateInput, Field } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api";
import { businessToday } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { ECARTS_ACTIFS } from "@/lib/features";
import {
  defaultPeriod,
  operationOf,
  toggleStatut,
  type ReconciliationFilter,
} from "@/lib/reconciliation";
import { PERMISSIONS, hasAnyPermission } from "@/lib/permissions";
import { listAccounts } from "@/services/accounts";
import { listAmbiguous, listProposals, runReconciliation } from "@/services/reconciliation";
import type { Account } from "@/types/account";
import type { Ecriture, StatutRapprochement } from "@/types/accounting";
import type { Ambigues, Correspondances, Operation, OperationsPage } from "@/types/reconciliation";

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

// Compteurs qui filtrent le volet « Transactions bancaires ». « À vérifier » n'en fait pas partie :
// ces opérations se traitent dans l'onglet Propositions (décision du 07/10/2026).
const COMPTEURS: { statut: StatutRapprochement; label: string }[] = [
  { statut: "Rapprochée", label: "Rapprochées" },
  { statut: "Non rapprochée", label: "Non rapprochées" },
];

function plural(n: number, word: string): string {
  return `${n} ${word}${n > 1 ? "s" : ""}`;
}

function Rapprochement({ companyId }: { companyId: number }) {
  const { user } = useAuth();
  const { toast } = useToast();
  const canValidate =
    !!user && hasAnyPermission(user.permissions, [PERMISSIONS.RECONCILIATION_VALIDATE]);
  // Tous les boutons « Signaler un écart » de la page en dépendent
  const canManageDiscrepancies =
    ECARTS_ACTIFS &&
    !!user &&
    hasAnyPermission(user.permissions, [PERMISSIONS.DISCREPANCIES_MANAGE]);

  const [filter, setFilter] = useState<ReconciliationFilter>(() => defaultPeriod(businessToday()));
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [reloadKey, setReloadKey] = useState(0);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [entry, setEntry] = useState<Ecriture | null>(null);
  const [parStatut, setParStatut] = useState<Record<StatutRapprochement, number> | null>(null);
  const [pending, setPending] = useState<Correspondances | null>(null);
  const [ambigues, setAmbigues] = useState<Ambigues | null>(null);
  const [running, setRunning] = useState(false);
  const [statut, setStatut] = useState("");
  const [tab, setTab] = useState<"rapprochement" | "propositions" | "historique">("rapprochement");

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
    listAmbiguous(companyId, filter).then(
      (result) => {
        if (!cancelled) setAmbigues(result);
      },
      () => {
        if (!cancelled) setAmbigues(null);
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

  // Tout ce qui est à vérifier : les propositions en attente et les opérations ambiguës
  const aVerifier =
    pending && ambigues ? pending.correspondances.length + ambigues.ambigues.length : null;
  const logos = new Map(accounts.map((account) => [account.bank_code, account.bank_logo]));

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
              <div
                className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3"
                role="group"
                aria-label="Résumé du rapprochement : un clic filtre les transactions"
              >
                {COMPTEURS.map(({ statut: value, label }) => (
                  <StatButton
                    key={value}
                    label={label}
                    value={parStatut?.[value]}
                    active={tab === "rapprochement" && statut === value}
                    description={`Afficher les transactions « ${value} »`}
                    onClick={() => {
                      setTab("rapprochement");
                      setStatut((current) => toggleStatut(current, value));
                    }}
                  />
                ))}
                <StatButton
                  label="Propositions en attente"
                  value={aVerifier ?? undefined}
                  active={tab === "propositions"}
                  description="Voir les propositions en attente"
                  onClick={() => setTab("propositions")}
                />
              </div>
            </div>
          )}
        </div>
      </Card>

      {!periodError && (
        <div
          className="flex gap-2 border-b border-simtis-border"
          role="tablist"
          aria-label="Vue du rapprochement"
        >
          {(
            [
              ["rapprochement", "Rapprochement", GitCompareArrows],
              [
                "propositions",
                `Propositions${aVerifier !== null ? ` (${aVerifier})` : ""}`,
                ListChecks,
              ],
              ["historique", "Historique", History],
            ] as const
          ).map(([value, label, Icon]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={tab === value}
              onClick={() => setTab(value)}
              className={cn(
                "-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition-colors duration-200",
                tab === value
                  ? "border-simtis-primary text-simtis-primary-dark"
                  : "border-transparent text-simtis-muted hover:text-simtis-primary",
              )}
            >
              <Icon className="h-4 w-4" aria-hidden />
              {label}
            </button>
          ))}
        </div>
      )}

      {!periodError && tab === "propositions" && (
        <ProposalsTab
          companyId={companyId}
          pending={pending}
          logos={logos}
          canValidate={canValidate}
          canManageDiscrepancies={canManageDiscrepancies}
          onChanged={reload}
          onOpen={(item) => {
            setTab("rapprochement");
            setStatut("");
            setOperation(operationOf(item));
          }}
          ambigues={ambigues}
          onOpenOperation={(selected) => {
            setTab("rapprochement");
            setStatut("");
            setOperation(selected);
          }}
        />
      )}

      {!periodError && tab === "historique" && (
        <HistoryTab
          key={`hist-${filterKey}`}
          companyId={companyId}
          filter={filter}
          canValidate={canValidate}
          reloadKey={reloadKey}
          onChanged={reload}
        />
      )}

      {!periodError && tab === "rapprochement" && (
        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(300px,360px)_minmax(0,1fr)]">
          <TransactionsPane
            key={`tx-${filterKey}`}
            companyId={companyId}
            filter={filter}
            reloadKey={reloadKey}
            selectedId={operation?.id ?? null}
            onSelect={setOperation}
            onLoaded={handleOperations}
            statut={statut}
            onStatutChange={setStatut}
          />
          <div className="xl:sticky xl:top-4">
            <MatchPanel
              key={operation?.id ?? "aucune"}
              companyId={companyId}
              operation={operation}
              entry={entry}
              canValidate={canValidate}
              canManageDiscrepancies={canManageDiscrepancies}
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
    </>
  );
}
