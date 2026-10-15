import { BankLabel } from "@/components/banks/BankLabel";
import { cn } from "@/lib/cn";
import type { Account } from "@/types/account";

/**
 * Libellé d'un compte dans les boutons de choix de compte (Écritures, Rapprochement) : logo,
 * « AWB · 5043 » (banque · journal Sage) et la devise du compte, pour distinguer AWB MAD, EUR et
 * USD d'un coup d'œil.
 */
export function AccountChipLabel({ account }: { account: Account }) {
  return (
    <span className="inline-flex items-center gap-2">
      <BankLabel code={account.bank_code} logo={account.bank_logo}>
        {account.bank_code} · {account.journal_sage}
      </BankLabel>
      <span
        className={cn(
          "rounded-full px-1.5 py-0.5 text-[11px] leading-none font-semibold",
          account.devise === "MAD"
            ? "bg-simtis-neutral-bg text-simtis-neutral-fg"
            : "bg-simtis-info-bg text-simtis-info-fg",
        )}
      >
        {account.devise}
      </span>
    </span>
  );
}
