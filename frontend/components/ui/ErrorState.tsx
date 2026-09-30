import { CircleAlert, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/Button";

type ErrorStateProps = {
  message?: string;
  onRetry?: () => void;
};

export function ErrorState({ message = "Une erreur est survenue.", onRetry }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center gap-3 px-4 py-12 text-center"
    >
      <CircleAlert className="h-10 w-10 text-simtis-danger" strokeWidth={1.5} aria-hidden />
      <p className="text-sm text-simtis-text">{message}</p>
      {onRetry && (
        <Button variant="secondary" icon={RefreshCw} onClick={onRetry}>
          Réessayer
        </Button>
      )}
    </div>
  );
}
