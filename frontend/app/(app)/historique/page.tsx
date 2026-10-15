import type { Metadata } from "next";

import { HistoriqueView } from "@/components/historique/HistoriqueView";

export const metadata: Metadata = { title: "Historique" };

export default function Page() {
  return <HistoriqueView />;
}
