import { AppShell } from "@/components/layout/AppShell";
import { ToastProvider } from "@/components/ui/Toast";

/** Layout commun à toutes les pages de l'application : barre latérale, en-tête, notifications. */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <ToastProvider>
      <AppShell>{children}</AppShell>
    </ToastProvider>
  );
}
