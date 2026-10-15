import type { Metadata } from "next";

import { AdministrationView } from "@/components/administration/AdministrationView";

export const metadata: Metadata = { title: "Administration" };

export default function Page() {
  return <AdministrationView />;
}
