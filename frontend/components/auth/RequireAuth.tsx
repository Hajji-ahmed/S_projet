"use client";

import { ShieldX } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/LoadingState";
import { canAccess } from "@/lib/permissions";
import { DEFAULT_PATH, loginPathFor } from "@/lib/redirect";

/** Écran d'attente pendant la vérification de la session. */
function SessionLoading() {
  return (
    <div
      role="status"
      aria-busy="true"
      className="grid min-h-screen place-items-center bg-simtis-background"
    >
      <div className="w-64 space-y-3">
        <span className="sr-only">Vérification de la session...</span>
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>
    </div>
  );
}

/**
 * Réservé aux utilisateurs connectés : sinon, renvoi vers /login en mémorisant la page demandée.
 * Confort d'affichage seulement : la vraie protection est l'API, qui refuse tout appel sans jeton.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "anonymous") {
      router.replace(loginPathFor(window.location.pathname + window.location.search));
    }
  }, [status, router]);

  if (status !== "authenticated") return <SessionLoading />;
  return children;
}

/** Affiche la page seulement si l'utilisateur a la permission de la consulter. */
export function RoutePermission({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const pathname = usePathname();

  if (user && !canAccess(user.permissions, pathname)) {
    return (
      <Card>
        <EmptyState
          icon={ShieldX}
          message="Vous n'avez pas accès à cette page. Contactez un administrateur si nécessaire."
          action={
            <Link href={DEFAULT_PATH} className={buttonClasses("secondary")}>
              Retour au dashboard
            </Link>
          }
        />
      </Card>
    );
  }
  return children;
}
