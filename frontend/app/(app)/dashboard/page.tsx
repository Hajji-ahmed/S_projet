import type { Metadata } from "next";
import { Suspense } from "react";

import { DashboardView } from "@/components/dashboard/DashboardView";

export const metadata: Metadata = { title: "Dashboard" };

export default function Page() {
  // useSearchParams (onglet, banque et période dans l'adresse) exige une frontière Suspense
  return (
    <Suspense>
      <DashboardView />
    </Suspense>
  );
}
