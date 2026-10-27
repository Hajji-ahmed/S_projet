"use client";

import { Check, ChevronDown, Landmark } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { cn } from "@/lib/cn";
import { moveIndex } from "@/lib/statements";

type BankOption = { id: number; code: string; logo: string | null };

type BankPickerProps = {
  id: string;
  banques: readonly BankOption[];
  /** Banque choisie ; undefined = toutes les banques. */
  value: number | undefined;
  onChange: (id: number | undefined) => void;
};

const TOUTES = "Toutes les banques";

/**
 * Filtre « Banque » avec le logo de chaque banque (27/10/2026) : une liste native ne peut pas
 * afficher d'image. La première ligne est « Toutes les banques ». Clavier comme `AccountPicker` :
 * flèches, Début, Fin, Entrée ou Espace pour choisir, Échap pour fermer.
 */
export function BankPicker({ id, banques, value, onChange }: BankPickerProps) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  // Index 0 : toutes les banques, puis une ligne par banque
  const choix: (BankOption | null)[] = [null, ...banques];
  const selected = banques.find((banque) => banque.id === value) ?? null;
  const listId = `${id}-liste`;

  useEffect(() => {
    if (!open) return;
    function onPointer(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  useEffect(() => {
    if (open) listRef.current?.focus();
  }, [open]);

  function openList() {
    setActive(
      Math.max(
        0,
        choix.findIndex((option) => (option?.id ?? undefined) === value),
      ),
    );
    setOpen(true);
  }

  function choose(index: number) {
    if (index < 0 || index >= choix.length) return;
    onChange(choix[index]?.id);
    setOpen(false);
    buttonRef.current?.focus();
  }

  function onButtonKey(event: KeyboardEvent<HTMLButtonElement>) {
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
      event.preventDefault();
      openList();
    }
  }

  function onListKey(event: KeyboardEvent<HTMLUListElement>) {
    const next = moveIndex(active, event.key, choix.length);
    if (next !== null) {
      event.preventDefault();
      setActive(next);
      listRef.current
        ?.querySelector(`[data-index="${next}"]`)
        ?.scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      choose(active);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      buttonRef.current?.focus();
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        id={id}
        type="button"
        aria-label={`Banque : ${selected?.code ?? TOUTES}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        onClick={() => (open ? setOpen(false) : openList())}
        onKeyDown={onButtonKey}
        className={cn(
          "flex h-11 min-w-[190px] items-center justify-between gap-3 rounded-[12px] border bg-simtis-card px-3 text-left text-sm font-medium text-simtis-text shadow-simtis transition-colors",
          "focus:ring-2 focus:ring-simtis-primary/15 focus:outline-none",
          open ? "border-simtis-primary" : "border-simtis-border focus:border-simtis-primary",
        )}
      >
        <Choix option={selected} />
        <ChevronDown className="h-4 w-4 shrink-0 text-simtis-muted" aria-hidden />
      </button>

      {open && (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          tabIndex={-1}
          aria-label="Banque"
          aria-activedescendant={`${id}-option-${choix[active]?.id ?? "toutes"}`}
          onKeyDown={onListKey}
          className="absolute right-0 z-20 mt-1 max-h-80 min-w-full overflow-auto rounded-[12px] border border-simtis-border bg-simtis-card py-1 shadow-simtis-hover focus:outline-none"
        >
          {choix.map((option, index) => {
            const isSelected = (option?.id ?? undefined) === value;
            return (
              <li
                key={option?.id ?? "toutes"}
                id={`${id}-option-${option?.id ?? "toutes"}`}
                role="option"
                aria-selected={isSelected}
                data-index={index}
                onPointerEnter={() => setActive(index)}
                onClick={() => choose(index)}
                className={cn(
                  "flex cursor-pointer items-center justify-between gap-3 px-3 py-2 text-sm whitespace-nowrap",
                  index === active && "bg-simtis-light",
                  isSelected && "font-medium text-simtis-primary-dark",
                )}
              >
                <Choix option={option} />
                {isSelected && <Check className="h-4 w-4 text-simtis-primary" aria-hidden />}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** Une banque avec son logo, ou « Toutes les banques » avec une icône de même taille. */
function Choix({ option }: { option: BankOption | null }) {
  if (option) return <BankLabel code={option.code} logo={option.logo} />;
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-simtis-light text-simtis-primary">
        <Landmark className="h-3.5 w-3.5" aria-hidden />
      </span>
      {TOUTES}
    </span>
  );
}
