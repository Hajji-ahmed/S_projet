/**
 * Aperçu modifiable d'un relevé : brouillons de lignes, revérification (mêmes règles que
 * `backend/app/services/import_service._read_line`) et résumé. Les montants restent du TEXTE ;
 * les sommes se font en centimes `BigInt`, jamais en nombre à virgule flottante.
 */
import { normalizeAmountInput } from "@/lib/accounts";
import { normalizeSignedAmountInput } from "@/lib/balances";
import type { AnalysedLine, LigneSoumise } from "@/types/statement";

/** Une ligne du fichier telle qu'elle est saisie dans l'aperçu (« » = vide). */
export type LineDraft = {
  numero: number;
  date_operation: string;
  date_valeur: string;
  libelle: string;
  reference: string;
  debit: string;
  credit: string;
  solde: string;
  pointage_type_id: number | null;
  lettrage_escompte: string;
  commentaire: string;
};

export type DraftSummary = {
  count: number;
  totalDebit: string;
  totalCredit: string;
  periodeDebut: string | null;
  periodeFin: string | null;
  ouverture: string | null;
  cloture: string | null;
  coherent: boolean | null;
};

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const LETTRAGE_MAX = 120;
// Pas de littéral « 100n » : la cible TypeScript du projet est antérieure à ES2020
const ZERO = BigInt(0);
const HUNDRED = BigInt(100);

/** « 12500.50 » → « 12 500,50 » ; décimales nulles retirées ; uniquement des chaînes. */
export function amountToInput(value: string | null): string {
  if (value === null) return "";
  const negative = value.startsWith("-");
  const [whole, decimals = ""] = (negative ? value.slice(1) : value).split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const cents = decimals.padEnd(2, "0").slice(0, 2);
  return `${negative ? "-" : ""}${grouped}${cents === "00" ? "" : `,${cents}`}`;
}

export function draftFromLine(line: AnalysedLine): LineDraft {
  const amount = (value: string | null) =>
    value === null || value === "0.00" ? "" : amountToInput(value);
  return {
    numero: line.numero,
    date_operation: line.date_operation ?? "",
    date_valeur: line.date_valeur ?? "",
    libelle: line.libelle ?? "",
    reference: line.reference ?? "",
    debit: amount(line.debit),
    credit: amount(line.credit),
    solde: amountToInput(line.solde),
    pointage_type_id: line.pointage_type_id,
    lettrage_escompte: line.lettrage_escompte ?? "",
    commentaire: line.commentaire ?? "",
  };
}

/** Montant de Débit / Crédit : signe ignoré (valeur absolue), comme le serveur. */
function unsigned(text: string): string | null {
  return normalizeAmountInput(text.trim().replace(/^[-−+]/, ""));
}

/** Motifs d'erreur d'une ligne, comme ceux du serveur ; vide si la ligne est valide. */
export function checkDraft(draft: LineDraft, today: string): string[] {
  const motifs: string[] = [];
  if (!draft.date_operation) motifs.push("Date d'opération manquante.");
  else if (!ISO_DATE.test(draft.date_operation)) motifs.push("Date d'opération illisible.");
  else if (draft.date_operation > today) motifs.push("Date d'opération dans le futur.");
  if (draft.date_valeur && !ISO_DATE.test(draft.date_valeur)) {
    motifs.push("Date de valeur illisible.");
  }
  if (!draft.libelle.trim()) motifs.push("Libellé manquant.");

  const debitText = draft.debit.trim();
  const creditText = draft.credit.trim();
  const debit = debitText ? unsigned(debitText) : null;
  const credit = creditText ? unsigned(creditText) : null;
  const unreadable = (debitText && debit === null) || (creditText && credit === null);
  if (debitText && debit === null) motifs.push("Débit : montant illisible (ex. 12 500,50).");
  if (creditText && credit === null) motifs.push("Crédit : montant illisible (ex. 12 500,50).");
  if (!unreadable) {
    const hasDebit = debit !== null && toCents(debit) !== ZERO;
    const hasCredit = credit !== null && toCents(credit) !== ZERO;
    if (hasDebit && hasCredit) motifs.push("Débit et crédit renseignés sur la même ligne.");
    else if (!hasDebit && !hasCredit) motifs.push("Ni débit ni crédit.");
  }

  if (draft.solde.trim() && normalizeSignedAmountInput(draft.solde) === null) {
    motifs.push("Solde : montant illisible (ex. -15 000,50).");
  }
  if (draft.lettrage_escompte.trim().length > LETTRAGE_MAX) {
    motifs.push(`Lettrage / Escompte : ${LETTRAGE_MAX} caractères au plus.`);
  }
  return motifs;
}

/**
 * Motifs d'une ligne de l'aperçu, comme le serveur les jugera : ceux de `checkDraft`, plus ceux
 * du fichier qu'une correction n'efface pas. Une ligne en erreur dans le fichier et laissée telle
 * quelle garde ses motifs (jamais corrigée en silence) ; une autre banque reste toujours refusée.
 */
export function lineMotifs(
  line: AnalysedLine | undefined,
  draft: LineDraft,
  original: LineDraft,
  today: string,
): string[] {
  const motifs = checkDraft(draft, today);
  if (line?.statut !== "Erreur") return motifs;
  const otherBank = line.motifs.filter((motif) => motif.startsWith("Banque «"));
  const untouched = sameDraft(draft, original) ? line.motifs : [];
  return [...new Set([...motifs, ...otherBank, ...untouched])];
}

const text = (value: string) => (value.trim() ? value.trim() : null);

/** Ligne à envoyer au serveur : montants normalisés (« 12500.50 »), textes blancs → null. */
export function draftToLigne(draft: LineDraft): LigneSoumise {
  return {
    numero: draft.numero,
    date_operation: text(draft.date_operation),
    date_valeur: text(draft.date_valeur),
    libelle: text(draft.libelle),
    reference: text(draft.reference),
    debit: draft.debit.trim() ? unsigned(draft.debit) : null,
    credit: draft.credit.trim() ? unsigned(draft.credit) : null,
    solde: draft.solde.trim() ? normalizeSignedAmountInput(draft.solde) : null,
    pointage_type_id: draft.pointage_type_id,
    lettrage_escompte: text(draft.lettrage_escompte),
    commentaire: text(draft.commentaire),
  };
}

export function sameDraft(a: LineDraft, b: LineDraft): boolean {
  return (Object.keys(a) as (keyof LineDraft)[]).every((key) => a[key] === b[key]);
}

/** « 12500.5 » → 1250050n. */
export function toCents(value: string): bigint {
  const negative = value.startsWith("-");
  const [whole, decimals = ""] = (negative ? value.slice(1) : value).split(".");
  const cents = BigInt(whole || "0") * HUNDRED + BigInt(`${decimals}00`.slice(0, 2));
  return negative ? -cents : cents;
}

/** 1250050n → « 12500.50 ». */
export function fromCents(cents: bigint): string {
  const negative = cents < ZERO;
  const absolute = negative ? -cents : cents;
  const rest = (absolute % HUNDRED).toString().padStart(2, "0");
  return `${negative ? "-" : ""}${absolute / HUNDRED}.${rest}`;
}

/**
 * Résumé des lignes cochées. Les soldes des lignes SOLDE INITIAL / SOLDE FINAL du fichier
 * l'emportent ; sinon ils sont déduits des lignes, lues comme le serveur (ordre du fichier,
 * inversé s'il va du plus récent au plus ancien).
 */
export function summariseDrafts(
  drafts: LineDraft[],
  fileOpening: string | null,
  fileClosing: string | null,
): DraftSummary {
  const lines = drafts.map(draftToLigne);
  const debits = lines.map((line) => toCents(line.debit ?? "0"));
  const credits = lines.map((line) => toCents(line.credit ?? "0"));
  const sum = (values: bigint[]) => values.reduce((total, value) => total + value, ZERO);
  const dates = lines
    .map((line) => line.date_operation)
    .filter((date): date is string => !!date)
    .sort();
  const result: DraftSummary = {
    count: lines.length,
    totalDebit: fromCents(sum(debits)),
    totalCredit: fromCents(sum(credits)),
    periodeDebut: dates[0] ?? null,
    periodeFin: dates.at(-1) ?? null,
    ouverture: fileOpening,
    cloture: fileClosing,
    coherent: null,
  };
  if (lines.length === 0) return result;

  const order = lines.map((_, index) => index);
  if ((lines[0].date_operation ?? "") > (lines.at(-1)?.date_operation ?? "")) order.reverse();
  if (lines.every((line) => line.solde !== null)) {
    const head = order[0];
    const tail = order[order.length - 1];
    result.ouverture ??= fromCents(
      toCents(lines[head].solde as string) - credits[head] + debits[head],
    );
    result.cloture ??= lines[tail].solde;
  }
  if (result.ouverture !== null && result.cloture !== null) {
    const movements = sum(credits) - sum(debits);
    result.coherent = toCents(result.ouverture) + movements === toCents(result.cloture);
  }
  return result;
}
