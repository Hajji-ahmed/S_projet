import { ArrowRight, type LucideIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type CardProps = {
  title?: string;
  icon?: LucideIcon;
  /** Lien « Voir tout → » en haut à droite. */
  action?: { label: string; href: string };
  /** Contenu ajouté à droite du titre, sur la même ligne (bouton « Filtres » des volets). */
  headerExtra?: ReactNode;
  /** Marges et en-tête réduits (volets du rapprochement, 28/10/2026). */
  compact?: boolean;
  className?: string;
  children: ReactNode;
};

/** Carte de base : sert aussi de conteneur aux tableaux et aux graphiques. */
export function Card({
  title,
  icon: Icon,
  action,
  headerExtra,
  compact = false,
  className,
  children,
}: CardProps) {
  return (
    <section
      className={cn(
        "rounded-card border border-simtis-border bg-simtis-card shadow-simtis",
        compact ? "p-3" : "p-5 lg:p-6",
        className,
      )}
    >
      {title && (
        <header
          className={cn(
            "flex flex-wrap items-center justify-between",
            compact ? "mb-2 gap-2" : "mb-4 gap-3",
          )}
        >
          <div className={cn("flex items-center", compact ? "gap-2" : "gap-3")}>
            {Icon && (
              <span
                className={cn(
                  "grid shrink-0 place-items-center bg-simtis-light text-simtis-primary",
                  compact ? "h-7 w-7 rounded-lg" : "h-9 w-9 rounded-[10px]",
                )}
              >
                <Icon className={compact ? "h-4 w-4" : "h-5 w-5"} aria-hidden />
              </span>
            )}
            <h2
              className={cn(
                "font-semibold tracking-tight text-simtis-text",
                compact ? "text-[15px]" : "text-base",
              )}
            >
              {title}
            </h2>
            {headerExtra}
          </div>
          {action && (
            <Link
              href={action.href}
              className="group flex items-center gap-1 rounded-md text-sm font-medium whitespace-nowrap text-simtis-primary transition-colors hover:text-simtis-primary-dark"
            >
              {action.label}{" "}
              <ArrowRight
                className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5"
                aria-hidden
              />
            </Link>
          )}
        </header>
      )}
      {children}
    </section>
  );
}
