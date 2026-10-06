import type { Metadata } from "next";

import { RapprochementView } from "@/components/rapprochement/RapprochementView";

export const metadata: Metadata = { title: "Rapprochement" };

export default function Page() {
  return <RapprochementView />;
}
