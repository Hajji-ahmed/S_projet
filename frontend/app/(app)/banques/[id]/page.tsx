import type { Metadata } from "next";

import { BankDetailView } from "@/components/banks/BankDetailView";

export const metadata: Metadata = { title: "Banque" };

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <BankDetailView bankId={Number(id)} />;
}
