import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/layout/PlaceholderPage";

export const metadata: Metadata = { title: "Banques" };

export default function Page() {
  return <PlaceholderPage title="Banques" description="Gestion des banques et comptes bancaires" />;
}
