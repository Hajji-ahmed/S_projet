import { ArrowRight, Landmark, Pencil, Power, PowerOff } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { currencySuffix, formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import type { Bank } from "@/types/bank";

type BankCardProps = {
  bank: Bank;
  /** Boutons d'action affichés seulement avec la permission banks.manage. */
  canManage: boolean;
  onEdit: (bank: Bank) => void;
  onToggleStatus: (bank: Bank) => void;
};

/** Montant en DH, « - » s'il est inconnu, en rouge s'il est négatif (découvert, dépassement). */
function Amount({ value, emphasis }: { value: string | null; emphasis?: "success" | "primary" }) {
  const negative = value !== null && value.startsWith("-");
  return (
    <span
      className={cn(
        "tabular-nums",
        negative && "text-simtis-danger",
        !negative && emphasis === "success" && value !== null && "text-simtis-success",
        !negative && emphasis === "primary" && value !== null && "text-simtis-primary",
      )}
    >
      {formatAmount(value, "DH")}
    </span>
  );
}

/**
 * Carte d'une banque pour la société active. Les chiffres viennent de son compte courant MAD ; les
 * autres comptes (EUR, USD, DH convertible) sont listés à part, chacun dans sa devise.
 */
export function BankCard({ bank, canManage, onEdit, onToggleStatus }: BankCardProps) {
  const figures = bank.figures;

  return (
    <article
      aria-label={`Banque ${bank.code}`}
      className={cn(
        "flex flex-col rounded-[14px] border border-simtis-border bg-simtis-card p-5 shadow-simtis",
        !bank.actif && "bg-simtis-background",
      )}
    >
      <div className="flex items-start gap-4">
        <span
          className={cn(
            "grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-xl border border-simtis-border bg-simtis-card",
            !bank.actif && "opacity-60",
          )}
        >
          {bank.logo ? (
            <Image
              src={bank.logo}
              alt=""
              width={56}
              height={56}
              className="h-12 w-12 object-contain"
            />
          ) : (
            <Landmark className="h-6 w-6 text-simtis-primary" aria-hidden />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-base font-semibold text-simtis-text">{bank.nom}</h2>
          <p className="mt-0.5 text-sm text-simtis-muted">
            Code <span className="font-semibold text-simtis-text">{bank.code}</span>
            <span aria-hidden> · </span>
            {bank.nb_comptes_actifs} compte{bank.nb_comptes_actifs > 1 ? "s" : ""}
          </p>
        </div>
        <StatusBadge status={bank.actif ? "Actif" : "Inactif"} />
      </div>

      {figures ? (
        <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
          <div>
            <dt className="text-simtis-muted">Solde</dt>
            <dd className="mt-0.5 font-semibold text-simtis-text">
              <Amount value={figures.solde} />
            </dd>
          </div>
          <div>
            <dt className="text-simtis-muted">Crédit disponible</dt>
            <dd className="mt-0.5 font-semibold">
              <Amount value={figures.credit_disponible} emphasis="success" />
            </dd>
          </div>
          <div className="col-span-2">
            <dt className="text-simtis-muted">Position disponible</dt>
            <dd className="mt-0.5 text-lg font-semibold">
              <Amount value={figures.position_disponible} emphasis="primary" />
            </dd>
          </div>
        </dl>
      ) : (
        <p className="mt-5 text-sm text-simtis-muted">Aucun compte courant en MAD.</p>
      )}

      {bank.autres_comptes.length > 0 && (
        <ul className="mt-4 space-y-1 border-t border-simtis-border pt-3 text-sm">
          {bank.autres_comptes.map((other) => (
            <li key={`${other.devise}-${other.type_compte}`} className="flex justify-between gap-3">
              <span className="text-simtis-muted">
                {other.type_compte === "DH convertible" ? "DH convertible" : other.devise}
              </span>
              <span className="text-simtis-text tabular-nums">
                {formatAmount(other.solde, currencySuffix(other.devise))}
              </span>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-4 text-xs text-simtis-muted">
        {figures?.date_maj ? `Mis à jour le ${formatDate(figures.date_maj)}` : "Aucun solde saisi"}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-simtis-border pt-4">
        <Link
          href={`/banques/${bank.id}`}
          className="mr-auto flex items-center gap-1 text-sm font-medium text-simtis-primary hover:underline"
        >
          Voir le détail <ArrowRight className="h-4 w-4" aria-hidden />
        </Link>
        {canManage && (
          <>
            <Button variant="secondary" icon={Pencil} onClick={() => onEdit(bank)}>
              Modifier
            </Button>
            <Button
              variant="ghost"
              icon={bank.actif ? PowerOff : Power}
              onClick={() => onToggleStatus(bank)}
              aria-label={bank.actif ? `Désactiver ${bank.code}` : `Réactiver ${bank.code}`}
            >
              {bank.actif ? "Désactiver" : "Réactiver"}
            </Button>
          </>
        )}
      </div>
    </article>
  );
}
