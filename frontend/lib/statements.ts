/**
 * Import des relevés : correspondance colonnes / champs et formulaire envoyé à l'API. Fonctions pures.
 */
import type { ColumnMapping, ConfirmOptions, FieldCode, ImportRequest } from "@/types/statement";

/** Taille maximale acceptée par l'API (`import_file.MAX_FILE_BYTES`, 20 Mo depuis le 08/10/2026). */
export const MAX_FILE_BYTES = 20 * 1024 * 1024;

/** Formats acceptés (relevés et exports Sage) : .xlsx, et l'ancien .xls depuis le 08/10/2026. */
export const EXTENSIONS = [".xlsx", ".xls"] as const;

/** Valeur de l'attribut `accept` des zones de dépôt. */
export const ACCEPT_EXCEL =
  ".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel";

/** Vérification faite avant l'envoi ; l'API refait toujours la sienne. */
export function fileProblem(file: { name: string; size: number }): string | null {
  const name = file.name.toLowerCase();
  if (!EXTENSIONS.some((extension) => name.endsWith(extension)))
    return "Seuls les fichiers Excel .xlsx ou .xls sont acceptés.";
  if (file.size === 0) return "Le fichier est vide.";
  if (file.size > MAX_FILE_BYTES) return "Fichier trop volumineux : 20 Mo au plus.";
  return null;
}

/** { champ: colonne } → { colonne: champ } : le champ choisi pour chaque colonne du fichier. */
export function fieldsByColumn(mapping: ColumnMapping): Record<number, FieldCode> {
  const result: Record<number, FieldCode> = {};
  for (const [code, index] of Object.entries(mapping)) {
    if (index !== null && index !== undefined) result[index] = code as FieldCode;
  }
  return result;
}

/**
 * Le champ d'une colonne change : un champ ne peut être associé qu'à une colonne, il est donc retiré
 * de celle qui l'avait. `null` = colonne ignorée.
 */
export function assignField(
  mapping: ColumnMapping,
  column: number,
  field: FieldCode | null,
): ColumnMapping {
  const next: ColumnMapping = {};
  for (const [code, index] of Object.entries(mapping)) {
    if (index !== column && code !== field) next[code as FieldCode] = index;
  }
  if (field) next[field] = column;
  return next;
}

/** Formulaire multipart attendu par `/statements/import/analyse` et `/confirm`. */
export function importForm(request: ImportRequest, options?: ConfirmOptions): FormData {
  const form = new FormData();
  form.append("fichier", request.file);
  form.append("bank_account_id", String(request.accountId));
  if (request.mapping) {
    const mapped = Object.fromEntries(
      Object.entries(request.mapping).filter(([, index]) => index !== null && index !== undefined),
    );
    form.append("mapping", JSON.stringify(mapped));
  }
  if (request.feuille) form.append("feuille", request.feuille);
  if (request.soldeOuverture) form.append("solde_ouverture", request.soldeOuverture);
  if (options && "lignes" in options) {
    // Aperçu modifiable : les lignes remplacent garder_doublons / ecarter_erreurs. Envoyées comme
    // un fichier JSON : le serveur limite un champ de formulaire à 1 Mo (environ 3 700 lignes).
    const json = new Blob([JSON.stringify(options.lignes)], { type: "application/json" });
    form.append("lignes", json, "lignes.json");
  } else if (options) {
    if (options.garderDoublons.length > 0) {
      form.append(
        "garder_doublons",
        JSON.stringify([...options.garderDoublons].sort((a, b) => a - b)),
      );
    }
    form.append("ecarter_erreurs", String(options.ecarterErreurs));
  }
  return form;
}

/** Nom du fichier exporté, identique à celui de l'API : « releve_CIH_MAD_2026-09-24_2026-09-26.xlsx ». */
export function exportFilename(statement: {
  bank_code: string;
  devise: string;
  periode_debut: string | null;
  periode_fin: string | null;
}): string {
  const { bank_code, devise, periode_debut, periode_fin } = statement;
  return `releve_${bank_code}_${devise}_${periode_debut}_${periode_fin}.xlsx`;
}

/** Période facultative d'un relevé continu, dates « AAAA-MM-JJ » (vide = pas de borne). */
export type Period = { from?: string; to?: string };

/** « ?from=...&to=... » avec les seules bornes renseignées, ou « » s'il n'y en a aucune. */
export function periodQuery(period: Period): string {
  const params = new URLSearchParams();
  if (period.from) params.set("from", period.from);
  if (period.to) params.set("to", period.to);
  return params.size ? `?${params}` : "";
}

/** Comptes qui ont au moins un relevé importé, une fois chacun, triés par banque puis devise. */
export function accountsWithStatements<
  T extends { bank_account_id: number; bank_code: string; devise: string },
>(statements: readonly T[]): T[] {
  const seen = new Map<number, T>();
  for (const statement of statements) {
    if (!seen.has(statement.bank_account_id)) seen.set(statement.bank_account_id, statement);
  }
  return [...seen.values()].sort(
    (a, b) => a.bank_code.localeCompare(b.bank_code) || a.devise.localeCompare(b.devise),
  );
}

/** Opérations affichées d'un relevé continu, puis ajoutées à chaque « Afficher plus ». */
export const OPERATIONS_AFFICHEES = 50;
/** Imports affichés dans le journal, puis ajoutés à chaque « Afficher plus ». */
export const IMPORTS_AFFICHES = 10;

/** Partie visible d'une longue liste : `hidden` lignes masquées, `next` affichées au clic suivant. */
export type ShownRows<T> = { rows: T[]; hidden: number; next: number };

/** Les `shown` dernières lignes (relevé trié par date croissante : les plus récentes). */
export function showLast<T>(rows: readonly T[], shown: number, step: number): ShownRows<T> {
  const hidden = Math.max(0, rows.length - shown);
  return { rows: rows.slice(hidden), hidden, next: Math.min(step, hidden) };
}

/** Les `shown` premières lignes (journal trié du plus récent au plus ancien). */
export function showFirst<T>(rows: readonly T[], shown: number, step: number): ShownRows<T> {
  const hidden = Math.max(0, rows.length - shown);
  return { rows: rows.slice(0, shown), hidden, next: Math.min(step, hidden) };
}

/**
 * Option mise en avant dans une liste déroulante après une touche du clavier : flèches (sans
 * boucler), Début, Fin. `null` si la touche ne déplace rien.
 */
export function moveIndex(current: number, key: string, count: number): number | null {
  if (count === 0) return null;
  switch (key) {
    case "ArrowDown":
      return Math.min(current + 1, count - 1);
    case "ArrowUp":
      return Math.max(current - 1, 0);
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return null;
  }
}

/** Fait enregistrer un fichier par le navigateur. */
export function saveFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** « 2026-10-01T09:30:00+00:00 » → « 01/10/2026 10:30 », à l'heure du Maroc. */
export function formatDateTime(iso: string): string {
  const parts = new Intl.DateTimeFormat("fr-FR", {
    timeZone: "Africa/Casablanca",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).formatToParts(new Date(iso));
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${get("day")}/${get("month")}/${get("year")} ${get("hour")}:${get("minute")}`;
}

/**
 * Commentaire tapé directement dans le tableau (10/10/2026) : la valeur à enregistrer (texte sans
 * espaces autour, ou null si vide), ou undefined si rien n'a changé.
 */
export function commentaireAEnregistrer(
  avant: string | null,
  saisi: string,
): string | null | undefined {
  const valeur = saisi.trim() || null;
  return valeur === (avant ?? null) ? undefined : valeur;
}
