import { Hammer } from "lucide-react";

import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";

/** Page vide du socle technique : remplacée par le vrai contenu dans la phase du module. */
export function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <Card>
        <EmptyState icon={Hammer} message="Ce module est en cours de construction." />
      </Card>
    </>
  );
}
