import type { Metadata } from "next";
import { Suspense } from "react";

import { EcartsView } from "@/components/ecarts/EcartsView";

export const metadata: Metadata = { title: "Écarts" };

export default function Page() {
  // useSearchParams (lien direct vers un écart : /ecarts?ecart=12) exige une frontière Suspense
  return (
    <Suspense>
      <EcartsView />
    </Suspense>
  );
}
