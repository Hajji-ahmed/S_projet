import type { Metadata } from "next";

import { AComptabiliserView } from "@/components/frais/AComptabiliserView";

export const metadata: Metadata = { title: "À comptabiliser" };

export default function Page() {
  return <AComptabiliserView />;
}
