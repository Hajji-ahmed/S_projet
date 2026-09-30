import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/layout/PlaceholderPage";

export const metadata: Metadata = { title: "Relevés" };

export default function Page() {
  return (
    <PlaceholderPage
      title="Relevés bancaires"
      description="Import et consultation des relevés bancaires"
    />
  );
}
