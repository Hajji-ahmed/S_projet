import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/layout/PlaceholderPage";

export const metadata: Metadata = { title: "Historique" };

export default function Page() {
  return <PlaceholderPage title="Historique" description="Journal des opérations et validations" />;
}
