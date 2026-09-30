import { ArrowRight, type LucideIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type CardProps = {
  title?: string;
  icon?: LucideIcon;
  /** Lien « Voir tout → » en haut à droite. */
  action?: { label: string; href: string };
  className?: string;
  children: ReactNode;
};

/** Carte de base : sert aussi de conteneur aux tableaux et aux graphiques. */
export function Card({ title, icon: Icon, action, className, children }: CardProps) {
  return (
    <section
      className={cn(
        "rounded-[14px] border border-simtis-border bg-simtis-card p-5 shadow-simtis lg:p-6",
        className,
      )}
    >
      {title && (
        <header className="mb-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            {Icon && (
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-simtis-light text-simtis-primary">
                <Icon className="h-5 w-5" aria-hidden />
              </span>
            )}
            <h2 className="text-base font-semibold text-simtis-text">{title}</h2>
          </div>
          {action && (
            <Link
              href={action.href}
              className="flex items-center gap-1 text-sm font-medium whitespace-nowrap text-simtis-primary hover:underline"
            >
              {action.label} <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          )}
        </header>
      )}
      {children}
    </section>
  );
}
