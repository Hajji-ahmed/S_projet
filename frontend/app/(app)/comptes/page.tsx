import type { Metadata } from "next";

import { AccountsView } from "@/components/accounts/AccountsView";

export const metadata: Metadata = { title: "Comptes" };

export default function Page() {
  return <AccountsView />;
}
