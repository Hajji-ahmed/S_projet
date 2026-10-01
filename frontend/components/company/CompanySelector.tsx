"use client";

import { Building2, ChevronDown } from "lucide-react";

import { useCompany } from "@/components/company/CompanyProvider";

/** Choix de la société active, dans l'en-tête. */
export function CompanySelector() {
  const { companies, company, setCompanyId } = useCompany();
  if (!company) return null;

  return (
    <label className="relative flex items-center">
      <span className="sr-only">Société active</span>
      <Building2
        className="pointer-events-none absolute left-3 hidden h-4 w-4 text-simtis-primary sm:block"
        aria-hidden
      />
      <select
        value={company.id}
        onChange={(event) => setCompanyId(Number(event.target.value))}
        className="h-10 max-w-[130px] cursor-pointer appearance-none truncate rounded-lg border border-simtis-border bg-simtis-light/50 pr-8 pl-3 text-sm font-medium text-simtis-primary-dark transition-colors hover:bg-simtis-light focus:border-simtis-primary focus:ring-2 focus:ring-simtis-primary/15 focus:outline-none sm:max-w-none sm:pl-9"
      >
        {companies.map((item) => (
          <option key={item.id} value={item.id}>
            {item.nom}
          </option>
        ))}
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-2.5 h-4 w-4 text-simtis-primary"
        aria-hidden
      />
    </label>
  );
}
