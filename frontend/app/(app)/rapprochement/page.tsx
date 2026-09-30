import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/layout/PlaceholderPage";

export const metadata: Metadata = { title: "Rapprochement" };

export default function Page() {
  return (
    <PlaceholderPage
      title="Rapprochement"
      description="Rapprochement des transactions bancaires et des écritures comptables"
    />
  );
}
