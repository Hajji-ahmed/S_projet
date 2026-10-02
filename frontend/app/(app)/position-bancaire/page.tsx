import type { Metadata } from "next";

import { PositionView } from "@/components/position/PositionView";

export const metadata: Metadata = { title: "Position bancaire" };

export default function Page() {
  return <PositionView />;
}
