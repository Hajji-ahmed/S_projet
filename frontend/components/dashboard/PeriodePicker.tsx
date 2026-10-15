"use client";

import { CalendarDays, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { DateInput } from "@/components/ui/Field";
import { cn } from "@/lib/cn";
import { libellePeriode } from "@/lib/dashboard";

type Periode = { from: string; to: string };

/** Pastille « 1 oct. 2026 - 14 oct. 2026 » qui ouvre les deux dates de la période. */
export function PeriodePicker({
  periode,
  onChange,
}: {
  periode: Periode;
  onChange: (cle: keyof Periode, valeur: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const fermerEchap = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const fermerDehors = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", fermerEchap);
    window.addEventListener("mousedown", fermerDehors);
    return () => {
      window.removeEventListener("keydown", fermerEchap);
      window.removeEventListener("mousedown", fermerDehors);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((ouvert) => !ouvert)}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="flex h-11 items-center gap-2.5 rounded-[12px] border border-simtis-border bg-simtis-card px-4 text-sm font-medium text-simtis-text shadow-simtis transition-colors duration-200 hover:bg-simtis-surface"
      >
        <CalendarDays className="h-4 w-4 text-simtis-muted" aria-hidden />
        <span className="tabular-nums">{libellePeriode(periode.from, periode.to)}</span>
        <ChevronDown
          className={cn(
            "h-4 w-4 text-simtis-muted transition-transform duration-200",
            open && "rotate-180",
          )}
          aria-hidden
        />
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Période du dashboard"
          className="absolute right-0 z-30 mt-2 w-[min(320px,calc(100vw-2rem))] space-y-3 rounded-card border border-simtis-border bg-simtis-card p-4 shadow-simtis-hover"
        >
          <label className="block text-xs font-medium text-simtis-muted">
            Du
            <DateInput
              className="mt-1"
              value={periode.from}
              onChange={(event) => onChange("from", event.target.value)}
            />
          </label>
          <label className="block text-xs font-medium text-simtis-muted">
            Au
            <DateInput
              className="mt-1"
              value={periode.to}
              onChange={(event) => onChange("to", event.target.value)}
            />
          </label>
        </div>
      )}
    </div>
  );
}
