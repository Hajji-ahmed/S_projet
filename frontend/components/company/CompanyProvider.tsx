"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { listCompanies } from "@/services/referentiel";
import type { Company } from "@/types/company";

const STORAGE_KEY = "simtis.societe-active";

type CompanyContextValue = {
  companies: Company[];
  /** Société active : tous les écrans n'affichent que ses données (jamais de consolidation). */
  company: Company | null;
  setCompanyId: (id: number) => void;
  status: "loading" | "ready" | "error";
};

const CompanyContext = createContext<CompanyContextValue | null>(null);

function readStoredId(): number | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value ? Number(value) : null;
  } catch {
    return null; // navigation privée ou stockage bloqué : la première société sera utilisée
  }
}

/** À placer sous RequireAuth : la liste des sociétés exige d'être connecté. */
export function CompanyProvider({ children }: { children: ReactNode }) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [status, setStatus] = useState<CompanyContextValue["status"]>("loading");
  const [selectedId, setSelectedId] = useState<number | null>(() =>
    typeof window === "undefined" ? null : readStoredId(),
  );

  useEffect(() => {
    let cancelled = false;
    listCompanies().then(
      (list) => {
        if (cancelled) return;
        setCompanies(list);
        setStatus("ready");
      },
      () => {
        if (!cancelled) setStatus("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  const setCompanyId = useCallback((id: number) => {
    setSelectedId(id);
    try {
      window.localStorage.setItem(STORAGE_KEY, String(id));
    } catch {
      // préférence non mémorisée : sans conséquence
    }
  }, []);

  // Une société mémorisée qui n'existe plus (ou désactivée) est remplacée par la première de la liste
  const company = companies.find((item) => item.id === selectedId) ?? companies[0] ?? null;

  return (
    <CompanyContext.Provider value={{ companies, company, setCompanyId, status }}>
      {children}
    </CompanyContext.Provider>
  );
}

export function useCompany() {
  const context = useContext(CompanyContext);
  if (!context) throw new Error("useCompany doit être utilisé dans un <CompanyProvider>.");
  return context;
}
