import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/layout/PlaceholderPage";

export const metadata: Metadata = { title: "Écritures comptables" };

export default function Page() {
  return (
    <PlaceholderPage
      title="Écritures comptables"
      description="Écritures importées depuis Sage / SI"
    />
  );
}
