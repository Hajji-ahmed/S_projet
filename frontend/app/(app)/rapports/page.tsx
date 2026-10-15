import type { Metadata } from "next";

import { RapportsView } from "@/components/rapports/RapportsView";

export const metadata: Metadata = { title: "Rapports" };

export default function Page() {
  return <RapportsView />;
}
