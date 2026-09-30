"use client";

import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";
import { API_URL } from "@/lib/api";
import { getHealth } from "@/services/health";

type ApiState = "loading" | "ok" | "degraded" | "unreachable";

const LABELS: Record<ApiState, string> = {
  loading: "Vérification...",
  ok: "API et base de données connectées",
  degraded: "API connectée, base de données injoignable",
  unreachable: "API injoignable",
};

const STYLES: Record<ApiState, string> = {
  loading: "bg-simtis-neutral-bg text-simtis-neutral-fg",
  ok: "bg-simtis-success-bg text-simtis-success-fg",
  degraded: "bg-simtis-warning-bg text-simtis-warning-fg",
  unreachable: "bg-simtis-danger-bg text-simtis-danger-fg",
};

/** Vérifie en direct que le frontend joint FastAPI (et que FastAPI joint PostgreSQL). */
export function ApiStatus() {
  const [state, setState] = useState<ApiState>("loading");

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((health) => {
        if (!cancelled) setState(health.status);
      })
      .catch(() => {
        if (!cancelled) setState("unreachable");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex flex-wrap items-center gap-3 text-sm">
      <span
        role="status"
        className={cn("inline-flex items-center rounded-full px-3 py-1 font-medium", STYLES[state])}
      >
        {LABELS[state]}
      </span>
      <span className="text-simtis-muted">
        GET <code>{API_URL}/health</code>
      </span>
    </div>
  );
}
