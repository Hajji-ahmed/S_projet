import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/layout/PlaceholderPage";

export const metadata: Metadata = { title: "Administration" };

export default function Page() {
  return (
    <PlaceholderPage title="Administration" description="Utilisateurs, rôles et permissions" />
  );
}
