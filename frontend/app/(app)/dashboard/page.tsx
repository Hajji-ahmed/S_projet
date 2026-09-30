import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/layout/PlaceholderPage";

export const metadata: Metadata = { title: "Dashboard" };

export default function Page() {
  return (
    <PlaceholderPage
      title="Dashboard"
      description="Vue d'ensemble de la position bancaire, du rapprochement et des prévisions"
    />
  );
}
