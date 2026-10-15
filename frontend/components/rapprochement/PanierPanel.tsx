"use client";

import { Layers, Link2, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
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
 */
export function PanierPanel({
  operations,
  ecritures,
  canValidate,
  onRetirerOperation,
  onRetirerEcriture,
  onVider,
  onDone,
}: {
  operations: Operation[];
  ecritures: Ecriture[];
  canValidate: boolean;
  onRetirerOperation: (operation: Operation) => void;
  onRetirerEcriture: (ecriture: Ecriture) => void;
  onVider: () => void;
  onDone: (message: string) => void;
}) {
  const { toast } = useToast();
  const [commentaire, setCommentaire] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const etat = etatPanier(operations, ecritures);
  const devise = unite(etat.devise);

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
    <Card title="Plusieurs lignes" icon={Layers}>
      <p className="mb-4 text-xs text-simtis-muted">
        Cochez des opérations à gauche et des écritures à droite : 1 → N, N → 1 ou N → N. Les totaux
        doivent se compenser exactement, sur un seul compte.
      </p>

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
        total={etat.totalBanque}
        unite={devise}
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
        total={etat.totalSage}
        unite={devise}
      />

      <div
        className={cn(
          "mt-4 flex items-center justify-between rounded-[10px] px-3 py-2.5 text-sm",
          etat.blocage === null
            ? "bg-simtis-success-bg text-simtis-success-fg"
            : "bg-simtis-background text-simtis-text",
        )}
      >
        <span className="font-medium">
          Écart{" "}
          <span className="ml-1 rounded-full bg-simtis-card px-2 py-0.5 text-xs text-simtis-muted">
            {etat.type}
          </span>
        </span>
        <span className="font-semibold tabular-nums">
          {formatAmount(absolute(etat.ecart), devise)}
        </span>
      </div>
      {etat.blocage && (
        <p className="mt-2 text-xs text-simtis-muted">
          {etat.blocage === "ecart"
            ? `Les totaux ne se compensent pas : écart de ${formatAmount(absolute(etat.ecart), devise)}.`
            : MESSAGES[etat.blocage]}
        </p>
      )}

      {canValidate && (
        <div className="mt-4 space-y-3">
          <Field label="Commentaire" htmlFor="panier-commentaire">
            <TextInput
              id="panier-commentaire"
              value={commentaire}
              maxLength={500}
              placeholder="Facultatif"
              onChange={(event) => setCommentaire(event.target.value)}
            />
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button
              icon={Link2}
              onClick={rapprocher}
              disabled={envoi || etat.blocage !== null}
              className="flex-1 justify-center"
            >
              {envoi
                ? "Rapprochement..."
                : `Rapprocher (${operations.length} → ${ecritures.length})`}
            </Button>
            <Button
              variant="secondary"
              onClick={onVider}
              disabled={envoi || operations.length + ecritures.length === 0}
            >
              Vider
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

function Cote({
  titre,
  vide,
  lignes,
  total,
  unite: uniteTotal,
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
  total: string;
  unite: string;
}) {
  return (
    <section className="mt-3 first-of-type:mt-0">
      <div className="mb-1.5 flex items-center justify-between text-xs font-semibold text-simtis-primary-dark">
        <span>
          {titre} ({lignes.length})
        </span>
        <span className="tabular-nums">{formatAmount(total, uniteTotal)}</span>
      </div>
      {lignes.length === 0 ? (
        <p className="rounded-[10px] border border-dashed border-simtis-border px-3 py-2 text-xs text-simtis-muted">
          {vide}
        </p>
      ) : (
        <ul className="max-h-[180px] divide-y divide-simtis-border overflow-y-auto rounded-[10px] border border-simtis-border">
          {lignes.map((ligne) => (
            <li key={ligne.id} className="flex items-center gap-2 px-2.5 py-1.5 text-xs">
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
