import type { Metadata } from "next";
import { Suspense } from "react";

import { RelevesView } from "@/components/releves/RelevesView";

export const metadata: Metadata = { title: "Relevés" };

export default function Page() {
  // useSearchParams (ligne ouverte depuis le tableau Banques) exige une frontière Suspense
  return (
    <Suspense>
      <RelevesView />
    </Suspense>
  );
}
