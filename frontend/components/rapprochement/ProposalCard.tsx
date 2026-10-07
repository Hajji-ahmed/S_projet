"use client";

import { ArrowLeftRight, Check, ExternalLink, TriangleAlert, X } from "lucide-react";
import type { ReactNode } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { ScoreBadge } from "@/components/rapprochement/Score";
import { Button } from "@/components/ui/Button";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import { absolute, ecartManuel, sensBanque, sensSage, validable } from "@/lib/reconciliation";
import type { Correspondance } from "@/types/reconciliation";

type ProposalCardProps = {
  item: Correspondance;
  logo: string | null | undefined;
  checked: boolean;
  canValidate: boolean;
  canSignal: boolean;
  busy: boolean;
  onToggle: () => void;
  onValidate: () => void;
  onReject: () => void;
  onSignal: () => void;
  /** Ouvre l'opération dans l'onglet Rapprochement (choisir une autre écriture). */
  onOpen: () => void;
};

/**
 * Une proposition en grand : transaction bancaire à gauche, écriture comptable à droite, score et
 * critères au centre. Une proposition dont les montants diffèrent ne se coche ni ne se valide :
 * elle se signale comme écart.
 */
export function ProposalCard({
  item,
  logo,
  checked,
  canValidate,
  canSignal,
  busy,
  onToggle,
  onValidate,
  onReject,
  onSignal,
  onOpen,
}: ProposalCardProps) {
  const ok = validable(item);
  const ecart = ecartManuel(item.operation.montant, item.ecriture.montant);
  const checkboxId = `proposition-${item.id}`;

  return (
    <article
      aria-label={`Proposition : ${item.operation.libelle} et ${item.ecriture.libelle}`}
      className={cn(
        "rounded-[14px] border bg-simtis-card p-4 shadow-simtis transition-colors duration-200",
        checked ? "border-simtis-primary bg-simtis-light/40" : "border-simtis-border",
      )}
    >
      <div className="grid gap-4 lg:grid-cols-[auto_minmax(0,1fr)_200px_minmax(0,1fr)] lg:items-center">
        <div className="flex items-center lg:self-stretch">
          {canValidate && (
            <input
              id={checkboxId}
              type="checkbox"
              checked={checked}
              disabled={!ok || busy}
              onChange={onToggle}
              aria-label={`Sélectionner la proposition ${item.operation.libelle}`}
              className="h-5 w-5 cursor-pointer accent-simtis-primary disabled:cursor-not-allowed"
            />
          )}
        </div>

        <Side title="Transaction bancaire">
          <Amount value={item.operation.montant} sens={sensBanque(item.operation.montant)} />
          <p className="font-medium">{item.operation.libelle}</p>
          <p className="flex flex-wrap items-center gap-x-2 text-xs text-simtis-muted">
            <span>{formatDate(item.operation.date_operation)}</span>
            <BankLabel code={item.operation.bank_code} logo={logo} />
            {item.operation.reference && <span>Réf. {item.operation.reference}</span>}
          </p>
        </Side>

        <div className="flex flex-col items-center gap-2 text-center">
          <ArrowLeftRight className="hidden h-5 w-5 text-simtis-muted lg:block" aria-hidden />
          <div className="flex items-center gap-2">
            <ScoreBadge score={item.score} forte={item.forte} />
            <span className="text-xs text-simtis-muted">{item.forte ? "forte" : "à vérifier"}</span>
          </div>
          <ul className="flex flex-wrap justify-center gap-1" aria-label="Critères du score">
            {item.criteres.map((critere) => {
              const gained = Number(critere.points) > 0;
              return (
                <li
                  key={critere.code}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
                    gained
                      ? "bg-simtis-success-bg text-simtis-success-fg"
                      : "bg-simtis-neutral-bg text-simtis-neutral-fg",
                  )}
                >
                  {gained ? (
                    <Check className="h-3 w-3" aria-hidden />
                  ) : (
                    <X className="h-3 w-3" aria-hidden />
                  )}
                  {critere.libelle}
                  <span className="sr-only">{gained ? " obtenu" : " non obtenu"}</span>
                </li>
              );
            })}
          </ul>
        </div>

        <Side title="Écriture comptable">
          <Amount value={item.ecriture.montant} sens={sensSage(item.ecriture.montant)} />
          <p className="font-medium">{item.ecriture.libelle}</p>
          <p className="flex flex-wrap gap-x-2 text-xs text-simtis-muted">
            <span>{formatDate(item.ecriture.date_ecriture)}</span>
            {item.ecriture.journal && <span>Journal {item.ecriture.journal}</span>}
            {item.ecriture.numero_piece && <span>Pièce {item.ecriture.numero_piece}</span>}
            {item.ecriture.tiers && <span>{item.ecriture.tiers}</span>}
          </p>
        </Side>
      </div>

      {!ok && (
        <p className="mt-3 flex items-center gap-2 rounded-[10px] bg-simtis-orange-bg px-3 py-2 text-sm text-simtis-orange-fg">
          <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden />
          Montant différent : écart de {formatAmount(absolute(ecart), "DH")}. Cette proposition ne
          peut pas être validée.
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center justify-end gap-2 border-t border-simtis-border pt-3">
        <Button variant="ghost" icon={ExternalLink} disabled={busy} onClick={onOpen}>
          Ouvrir dans le rapprochement
        </Button>
        {canValidate && (
          <Button variant="secondary" icon={X} disabled={busy} onClick={onReject}>
            Rejeter
          </Button>
        )}
        {ok
          ? canValidate && (
              <Button icon={Check} disabled={busy} onClick={onValidate}>
                Valider
              </Button>
            )
          : canSignal && (
              <Button icon={TriangleAlert} disabled={busy} onClick={onSignal}>
                Signaler un écart
              </Button>
            )}
      </div>
    </article>
  );
}

function Side({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-1 rounded-[12px] border border-simtis-border bg-simtis-background p-3 text-sm">
      <p className="text-xs font-semibold tracking-wide text-simtis-muted uppercase">{title}</p>
      {children}
    </div>
  );
}

function Amount({ value, sens }: { value: string; sens: string }) {
  return (
    <p className="text-[22px] leading-tight font-bold text-simtis-primary-dark tabular-nums">
      {formatAmount(absolute(value), "DH")}{" "}
      <span className="text-xs font-normal text-simtis-muted lowercase">{sens}</span>
    </p>
  );
}
