import type { Metadata } from "next";

import { EcrituresView } from "@/components/ecritures/EcrituresView";

export const metadata: Metadata = { title: "Écritures comptables" };

export default function Page() {
  return <EcrituresView />;
}
