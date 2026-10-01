import { RequireAuth, RoutePermission } from "@/components/auth/RequireAuth";
import { CompanyProvider } from "@/components/company/CompanyProvider";
import { AppShell } from "@/components/layout/AppShell";
import { ToastProvider } from "@/components/ui/Toast";

/**
 * Layout commun à toutes les pages de l'application : réservé aux utilisateurs connectés, avec la
 * barre latérale, l'en-tête (avec la société active) et les notifications. Le contenu n'apparaît que si la permission existe.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <CompanyProvider>
        <ToastProvider>
          <AppShell>
            <RoutePermission>{children}</RoutePermission>
          </AppShell>
        </ToastProvider>
      </CompanyProvider>
    </RequireAuth>
  );
}
