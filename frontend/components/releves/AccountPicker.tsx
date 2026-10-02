"use client";

import { Check, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { cn } from "@/lib/cn";
import { moveIndex } from "@/lib/statements";

export type AccountOption = {
  id: number;
  bankCode: string;
  logo: string | null;
  /** « CIH · MAD · Compte DÉMO ». */
  label: string;
};

type AccountPickerProps = {
  /** Identifiant du bouton, relié au libellé du champ (`<Field htmlFor>`). */
  id: string;
  options: AccountOption[];
  value: number | null;
  onChange: (id: number) => void;
  placeholder: string;
  disabled?: boolean;
};

/**
 * Liste déroulante des comptes avec le logo de chaque banque : une liste native ne peut pas
 * afficher d'image. Clavier : flèches, Début, Fin, Entrée ou Espace pour choisir, Échap pour fermer.
 */
export function AccountPicker({
  id,
  options,
  value,
  onChange,
  placeholder,
  disabled,
}: AccountPickerProps) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const selected = options.find((option) => option.id === value);
  const listId = `${id}-liste`;

  // Un clic en dehors ferme la liste
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
    if (disabled || options.length === 0) return;
    setActive(
      Math.max(
        0,
        options.findIndex((option) => option.id === value),
      ),
    );
    setOpen(true);
  }

  function choose(index: number) {
    const option = options[index];
    if (!option) return;
    onChange(option.id);
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
    const next = moveIndex(active, event.key, options.length);
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
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        onClick={() => (open ? setOpen(false) : openList())}
        onKeyDown={onButtonKey}
        className={cn(
          "flex h-[42px] w-full items-center justify-between gap-2 rounded-lg border bg-simtis-card px-3 text-left text-sm text-simtis-text transition-colors",
          "focus:ring-2 focus:ring-simtis-primary/15 focus:outline-none disabled:cursor-not-allowed disabled:bg-simtis-background",
          open ? "border-simtis-primary" : "border-simtis-border focus:border-simtis-primary",
        )}
      >
        {selected ? (
          <BankLabel code={selected.bankCode} logo={selected.logo} className="min-w-0 truncate">
            {selected.label}
          </BankLabel>
        ) : (
          <span className="text-simtis-muted">{placeholder}</span>
        )}
        <ChevronDown className="h-4 w-4 shrink-0 text-simtis-muted" aria-hidden />
      </button>

      {open && (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          tabIndex={-1}
          aria-labelledby={id}
          aria-activedescendant={`${id}-option-${options[active]?.id}`}
          onKeyDown={onListKey}
          className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-lg border border-simtis-border bg-simtis-card py-1 shadow-simtis focus:outline-none"
        >
          {options.map((option, index) => {
            const isSelected = option.id === value;
            return (
              <li
                key={option.id}
                id={`${id}-option-${option.id}`}
                role="option"
                aria-selected={isSelected}
                data-index={index}
                onPointerEnter={() => setActive(index)}
                onClick={() => choose(index)}
                className={cn(
                  "flex cursor-pointer items-center justify-between gap-2 px-3 py-2 text-sm",
                  index === active && "bg-simtis-light",
                  isSelected && "font-medium text-simtis-primary-dark",
                )}
              >
                <BankLabel code={option.bankCode} logo={option.logo}>
                  {option.label}
                </BankLabel>
                {isSelected && <Check className="h-4 w-4 text-simtis-primary" aria-hidden />}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
