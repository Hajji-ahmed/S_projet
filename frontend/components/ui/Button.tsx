import type { LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-simtis-primary text-white shadow-simtis hover:bg-simtis-primary-dark",
  secondary:
    "border border-simtis-border bg-simtis-card text-simtis-primary-dark hover:border-simtis-primary/40 hover:bg-simtis-surface",
  danger: "bg-simtis-danger text-white shadow-simtis hover:bg-simtis-danger-fg",
  ghost: "text-simtis-primary hover:bg-simtis-light",
};

/** Classes d'un bouton, réutilisables sur un `<Link>` pour un lien qui a l'aspect d'un bouton. */
export function buttonClasses(variant: ButtonVariant = "primary", className?: string) {
  return cn(
    "inline-flex h-10 items-center gap-2 rounded-[10px] px-4 text-sm font-medium whitespace-nowrap transition-colors duration-200",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-simtis-secondary",
    "active:translate-y-px disabled:pointer-events-none disabled:opacity-50 disabled:shadow-none",
    VARIANTS[variant],
    className,
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  icon?: LucideIcon;
};

export function Button({
  variant = "primary",
  icon: Icon,
  className,
  children,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button type={type} className={buttonClasses(variant, className)} {...props}>
      {Icon && <Icon className="h-4 w-4 shrink-0" aria-hidden />}
      {children}
    </button>
  );
}
