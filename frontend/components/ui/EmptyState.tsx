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
      <Icon className="h-10 w-10 text-simtis-muted" strokeWidth={1.5} aria-hidden />
      <p className="text-sm text-simtis-muted">{message}</p>
      {action}
    </div>
  );
}
