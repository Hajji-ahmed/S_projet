"use client";

import { ChevronDown, ChevronUp, Layers, Link2, Maximize2, Minimize2, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/Field";
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import {
  MANUEL_MAX,
  absolute,
  etatPanier,
  montantEcriture,
  unite,
  type BlocagePanier,
} from "@/lib/reconciliation";
import { matchGroupe } from "@/services/reconciliation";
import type { Ecriture } from "@/types/accounting";
import type { Operation } from "@/types/reconciliation";

const MESSAGES: Record<Exclude<BlocagePanier, "ecart" | null>, string> = {
  vide: "Cochez au moins une opération bancaire et une écriture comptable.",
  limite: `Au plus ${MANUEL_MAX} lignes de chaque côté.`,
  comptes: "Les lignes choisies sont sur plusieurs comptes bancaires.",
  rapprochee: "Une ligne choisie est déjà rapprochée.",
};

/**
 * Panier du rapprochement manuel de plusieurs lignes (P13, 15/10/2026) : opérations et écritures
 * cochées dans les volets, leurs totaux et l'écart (centimes exacts). « Rapprocher » n'est actif
 * que lorsque les totaux se compensent sur un seul compte ; l'API vérifie tout de nouveau.
 * Depuis le 28/10/2026 c'est un bandeau d'une ligne au-dessus des volets, toujours affiché (les
 * lignes se cochent toujours, 1 → 1 compris) ; « Détail » déplie les lignes cochées.
 */
export function PanierPanel({
  operations,
  ecritures,
  canValidate,
  onRetirerOperation,
  onRetirerEcriture,
  onVider,
  onDone,
  pleinEcran,
  onPleinEcran,
}: {
  operations: Operation[];
  ecritures: Ecriture[];
  canValidate: boolean;
  onRetirerOperation: (operation: Operation) => void;
  onRetirerEcriture: (ecriture: Ecriture) => void;
  onVider: () => void;
  onDone: (message: string) => void;
  /** Plein écran du rapprochement (29/10/2026) : bouton au bout du bandeau. */
  pleinEcran?: boolean;
  onPleinEcran?: () => void;
}) {
  const { toast } = useToast();
  const [commentaire, setCommentaire] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [detail, setDetail] = useState(false);
  const etat = etatPanier(operations, ecritures);
  const devise = unite(etat.devise);
  const message =
    etat.blocage === "ecart"
      ? "Les totaux ne se compensent pas."
      : etat.blocage
        ? MESSAGES[etat.blocage]
        : null;

  async function rapprocher() {
    setEnvoi(true);
    try {
      const resultat = await matchGroupe(
        operations.map((op) => op.id),
        ecritures.map((e) => e.id),
        commentaire,
      );
      setCommentaire("");
      onDone(`Rapprochement ${resultat.code ?? ""} (${resultat.type}) validé.`);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Rapprochement impossible.", "error");
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <section
      aria-label="Correspondance"
      className="rounded-card border border-simtis-border bg-simtis-card shadow-simtis"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2 text-sm">
        <span className="flex items-center gap-2 font-semibold text-simtis-primary-dark">
          <Layers className="h-4 w-4 text-simtis-primary" aria-hidden />
          Correspondance
        </span>
        <Total
          label="Banque"
          nombre={operations.length}
          montant={formatAmount(etat.totalBanque, devise)}
        />
        <Total
          label="Sage"
          nombre={ecritures.length}
          montant={formatAmount(etat.totalSage, devise)}
        />
        <span
          className={cn(
            "inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium tabular-nums",
            etat.blocage === null
              ? "bg-simtis-success-bg text-simtis-success-fg"
              : "bg-simtis-background text-simtis-text",
          )}
        >
          Écart {formatAmount(absolute(etat.ecart), devise)}
          <span className="rounded-full bg-simtis-card px-1.5 text-simtis-muted">{etat.type}</span>
        </span>
        {message && (
          <span className="min-w-0 flex-1 truncate text-xs text-simtis-muted" title={message}>
            {message}
          </span>
        )}

        <div className="ml-auto flex flex-wrap items-center gap-2">
          {canValidate && (
            <TextInput
              id="panier-commentaire"
              aria-label="Commentaire du rapprochement"
              value={commentaire}
              maxLength={500}
              placeholder="Commentaire (facultatif)"
              onChange={(event) => setCommentaire(event.target.value)}
              className="h-8 w-56 text-xs"
            />
          )}
          <Button
            variant="ghost"
            icon={detail ? ChevronUp : ChevronDown}
            aria-expanded={detail}
            onClick={() => setDetail((ouvert) => !ouvert)}
            className="h-8 px-2"
          >
            Détail
          </Button>
          <Button
            variant="secondary"
            onClick={onVider}
            disabled={envoi || operations.length + ecritures.length === 0}
            className="h-8 px-3"
          >
            Vider
          </Button>
          {canValidate && (
            <Button
              icon={Link2}
              onClick={rapprocher}
              disabled={envoi || etat.blocage !== null}
              className="h-8 px-3"
            >
              {envoi
                ? "Rapprochement..."
                : `Rapprocher (${operations.length} → ${ecritures.length})`}
            </Button>
          )}
          {onPleinEcran && (
            <Button
              variant="secondary"
              icon={pleinEcran ? Minimize2 : Maximize2}
              onClick={onPleinEcran}
              className="h-8 w-8 justify-center px-0"
              aria-label={pleinEcran ? "Quitter le plein écran" : "Plein écran"}
              title={
                pleinEcran
                  ? "Quitter le plein écran (Échap)"
                  : "Plein écran : masque le menu, l'en-tête et les compteurs"
              }
            />
          )}
        </div>
      </div>
      {detail && (
        <div className="grid gap-3 border-t border-simtis-border px-4 py-3 md:grid-cols-2">
          <Cote
            titre="Opérations bancaires"
            vide="Aucune opération cochée."
            lignes={operations.map((op) => ({
              id: op.id,
              date: op.date_operation,
              libelle: op.libelle,
              montant: op.montant,
              unite: unite(op.devise),
              retirer: () => onRetirerOperation(op),
            }))}
          />
          <Cote
            titre="Écritures comptables"
            vide="Aucune écriture cochée."
            lignes={ecritures.map((e) => ({
              id: e.id,
              date: e.date_ecriture,
              libelle: e.libelle,
              montant: montantEcriture(e),
              unite: unite(e.devise),
              retirer: () => onRetirerEcriture(e),
            }))}
          />
        </div>
      )}
    </section>
  );
}

function Total({ label, nombre, montant }: { label: string; nombre: number; montant: string }) {
  return (
    <span className="whitespace-nowrap">
      <span className="text-simtis-muted">
        {label} ({nombre})
      </span>{" "}
      <span className="font-semibold tabular-nums">{montant}</span>
    </span>
  );
}

function Cote({
  titre,
  vide,
  lignes,
}: {
  titre: string;
  vide: string;
  lignes: {
    id: number;
    date: string;
    libelle: string;
    montant: string;
    unite: string;
    retirer: () => void;
  }[];
}) {
  return (
    <section>
      <p className="mb-1.5 text-xs font-semibold text-simtis-primary-dark">
        {titre} ({lignes.length})
      </p>
      {lignes.length === 0 ? (
        <p className="rounded-[10px] border border-dashed border-simtis-border px-3 py-2 text-xs text-simtis-muted">
          {vide}
        </p>
      ) : (
        <ul className="max-h-[160px] divide-y divide-simtis-border overflow-y-auto rounded-[10px] border border-simtis-border">
          {lignes.map((ligne) => (
            <li key={ligne.id} className="flex items-center gap-2 px-2.5 py-1 text-xs">
              <span className="w-[70px] shrink-0 text-simtis-muted tabular-nums">
                {formatDate(ligne.date)}
              </span>
              <span className="min-w-0 flex-1 truncate" title={ligne.libelle}>
                {ligne.libelle}
              </span>
              <span className="shrink-0 font-medium whitespace-nowrap tabular-nums">
                {formatAmount(ligne.montant, ligne.unite)}
              </span>
              <button
                type="button"
                onClick={ligne.retirer}
                aria-label={`Retirer ${ligne.libelle}`}
                className="rounded-md p-0.5 text-simtis-muted hover:bg-simtis-danger-bg hover:text-simtis-danger-fg"
              >
                <X className="h-3.5 w-3.5" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
