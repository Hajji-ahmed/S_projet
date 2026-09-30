import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/layout/PlaceholderPage";

export const metadata: Metadata = { title: "Position bancaire" };

export default function Page() {
  return (
    <PlaceholderPage
      title="Position bancaire"
      description="Soldes, crédits et position disponible"
    />
  );
}
