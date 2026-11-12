import { toCents } from "@/lib/statementLines";

// Filtres du relevé par compte dans les en-têtes de colonnes, comme dans Excel (12/11/2026). Le
// filtre Date recharge la période depuis l'API ; ceux-ci s'appliquent aux opérations déjà chargées.

/** Champs d'une opération lus par les filtres. */
export type LigneFiltrable = {
  id: number;
  libelle: string;
  reference: string | null;
  /** Null : pointage pas encore choisi (« À choisir »). */
  pointage: string | null;
  debit: string;
  credit: string;
  statut: string;
};

export type SensMontant = "" | "Débit" | "Crédit";
export type StatutFiltre = "" | "Rapprochée" | "Non rapprochée";

export type FiltresReleve = {
  /** Pointages cochés (null = « À choisir ») ; vide = tous. */
  pointages: (string | null)[];
  /** Recherche dans le libellé et la référence. */
  q: string;
  /** Débit, Crédit ou les deux (vide). */
  sens: SensMontant;
  /** Montants normalisés (« 12500.50 ») ; vide = pas de borne. L'exact l'emporte sur min / max. */
  exact: string;
  min: string;
  max: string;
  statut: StatutFiltre;
};

export const FILTRES_RELEVE_VIDES: FiltresReleve = {
  pointages: [],
  q: "",
  sens: "",
  exact: "",
  min: "",
  max: "",
  statut: "",
};

export const LIBELLE_A_CHOISIR = "À choisir";

const ZERO = BigInt(0);

/** Minuscules, sans accents : « Société » et « SOCIETE » se retrouvent. */
function normaliser(texte: string): string {
  return texte.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

function absolu(cents: bigint): bigint {
  return cents < ZERO ? -cents : cents;
}

/** Montant de la ligne dans le sens demandé, en centimes ; null si elle n'a pas ce sens. */
function montantLigne(ligne: LigneFiltrable, sens: SensMontant): bigint | null {
  const debit = absolu(toCents(ligne.debit));
  const credit = absolu(toCents(ligne.credit));
  if (sens === "Débit") return debit !== ZERO ? debit : null;
  if (sens === "Crédit") return credit !== ZERO ? credit : null;
  return debit !== ZERO ? debit : credit;
}

function montantFiltre(filtres: FiltresReleve): boolean {
  return !!(filtres.sens || filtres.exact || filtres.min || filtres.max);
}

function garderMontant(ligne: LigneFiltrable, filtres: FiltresReleve): boolean {
  if (!montantFiltre(filtres)) return true;
  const montant = montantLigne(ligne, filtres.sens);
  if (montant === null) return false;
  if (filtres.exact) return montant === toCents(filtres.exact);
  if (filtres.min && montant < toCents(filtres.min)) return false;
  if (filtres.max && montant > toCents(filtres.max)) return false;
  return true;
}

/** « Non rapprochée » couvre aussi « À vérifier » : une ligne en proposition reste non rapprochée
 * tant que le rapprochement n'est pas validé. */
function garderStatut(statut: string, filtre: StatutFiltre): boolean {
  if (!filtre) return true;
  if (filtre === "Non rapprochée") return statut === "Non rapprochée" || statut === "À vérifier";
  return statut === filtre;
}

export function filtrerOperations<T extends LigneFiltrable>(
  lignes: readonly T[],
  filtres: FiltresReleve,
): T[] {
  const q = normaliser(filtres.q.trim());
  return lignes.filter(
    (ligne) =>
      (filtres.pointages.length === 0 || filtres.pointages.includes(ligne.pointage)) &&
      (!q || normaliser(`${ligne.libelle} ${ligne.reference ?? ""}`).includes(q)) &&
      garderMontant(ligne, filtres) &&
      garderStatut(ligne.statut, filtres.statut),
  );
}

/** Choix du filtre Pointage : « À choisir » d'abord s'il y en a, puis les pointages présents. */
export function optionsPointage(lignes: readonly LigneFiltrable[]): (string | null)[] {
  const presents = new Set<string>();
  let aChoisir = false;
  for (const ligne of lignes) {
    if (ligne.pointage === null) aChoisir = true;
    else presents.add(ligne.pointage);
  }
  const tries = [...presents].sort((a, b) => a.localeCompare(b, "fr"));
  return aChoisir ? [null, ...tries] : tries;
}

/** Colonnes dont l'entonnoir est allumé (la Date suit la période du relevé). */
export function colonnesFiltreesReleve(filtres: FiltresReleve) {
  const montant = montantFiltre(filtres);
  return {
    pointage: filtres.pointages.length > 0,
    libelle: !!filtres.q.trim(),
    debit: montant && filtres.sens !== "Crédit",
    credit: montant && filtres.sens !== "Débit",
    statut: !!filtres.statut,
  };
}

export function filtresReleveActifs(filtres: FiltresReleve): boolean {
  return Object.values(colonnesFiltreesReleve(filtres)).some(Boolean);
}
