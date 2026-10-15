import { Inbox, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

type EmptyStateProps = {
  message: string;
  icon?: LucideIcon;
  /** Action principale éventuelle, ex. un bouton « + Importer un relevé ». */
  action?: ReactNode;
};

export function EmptyState({ message, icon: Icon = Inbox, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-4 py-12 text-center">
      <span className="grid h-14 w-14 place-items-center rounded-full bg-simtis-surface">
        <Icon className="h-7 w-7 text-simtis-muted" strokeWidth={1.5} aria-hidden />
      </span>
      <p className="text-sm text-simtis-muted">{message}</p>
      {action}
    </div>
  );
}
