"use client";

import { Ban, Link2, Shuffle } from "lucide-react";
import { useState } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { ScoreBadge } from "@/components/rapprochement/Score";
import { Button } from "@/components/ui/Button";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import {
  absolute,
  etatPanier,
  montantEcriture,
  sensBanque,
  sensSage,
  unite,
  uniteEcriture,
} from "@/lib/reconciliation";
import type { EcritureAmbigue } from "@/types/reconciliation";

/**
 * Écriture ambiguë (15/10/2026) : le moteur a trouvé plusieurs opérations aussi proches et n'en a
 * proposé aucune. L'utilisateur coche la bonne (1 → 1), ou plusieurs dont la somme vaut l'écriture
 * (N → 1) ; ou déclare qu'aucune ne correspond.
 */
export function EcritureAmbigueCard({
  item,
  logo,
  seuilFort,
  canValidate,
  busy,
  onRapprocher,
  onAucune,
  selection,
}: {
  item: EcritureAmbigue;
  logo: string | null | undefined;
  seuilFort: string;
  canValidate: boolean;
  busy: boolean;
  /** Rapprochement manuel des opérations cochées avec l'écriture (validé d'emblée). */
  onRapprocher: (operationIds: number[]) => void;
  onAucune: () => void;
  /** Sélection pour « Aucune correspondance » en lot (15/10/2026). */
  selection?: { checked: boolean; onToggle: () => void };
}) {
  const { ecriture, candidats } = item;
  const [cochees, setCochees] = useState<typeof candidats>([]);
  const etat = etatPanier(
    cochees.map((c) => c.operation),
    [ecriture],
  );
  const devise = uniteEcriture(ecriture);

  return (
    <article
      aria-label={`Écriture ambiguë : ${ecriture.libelle}`}
      className="rounded-card border border-l-4 border-simtis-border border-l-simtis-warning bg-simtis-card p-4 shadow-simtis"
    >
      {selection && (
        <label className="mb-3 flex w-fit cursor-pointer items-center gap-2 text-xs font-medium text-simtis-muted">
          <input
            type="checkbox"
            checked={selection.checked}
            disabled={busy}
            onChange={selection.onToggle}
            className="h-4 w-4 accent-simtis-primary"
          />
          Sélectionner pour « Aucune correspondance »
        </label>
      )}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-simtis-warning-fg uppercase">
            <Shuffle className="h-3.5 w-3.5" aria-hidden />
            Écriture ambiguë : {candidats.length} opérations aussi proches
          </p>
          <p className="text-lg font-semibold text-simtis-primary-dark tabular-nums">
            {formatAmount(absolute(montantEcriture(ecriture)), devise)}{" "}
            <span className="text-sm font-normal text-simtis-muted">
              {sensSage(ecriture.montant)}
            </span>
          </p>
          <p className="font-medium">{ecriture.libelle}</p>
          <p className="flex flex-wrap items-center gap-x-3 text-xs text-simtis-muted">
            <span>{formatDate(ecriture.date_ecriture)}</span>
            {ecriture.journal && <span>Journal {ecriture.journal}</span>}
            {ecriture.numero_piece && <span>Pièce {ecriture.numero_piece}</span>}
          </p>
        </div>
        {canValidate && (
          <Button variant="secondary" icon={Ban} disabled={busy} onClick={onAucune}>
            Aucune opération ne correspond
          </Button>
        )}
      </div>

      <p className="mt-4 mb-2 text-xs font-semibold tracking-wide text-simtis-muted uppercase">
        Cochez l&apos;opération qui correspond, ou plusieurs dont la somme fait l&apos;écriture
      </p>
      <ul className="space-y-2">
        {candidats.map((candidat) => {
          const op = candidat.operation;
          const coche = cochees.some((c) => c.operation.id === op.id);
          return (
            <li key={op.id}>
              <label
                className={cn(
                  "flex cursor-pointer flex-wrap items-center gap-3 rounded-[12px] border px-3 py-2.5 transition-colors duration-150",
                  coche
                    ? "border-simtis-primary bg-simtis-light"
                    : "border-simtis-border bg-simtis-background hover:bg-simtis-light/40",
                )}
              >
                {canValidate && (
                  <input
                    type="checkbox"
                    checked={coche}
                    disabled={busy}
                    onChange={() =>
                      setCochees((liste) =>
                        liste.some((c) => c.operation.id === op.id)
                          ? liste.filter((c) => c.operation.id !== op.id)
                          : [...liste, candidat],
                      )
                    }
                    className="h-4 w-4 accent-simtis-primary"
                  />
                )}
                <span className="min-w-0 flex-1">
                  <span className="block text-sm">
                    <strong className="tabular-nums">
                      {formatAmount(absolute(op.montant), unite(op.devise))}
                    </strong>{" "}
                    <span className="text-xs text-simtis-muted">{sensBanque(op.montant)}</span>
                  </span>
                  <span className="block truncate text-sm" title={op.libelle}>
                    {op.libelle}
                  </span>
                  <span className="flex items-center gap-2 text-xs text-simtis-muted">
                    {formatDate(op.date_operation)}
                    <BankLabel code={op.bank_code} logo={logo} />
                    {op.reference && <span>Réf. {op.reference}</span>}
                  </span>
                </span>
                <ScoreBadge
                  score={candidat.score}
                  forte={Number(candidat.score) >= Number(seuilFort)}
                />
              </label>
            </li>
          );
        })}
      </ul>

      {canValidate && cochees.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-[12px] bg-simtis-background px-3 py-2.5 text-sm">
          <span>
            {cochees.length} opération{cochees.length > 1 ? "s" : ""} cochée
            {cochees.length > 1 ? "s" : ""} · écart{" "}
            <strong
              className={cn(
                "tabular-nums",
                etat.ecart === "0.00" ? "text-simtis-success-fg" : "text-simtis-danger-fg",
              )}
            >
              {formatAmount(absolute(etat.ecart), devise)}
            </strong>
          </span>
          <Button
            icon={Link2}
            disabled={busy || etat.blocage !== null}
            onClick={() => onRapprocher(cochees.map((c) => c.operation.id))}
          >
            Rapprocher ({cochees.length} → 1)
          </Button>
        </div>
      )}
    </article>
  );
}
