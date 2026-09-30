import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/layout/PlaceholderPage";

export const metadata: Metadata = { title: "Comptes" };

export default function Page() {
  return <PlaceholderPage title="Comptes" description="Gestion des comptes bancaires" />;
}
