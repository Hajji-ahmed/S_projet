import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/layout/PlaceholderPage";

export const metadata: Metadata = { title: "Écarts" };

export default function Page() {
  return (
    <PlaceholderPage
      title="Écarts"
      description="Suivi des opérations non rapprochées et des écarts"
    />
  );
}
