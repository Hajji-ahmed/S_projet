"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";

/** Parties de la démonstration qui ont besoin d'interactivité (modale, notifications, réessayer). */
export function InteractiveDemo() {
  const [modalOpen, setModalOpen] = useState(false);
  const { toast } = useToast();

  return (
    <>
      <Card title="États de l'interface">
        <div className="grid gap-6 lg:grid-cols-3">
          <div>
            <p className="mb-3 text-xs font-semibold text-simtis-muted uppercase">Chargement</p>
            <LoadingState rows={3} />
          </div>
          <div>
            <p className="mb-3 text-xs font-semibold text-simtis-muted uppercase">Vide</p>
            <EmptyState message="Aucun relevé bancaire disponible." />
          </div>
          <div>
            <p className="mb-3 text-xs font-semibold text-simtis-muted uppercase">Erreur</p>
            <ErrorState onRetry={() => toast("Nouvelle tentative lancée.")} />
          </div>
        </div>
      </Card>

      <Card title="Fenêtre modale et notifications">
        <div className="flex flex-wrap gap-3">
          <Button variant="secondary" onClick={() => setModalOpen(true)}>
            Ouvrir la fenêtre modale
          </Button>
          <Button variant="secondary" onClick={() => toast("Opération enregistrée.")}>
            Notification de succès
          </Button>
          <Button variant="secondary" onClick={() => toast("L'opération a échoué.", "error")}>
            Notification d&apos;erreur
          </Button>
        </div>
      </Card>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Confirmer l'action"
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              Annuler
            </Button>
            <Button
              onClick={() => {
                setModalOpen(false);
                toast("Action confirmée.");
              }}
            >
              Confirmer
            </Button>
          </>
        }
      >
        Exemple de fenêtre modale. Elle se ferme avec Échap, un clic sur le fond ou la croix.
      </Modal>
    </>
  );
}
