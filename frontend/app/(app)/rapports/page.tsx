import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/layout/PlaceholderPage";

export const metadata: Metadata = { title: "Rapports" };

export default function Page() {
  return (
    <PlaceholderPage
      title="Rapports"
      description="Exports de la position, du rapprochement, des écarts et des prévisions"
    />
  );
}
