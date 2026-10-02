import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

const CONTROL =
  "h-[42px] w-full rounded-lg border bg-simtis-card px-3 text-sm text-simtis-text placeholder:text-simtis-muted " +
  "transition-colors focus:ring-2 focus:outline-none disabled:cursor-not-allowed disabled:bg-simtis-background disabled:text-simtis-muted";

function controlClasses(invalid: boolean | undefined, className?: string) {
  return cn(
    CONTROL,
    invalid
      ? "border-simtis-danger focus:border-simtis-danger focus:ring-simtis-danger/15"
      : "border-simtis-border focus:border-simtis-primary focus:ring-simtis-primary/15",
    className,
  );
}

type FieldProps = {
  label: string;
  htmlFor: string;
  /** Aide affichée sous le champ, remplacée par l'erreur s'il y en a une. */
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
};

/** Libellé, champ, puis aide ou erreur. L'erreur est reliée au champ pour les lecteurs d'écran. */
export function Field({ label, htmlFor, hint, error, required, children }: FieldProps) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1.5 block text-sm font-medium text-simtis-text">
        {label}
        {required && (
          <span className="ml-0.5 text-simtis-danger" aria-hidden>
            *
          </span>
        )}
      </label>
      {children}
      {error ? (
        <p id={`${htmlFor}-message`} role="alert" className="mt-1.5 text-xs text-simtis-danger-fg">
          {error}
        </p>
      ) : (
        hint && (
          <p id={`${htmlFor}-message`} className="mt-1.5 text-xs text-simtis-muted">
            {hint}
          </p>
        )
      )}
    </div>
  );
}

type InputProps = InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean };

export function TextInput({ invalid, className, id, ...props }: InputProps) {
  return (
    <input
      id={id}
      type="text"
      aria-invalid={invalid || undefined}
      aria-describedby={id ? `${id}-message` : undefined}
      className={controlClasses(invalid, className)}
      {...props}
    />
  );
}

/** Nombre saisi au clavier : aligné à droite, chiffres tabulaires, clavier numérique sur mobile. */
export function NumberInput({ invalid, className, id, ...props }: InputProps) {
  return (
    <input
      id={id}
      type="text"
      inputMode="numeric"
      aria-invalid={invalid || undefined}
      aria-describedby={id ? `${id}-message` : undefined}
      className={controlClasses(invalid, cn("text-right tabular-nums", className))}
      {...props}
    />
  );
}

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  options: readonly { value: string; label: string }[];
  /** Première option, valeur vide (ex. « Aucun logo »). */
  placeholder?: string;
  invalid?: boolean;
};

export function Select({ options, placeholder, invalid, className, id, ...props }: SelectProps) {
  return (
    <select
      id={id}
      aria-invalid={invalid || undefined}
      aria-describedby={id ? `${id}-message` : undefined}
      className={controlClasses(invalid, className)}
      {...props}
    >
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

/** Date au format du navigateur ; la valeur reste « AAAA-MM-JJ ». */
export function DateInput({ invalid, className, id, ...props }: InputProps) {
  return (
    <input
      id={id}
      type="date"
      aria-invalid={invalid || undefined}
      aria-describedby={id ? `${id}-message` : undefined}
      className={controlClasses(invalid, cn("tabular-nums", className))}
      {...props}
    />
  );
}
