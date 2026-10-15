"use client";

import { Check, Copy, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import type { PasswordResult } from "@/types/admin";

/** Mot de passe provisoire : affiché une seule fois, à transmettre à l'utilisateur. */
export function PasswordModal({
  titre,
  result,
  onClose,
}: {
  titre: string;
  result: PasswordResult;
  onClose: () => void;
}) {
  const [copie, setCopie] = useState(false);

  async function copier() {
    try {
      await navigator.clipboard.writeText(result.mot_de_passe);
      setCopie(true);
    } catch {
      setCopie(false);
    }
  }

  return (
    <Modal
      open
      title={titre}
      onClose={onClose}
      footer={<Button onClick={onClose}>J&apos;ai noté le mot de passe</Button>}
    >
      <p>
        Mot de passe provisoire de <strong>{result.user.nom}</strong> ({result.user.email}) :
      </p>
      <div className="mt-3 flex items-center gap-2 rounded-[12px] border border-simtis-border bg-simtis-surface p-3">
        <code className="min-w-0 flex-1 font-mono text-base font-semibold tracking-wide break-all text-simtis-text select-all">
          {result.mot_de_passe}
        </code>
        <Button variant="secondary" icon={copie ? Check : Copy} onClick={copier}>
          {copie ? "Copié" : "Copier"}
        </Button>
      </div>
      <p className="mt-3 flex items-start gap-2 rounded-[10px] bg-simtis-warning-bg px-3 py-2.5 text-simtis-warning-fg">
        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        Il ne sera plus jamais affiché. Transmettez-le à l&apos;utilisateur par un canal sûr.
      </p>
    </Modal>
  );
}
