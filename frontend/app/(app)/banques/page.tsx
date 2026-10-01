import type { Metadata } from "next";

import { BanksView } from "@/components/banks/BanksView";

export const metadata: Metadata = { title: "Banques" };

export default function Page() {
  return <BanksView />;
}
