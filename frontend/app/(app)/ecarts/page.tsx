import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { EcartsView } from "@/components/ecarts/EcartsView";
import { ECARTS_ACTIFS } from "@/lib/features";

export const metadata: Metadata = { title: "Écarts" };

export default function Page() {
  // Fonction mise de côté le 07/10/2026 : la page n'existe plus tant qu'elle n'est pas réactivée
  if (!ECARTS_ACTIFS) notFound();
  // useSearchParams (lien direct vers un écart : /ecarts?ecart=12) exige une frontière Suspense
  return (
    <Suspense>
      <EcartsView />
    </Suspense>
  );
}
