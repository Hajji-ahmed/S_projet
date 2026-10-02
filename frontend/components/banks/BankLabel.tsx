import Image from "next/image";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type BankLabelProps = {
  /** Code affiché (AWB, BMCE...) : c'est lui que lisent le classeur et les lecteurs d'écran. */
  code: string;
  /** Chemin d'un fichier de `public/banques/`, ou null : le code s'affiche alors seul. */
  logo: string | null | undefined;
  /** « inline » : logo puis texte (tableaux) ; « stacked » : logo au-dessus du code (en-têtes de colonnes). */
  layout?: "inline" | "stacked";
  /** Texte affiché à la place du code seul (ex. « CIH · MAD »). */
  children?: ReactNode;
  className?: string;
};

/** Logo d'une banque à côté de son code, partout où un tableau nomme une banque. */
export function BankLabel({ code, logo, layout = "inline", children, className }: BankLabelProps) {
  const stacked = layout === "stacked";
  return (
    <span
      className={cn(
        stacked
          ? "inline-flex flex-col items-center gap-1"
          : "inline-flex items-center gap-2 whitespace-nowrap",
        className,
      )}
    >
      {logo && (
        <span
          className="grid h-6 w-6 shrink-0 place-items-center overflow-hidden rounded-md border border-simtis-border bg-simtis-card"
          data-bank-logo={code}
        >
          {/* Décoratif : le code écrit à côté nomme déjà la banque */}
          <Image src={logo} alt="" width={20} height={20} className="h-5 w-5 object-contain" />
        </span>
      )}
      <span>{children ?? code}</span>
    </span>
  );
}

/** Code de banque → logo, à partir de la liste des banques déjà chargée. */
export function logosByCode(banks: readonly { code: string; logo: string | null }[]) {
  return new Map(banks.map((bank) => [bank.code, bank.logo]));
}
