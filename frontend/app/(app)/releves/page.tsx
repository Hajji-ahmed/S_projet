import type { Metadata } from "next";

import { RelevesView } from "@/components/releves/RelevesView";

export const metadata: Metadata = { title: "Relevés" };

export default function Page() {
  return <RelevesView />;
}
