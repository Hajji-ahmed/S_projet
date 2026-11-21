"use client";

import { useEffect, useState } from "react";

import { AccountChipLabel } from "@/components/banks/AccountChipLabel";
import { AccountButton } from "@/components/ecritures/EntriesCard";
import { Card } from "@/components/ui/Card";
import { DateInput, Field } from "@/components/ui/Field";
import { businessToday } from "@/lib/balances";
import { cn } from "@/lib/cn";
import {
  CLE_PERIODE,
  periodeAStocker,
  periodeMemorisee,
  periodeRapprochement,
  raccourcisPeriode,
  type ReconciliationFilter,
} from "@/lib/reconciliation";
import { listAccounts } from "@/services/accounts";
import type { Account } from "@/types/account";

/**
 * Filtre compte + période partagé par /rapprochement et /a-comptabiliser (21/11/2026) : du
 * 1er janvier à aujourd'hui, ou la dernière période choisie sur ce poste (même clé pour les deux
 * pages). Seuls les comptes qui ont un journal Sage sont proposés.
 */
export function useFiltreRapprochement(companyId: number) {
  const [filter, setFilter] = useState<ReconciliationFilter>(() =>
    periodeRapprochement(businessToday()),
  );
  // La période gardée par le navigateur est lue avant le premier chargement des listes
  const [periodeLue, setPeriodeLue] = useState(false);
  const [accounts, setAccounts] = useState<Account[]>([]);

  useEffect(() => {
    let brut: string | null = null;
    try {
      brut = window.localStorage.getItem(CLE_PERIODE);
    } catch {
      // Stockage indisponible : période par défaut
    }
    const periode = periodeMemorisee(brut, businessToday());
    // eslint-disable-next-line react-hooks/set-state-in-effect -- lecture unique du navigateur
    setFilter((current) => ({ ...current, ...periode }));
    setPeriodeLue(true);
  }, []);

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

  function changeFilter(next: Partial<ReconciliationFilter>) {
    setFilter((current) => {
      const suivant = { ...current, ...next };
      if ("from" in next || "to" in next) {
        try {
          window.localStorage.setItem(CLE_PERIODE, periodeAStocker(suivant, businessToday()));
        } catch {
          // Stockage indisponible : le choix vaut pour la visite en cours
        }
      }
      return suivant;
    });
  }

  const periodError =
    filter.from && filter.to && filter.from > filter.to
      ? "La date de début doit précéder la date de fin."
      : !filter.from || !filter.to
        ? "Choisissez une période."
        : null;

  return { filter, changeFilter, periodeLue, periodError, accounts };
}

type FiltreRapprochementProps = {
  /** Préfixe des id des champs Du / Au, unique dans la page. */
  idPrefix: string;
  filter: ReconciliationFilter;
  accounts: Account[];
  periodError: string | null;
  onChange: (next: Partial<ReconciliationFilter>) => void;
};

/** Barre « Tous les comptes / un compte », dates Du / Au et raccourcis de période. */
export function FiltreRapprochement({
  idPrefix,
  filter,
  accounts,
  periodError,
  onChange,
}: FiltreRapprochementProps) {
  return (
    <Card>
      <div className="space-y-4">
        <div className="flex gap-2 overflow-x-auto pb-1" role="group" aria-label="Compte bancaire">
          <AccountButton
            active={filter.bankAccountId === undefined}
            onClick={() => onChange({ bankAccountId: undefined })}
          >
            Tous les comptes
          </AccountButton>
          {accounts.map((account) => (
            <AccountButton
              key={account.id}
              active={filter.bankAccountId === account.id}
              onClick={() => onChange({ bankAccountId: account.id })}
            >
              <AccountChipLabel account={account} />
            </AccountButton>
          ))}
        </div>

        <div className="flex flex-wrap items-end gap-x-3 gap-y-2">
          <div className="w-full max-w-[170px]">
            <Field label="Du" htmlFor={`${idPrefix}-du`}>
              <DateInput
                id={`${idPrefix}-du`}
                value={filter.from}
                onChange={(event) => onChange({ from: event.target.value })}
              />
            </Field>
          </div>
          <div className="w-full max-w-[170px]">
            <Field label="Au" htmlFor={`${idPrefix}-au`}>
              <DateInput
                id={`${idPrefix}-au`}
                value={filter.to}
                onChange={(event) => onChange({ to: event.target.value })}
              />
            </Field>
          </div>
          {/* Raccourcis de période (11/11/2026) : remplissent Du et Au */}
          <div
            className="flex flex-wrap gap-1 pb-1"
            role="group"
            aria-label="Raccourcis de période"
          >
            {raccourcisPeriode(businessToday()).map((raccourci) => {
              const actif = filter.from === raccourci.from && filter.to === raccourci.to;
              return (
                <button
                  key={raccourci.label}
                  type="button"
                  aria-pressed={actif}
                  onClick={() => onChange({ from: raccourci.from, to: raccourci.to })}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-sm font-medium transition-colors duration-200",
                    actif
                      ? "border-simtis-primary bg-simtis-light text-simtis-primary-dark"
                      : "border-simtis-border bg-simtis-card text-simtis-muted hover:border-simtis-primary hover:text-simtis-primary",
                  )}
                >
                  {raccourci.label}
                </button>
              );
            })}
          </div>
          {periodError && (
            <p role="alert" className="pb-2 text-sm text-simtis-danger-fg">
              {periodError}
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}
