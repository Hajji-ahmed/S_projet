import { Landmark, Pencil, Power, PowerOff } from "lucide-react";
import Image from "next/image";

import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { cn } from "@/lib/cn";
import type { Bank } from "@/types/bank";

type BankCardProps = {
  bank: Bank;
  /** Boutons d'action affichés seulement avec la permission banks.manage. */
  canManage: boolean;
  onEdit: (bank: Bank) => void;
  onToggleStatus: (bank: Bank) => void;
};

/** Carte du référentiel. Le solde, le crédit et la position disponibles s'y ajouteront en P6.3. */
export function BankCard({ bank, canManage, onEdit, onToggleStatus }: BankCardProps) {
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
          </p>
        </div>
        <StatusBadge status={bank.actif ? "Actif" : "Inactif"} />
      </div>

      <dl className="mt-5 grid grid-cols-2 gap-4 text-sm">
        <div>
          <dt className="text-simtis-muted">Comptes actifs</dt>
          <dd className="mt-0.5 text-lg font-semibold text-simtis-text tabular-nums">
            {bank.nb_comptes_actifs}
          </dd>
        </div>
        <div>
          <dt className="text-simtis-muted">Ordre d&apos;affichage</dt>
          <dd className="mt-0.5 text-lg font-semibold text-simtis-text tabular-nums">
            {bank.ordre_affichage}
          </dd>
        </div>
      </dl>

      {canManage && (
        <div className="mt-5 flex flex-wrap gap-2 border-t border-simtis-border pt-4">
          <Button variant="secondary" icon={Pencil} onClick={() => onEdit(bank)}>
            Modifier
          </Button>
          <Button
            variant="ghost"
            icon={bank.actif ? PowerOff : Power}
            onClick={() => onToggleStatus(bank)}
          >
            {bank.actif ? "Désactiver" : "Réactiver"}
          </Button>
        </div>
      )}
    </article>
  );
}
