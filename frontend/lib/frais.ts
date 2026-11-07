import { fromCents, toCents } from "@/lib/statementLines";
import type { CompteFrais, LigneGL, LigneSaisie, PropositionTimbres } from "@/types/frais";

/** Identifiant d'une écriture proposée : sa famille, un compte et un jour. */
export function cleJour(
  item: Pick<PropositionTimbres, "famille" | "bank_account_id" | "date">,
): string {
  return `${item.famille}|${item.bank_account_id}|${item.date}`;
}

/** Nombre de jours cochés et leur total exact (centimes en BigInt, jamais de float). */
export function selectionTimbres(
  propositions: PropositionTimbres[],
  selection: Set<string>,
): { nb: number; total: string } {
  let total = BigInt(0);
  let nb = 0;
  for (const item of propositions) {
    if (!selection.has(cleJour(item))) continue;
    nb += 1;
    total += toCents(item.total);
  }
  return { nb, total: fromCents(total) };
}

/** Libellés proposés pour une écriture saisie à la main (saisie libre). */
export const LIBELLES_SUGGERES = [
  "AGIOS",
  "COM",
  "FRAIS",
  "FRAIS D'ESCOMPTE",
  "FRAIS DE REFINANCEMENT",
  "INTERET CREDOC",
  "INTERETS DEBITEURS",
];

/** Libellés proposés : les libellés usuels puis les intitulés des comptes de frais (05/11/2026). */
export function suggestionsLibelles(comptes: CompteFrais[]): string[] {
  return [...new Set([...LIBELLES_SUGGERES, ...comptes.map((compte) => compte.intitule)])];
}

/** Comptes de frais proposés pour un compte de cette banque : un compte réservé (63119710 « CMT
 * BP ») ne l'est que pour sa banque. */
export function comptesDeLaBanque(comptes: CompteFrais[], banque: string): CompteFrais[] {
  return comptes.filter((compte) => compte.banque === null || compte.banque === banque);
}

/** « Intérêts crédit affacturage » → « INTERET CREDIT AFFACTURAGE » : comme le serveur, sans
 * accents ni ponctuation, INTERETS = INTERET. */
function cleIntitule(texte: string): string {
  return texte
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, " ")
    .trim()
    .split(/\s+/)
    .map((mot) => (mot === "INTERETS" ? "INTERET" : mot))
    .join(" ");
}

/**
 * Compte de frais que le serveur donne à ce libellé (`frais_service.compte_charge`, 05/11/2026) :
 * AGIOS → celui de la banque, sinon l'intitulé le plus long qui commence le libellé ; null sinon
 * (le serveur garde alors COM 61714000 ou les frais bancaires 61473000).
 */
export function compteDuLibelle(
  libelle: string,
  banque: string,
  comptes: CompteFrais[],
): string | null {
  const texte = cleIntitule(libelle);
  const candidats = comptesDeLaBanque(comptes, banque);
  if (texte.split(" ")[0] === "AGIOS")
    return (
      candidats.find((compte) => compte.banque === banque && compte.intitule.startsWith("AGIOS"))
        ?.numero ?? null
    );
  let trouve: { longueur: number; numero: string } | null = null;
  for (const compte of candidats) {
    const cle = cleIntitule(compte.intitule);
    if (
      cle &&
      (texte === cle || texte.startsWith(`${cle} `)) &&
      cle.length > (trouve?.longueur ?? -1)
    )
      trouve = { longueur: cle.length, numero: compte.numero };
  }
  return trouve?.numero ?? null;
}

/** Compte des commissions (COM) et des autres frais bancaires (16/10/2026). */
export const COMPTE_COMMISSION = "61714000";
export const COMPTE_FRAIS_BANCAIRES = "61473000";
/** Valeur du choix « Autre… » de la liste des comptes de charge (07/11/2026). */
export const AUTRE_COMPTE = "autre";

/** Compte de charge que SIMTIS prend sans choix (07/11/2026), comme le serveur
 * (`frais_service.compte_charge`) : AGIOS selon la banque, puis l'intitulé d'un compte de la liste,
 * puis COM / COMMISSION → 61714000, sinon 61473000. "" : AGIOS d'une banque sans compte d'agios. */
export function compteParDefaut(libelle: string, banque: string, comptes: CompteFrais[]): string {
  const premier = cleIntitule(libelle).split(" ")[0];
  const duLibelle = compteDuLibelle(libelle, banque, comptes);
  if (premier === "AGIOS") return duLibelle ?? "";
  if (duLibelle) return duLibelle;
  return ["COM", "COMMISSION", "COMMISSIONS"].includes(premier)
    ? COMPTE_COMMISSION
    : COMPTE_FRAIS_BANCAIRES;
}

/** Compte saisi à la main (« Autre », 07/11/2026) : 4 à 20 chiffres, comme le serveur. */
export function compteValide(compte: string): boolean {
  return /^\d{4,20}$/.test(compte.trim());
}

/** Somme exacte (signée) des montants, en texte « -165.00 ». */
export function sommeMontants(montants: string[]): string {
  return fromCents(montants.reduce((total, montant) => total + toCents(montant), BigInt(0)));
}

/**
 * (Frais HT, TVA) d'un total TTC positif, comme le serveur : HT = total ÷ (1 + taux), arrondi au
 * centime le plus proche (0,5 vers le haut) ; TVA = total − HT. Taux en %, « 10 » ou « 7,5 ».
 * Null si le taux n'est pas un nombre positif de 2 décimales au plus.
 */
export function ventilerTva(total: string, taux: string): { ht: string; tva: string } | null {
  const valeur = taux.trim().replace(",", ".");
  if (!/^\d{1,3}(\.\d{1,2})?$/.test(valeur)) return null;
  const centiemes = toCents(valeur); // 10 % → 1000
  if (centiemes <= BigInt(0) || centiemes > BigInt(10000)) return null;
  const ttc = toCents(total);
  const base = BigInt(10000);
  const denominateur = base + centiemes;
  const ht = (BigInt(2) * ttc * base + denominateur) / (BigInt(2) * denominateur);
  return { ht: fromCents(ht), tva: fromCents(ttc - ht) };
}

/** Lignes d'une proposition, modifiables (19/10/2026) : montant positif et son sens. */
export function lignesSaisies(lignes: LigneGL[]): LigneSaisie[] {
  return lignes.map((ligne) => ({
    compte: ligne.compte ?? "",
    libelle: ligne.libelle,
    montant: ligne.credit ?? ligne.debit ?? "0.00",
    sens: ligne.credit ? "Crédit" : "Débit",
  }));
}

/**
 * Contrôle des lignes saisies, comme le serveur : chacune a un compte, un libellé et un montant
 * positif, et crédits − débits = total des opérations. `ecart` = total − lignes, en texte exact.
 */
export function etatLignes(
  lignes: LigneSaisie[],
  total: string,
): { somme: string; ecart: string; erreur: string | null } {
  let somme = BigInt(0);
  let erreur: string | null = null;
  if (lignes.length === 0) erreur = "L'écriture doit garder au moins une ligne.";
  for (const ligne of lignes) {
    const montant = /^\d+(\.\d{1,2})?$/.test(ligne.montant) ? toCents(ligne.montant) : null;
    if (!ligne.compte.trim()) erreur ??= "Chaque ligne a un N° compte général.";
    else if (ligne.compte.replace(/\s/g, "").length > 20)
      erreur ??= "Un N° compte général a 20 caractères au plus.";
    if (!ligne.libelle.trim()) erreur ??= "Chaque ligne a un libellé.";
    else if (ligne.libelle.trim().length > 60) erreur ??= "Un libellé a 60 caractères au plus.";
    if (montant === null || montant <= BigInt(0)) {
      erreur ??= "Chaque montant est positif, au centime près.";
      continue;
    }
    somme += ligne.sens === "Crédit" ? montant : -montant;
  }
  const ecart = toCents(total) - somme;
  if (!erreur && ecart !== BigInt(0))
    erreur = "Le total des lignes doit être égal à la somme des opérations.";
  return { somme: fromCents(somme), ecart: fromCents(ecart), erreur };
}

/** Libellé d'une ligne quand seul le libellé de l'écriture change : « TVA … » pour la TVA. */
export function libelleModifie(ligne: LigneGL, libelleOrigine: string, libelle: string): string {
  return ligne.libelle === `TVA ${libelleOrigine}` ? `TVA ${libelle}` : libelle;
}
