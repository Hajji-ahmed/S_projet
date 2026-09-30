import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/layout/PlaceholderPage";

export const metadata: Metadata = { title: "Devises" };

export default function Page() {
  return <PlaceholderPage title="Devises" description="Soldes par devise" />;
}
