import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/layout/PlaceholderPage";

export const metadata: Metadata = { title: "Prévisions" };

export default function Page() {
  return (
    <PlaceholderPage
      title="Prévisions de trésorerie"
      description="Flux prévus et position prévisionnelle"
    />
  );
}
