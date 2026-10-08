"use client";

import { Check, CircleAlert, PenLine, RotateCcw } from "lucide-react";
import { Fragment, useState, type ReactNode } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { FilterTile } from "@/components/releves/FilterTile";
import { IgnoredLinesTable } from "@/components/releves/IgnoredLinesTable";
import { DateInput, NumberInput, Select, TextInput } from "@/components/ui/Field";
import { Pagination } from "@/components/ui/Pagination";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import { pageOf, toggleVue, type VueLignes } from "@/lib/importLines";
import {
  lineMotifs,
  draftToLigne,
  sameDraft,
  summariseDrafts,
  type LineDraft,
} from "@/lib/statementLines";
import type { AnalysedLine, Analysis, LineStatus, PointageType } from "@/types/statement";

type EditablePreviewProps = {
  analysis: Analysis;
  /** Nom de la société active : colonne Société du format standard. */
  societe: string;
  logo: string | null | undefined;
  suffix: string;
  pointages: PointageType[];
  drafts: LineDraft[];
  originals: LineDraft[];
  checked: Set<number>;
  editing: number | null;
  today: string;
  onChange: (draft: LineDraft) => void;
  onToggle: (numero: number, checked: boolean) => void;
  onEdit: (numero: number | null) => void;
  onReset: (numero: number) => void;
};

const HEAD = "px-3 py-2.5 text-left whitespace-nowrap";
const CELL = "px-3 py-2 align-top";
const ICON =
  "rounded-lg p-1.5 text-simtis-muted transition-colors hover:bg-simtis-light hover:text-simtis-primary";

/** Ligne du fichier déjà importée pour ce compte : jamais cochable. */
export function alreadyImported(line: AnalysedLine | undefined): boolean {
  return !!line && line.statut === "Doublon" && line.doublon_de === null;
}

/** État affiché : erreur tant que la ligne a un motif (`lineMotifs`), sinon le statut d'origine. */
export function draftStatus(line: AnalysedLine | undefined, motifs: string[]): LineStatus {
  if (alreadyImported(line)) return "Doublon";
  if (motifs.length > 0) return "Erreur";
  return line?.statut === "Doublon" ? "Doublon" : "Valide";
}

/**
 * Étape Validation : le relevé tel qu'il sera enregistré, au format standard, modifiable ligne
 * par ligne (décision métier du 02/10/2026 : correction seulement, aucun ajout de ligne).
 */
export function EditablePreview({
  analysis,
  societe,
  logo,
  suffix,
  pointages,
  drafts,
  originals,
  checked,
  editing,
  today,
  onChange,
  onToggle,
  onEdit,
  onReset,
}: EditablePreviewProps) {
  const lines = new Map(analysis.lignes.map((line) => [line.numero, line]));
  const originalOf = new Map(originals.map((draft) => [draft.numero, draft]));
  const pointageLabel = new Map(pointages.map((item) => [item.id, item.libelle]));
  const checkedDrafts = drafts.filter((draft) => checked.has(draft.numero));
  const { resume } = analysis;
  const summary = summariseDrafts(
    checkedDrafts,
    resume.solde_ouverture_fichier ? resume.solde_ouverture : null,
    resume.solde_cloture_fichier ? resume.solde_cloture : null,
  );
  const motifsOf = (draft: LineDraft) =>
    lineMotifs(lines.get(draft.numero), draft, originalOf.get(draft.numero) ?? draft, today);
  const errors = checkedDrafts.filter((draft) => motifsOf(draft).length > 0).length;
  const duplicates = analysis.lignes.filter((line) => line.statut === "Doublon").length;
  // Tuile choisie : le tableau ne montre que ces lignes (second clic : toutes)
  const [vue, setVue] = useState<VueLignes>("toutes");
  const [page, setPage] = useState(1);
  function choose(next: VueLignes) {
    setVue((current) => toggleVue(current, next));
    setPage(1);
  }
  const shownDrafts = drafts.filter((draft) => {
    if (vue === "importer") return checked.has(draft.numero);
    if (vue === "erreurs") return checked.has(draft.numero) && motifsOf(draft).length > 0;
    if (vue === "doublons") return lines.get(draft.numero)?.statut === "Doublon";
    return true;
  });
  // 100 lignes par page ; les totaux et le filtre portent sur tout le fichier
  const pageDrafts = pageOf(shownDrafts, page);

  function amount(value: string | null, typed: string): ReactNode {
    if (value !== null) return formatAmount(value, suffix, { dashForZero: true });
    return typed ? <span className="text-simtis-danger-fg">{typed}</span> : "-";
  }

  function field(draft: LineDraft, key: keyof LineDraft, label: string) {
    const common = {
      "aria-label": `${label} de la ligne ${draft.numero}`,
      value: String(draft[key] ?? ""),
      onChange: (event: { target: { value: string } }) =>
        onChange({ ...draft, [key]: event.target.value }),
      className: "h-9 min-w-[120px]",
    };
    if (key === "date_operation" || key === "date_valeur") return <DateInput {...common} />;
    if (key === "debit" || key === "credit" || key === "solde") return <NumberInput {...common} />;
    return <TextInput {...common} />;
  }

  return (
    <>
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <FilterTile
          label="Lignes à importer"
          value={summary.count}
          tone="text-simtis-success"
          active={vue === "importer"}
          onClick={() => choose("importer")}
        />
        <FilterTile
          label="Lignes en erreur"
          value={errors}
          tone="text-simtis-danger"
          active={vue === "erreurs"}
          onClick={() => choose("erreurs")}
        />
        <FilterTile
          label="Doublons"
          value={duplicates}
          tone="text-simtis-warning"
          active={vue === "doublons"}
          onClick={() => choose("doublons")}
        />
        <FilterTile
          label="Lignes ignorées"
          value={resume.nb_ignorees}
          tone="text-simtis-muted"
          active={vue === "ignorees"}
          onClick={() => choose("ignorees")}
        />
      </div>
      {summary.coherent === false && (
        <div
          role="alert"
          className="mb-4 flex items-start gap-2 rounded-lg bg-simtis-warning-bg px-3 py-2.5 text-sm text-simtis-warning-fg"
        >
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          Les mouvements retenus ne retrouvent pas le solde de clôture : vérifiez les lignes.
        </div>
      )}
      <dl
        className="mb-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-4"
        aria-label="Résumé des lignes à importer"
      >
        <div>
          <dt className="text-simtis-muted">Période</dt>
          <dd className="font-medium">
            {summary.periodeDebut
              ? `${formatDate(summary.periodeDebut)} au ${formatDate(summary.periodeFin)}`
              : "-"}
          </dd>
        </div>
        <div>
          <dt className="text-simtis-muted">Total débit / crédit</dt>
          <dd className="font-medium tabular-nums">
            {formatAmount(summary.totalDebit, suffix)} / {formatAmount(summary.totalCredit, suffix)}
          </dd>
        </div>
        <div>
          <dt className="text-simtis-muted">Solde d&apos;ouverture</dt>
          <dd className="font-medium tabular-nums">
            {formatAmount(summary.ouverture, suffix)}
            {resume.solde_ouverture_fichier && (
              <span className="block text-xs font-normal text-simtis-muted">
                ligne SOLDE INITIAL du fichier
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-simtis-muted">Solde de clôture</dt>
          <dd className="font-medium tabular-nums">
            {formatAmount(summary.cloture, suffix)}
            {resume.solde_cloture_fichier && (
              <span className="block text-xs font-normal text-simtis-muted">
                ligne SOLDE FINAL du fichier
              </span>
            )}
          </dd>
        </div>
      </dl>

      {vue === "ignorees" && <IgnoredLinesTable lignes={analysis.lignes_ignorees ?? []} />}
      {vue !== "ignorees" && shownDrafts.length === 0 && (
        <p className="rounded-[12px] border border-simtis-border px-4 py-6 text-center text-sm text-simtis-muted">
          Aucune ligne dans ce filtre.
        </p>
      )}
      {/* « relative » : les textes réservés aux lecteurs d'écran (sr-only, en position absolue)
          restent dans la zone qui défile au lieu d'élargir toute la page */}
      <div
        className={cn(
          "relative overflow-x-auto rounded-[12px] border border-simtis-border bg-simtis-card",
          (vue === "ignorees" || shownDrafts.length === 0) && "hidden",
        )}
      >
        <table className="w-full border-collapse text-[13.5px] text-simtis-text">
          <thead>
            <tr className="bg-simtis-light/60 text-[13px] font-semibold text-simtis-primary-dark">
              <th scope="col" className={HEAD}>
                Importer
              </th>
              <th scope="col" className={HEAD}>
                État
              </th>
              <th scope="col" className={HEAD}>
                Société
              </th>
              <th scope="col" className={HEAD}>
                Pointage
              </th>
              <th scope="col" className={HEAD}>
                Banque
              </th>
              <th scope="col" className={HEAD}>
                Date d&apos;opération
              </th>
              <th scope="col" className={HEAD}>
                Date de valeur
              </th>
              <th scope="col" className={HEAD}>
                Libellé
              </th>
              <th scope="col" className={cn(HEAD, "text-right")}>
                Débit
              </th>
              <th scope="col" className={cn(HEAD, "text-right")}>
                Crédit
              </th>
              <th scope="col" className={cn(HEAD, "text-right")}>
                Solde
              </th>
              <th scope="col" className={HEAD}>
                Lettrage / Escompte
              </th>
              <th scope="col" className={HEAD}>
                Commentaire
              </th>
              <th scope="col" className={HEAD}>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {pageDrafts.rows.map((draft) => {
              const line = lines.get(draft.numero);
              const original = originalOf.get(draft.numero) ?? draft;
              const motifs = lineMotifs(line, draft, original, today);
              const status = draftStatus(line, motifs);
              const locked = alreadyImported(line);
              const corrected = !sameDraft(draft, original);
              const isEditing = editing === draft.numero;
              const ligne = draftToLigne(draft);
              const notes =
                locked || (status === "Doublon" && !motifs.length) ? (line?.motifs ?? []) : motifs;
              return (
                <Fragment key={draft.numero}>
                  <tr
                    className={cn(
                      "border-t border-simtis-border/70",
                      isEditing ? "bg-simtis-light/40" : "hover:bg-simtis-light/30",
                      !checked.has(draft.numero) && !isEditing && "text-simtis-muted",
                    )}
                  >
                    <td className={CELL}>
                      <input
                        type="checkbox"
                        className="mt-1 h-4 w-4 accent-simtis-primary"
                        checked={checked.has(draft.numero)}
                        disabled={locked}
                        onChange={(event) => onToggle(draft.numero, event.target.checked)}
                        aria-label={`Importer la ligne ${draft.numero}`}
                      />
                    </td>
                    <td className={CELL}>
                      <StatusBadge status={status} />
                      <span className="mt-1 block text-xs text-simtis-muted">
                        ligne {draft.numero}
                      </span>
                      {corrected && (
                        <span className="block text-xs font-medium text-simtis-primary">
                          corrigée
                        </span>
                      )}
                    </td>
                    <td className={cn(CELL, "whitespace-nowrap")}>{societe}</td>
                    <td className={CELL}>
                      {isEditing ? (
                        <Select
                          aria-label={`Pointage de la ligne ${draft.numero}`}
                          className="h-9 min-w-[150px]"
                          value={
                            draft.pointage_type_id === null ? "" : String(draft.pointage_type_id)
                          }
                          placeholder="Sans pointage"
                          options={pointages.map((item) => ({
                            value: String(item.id),
                            label: item.libelle,
                          }))}
                          onChange={(event) =>
                            onChange({
                              ...draft,
                              pointage_type_id: event.target.value
                                ? Number(event.target.value)
                                : null,
                            })
                          }
                        />
                      ) : (
                        <span className="whitespace-nowrap">
                          {draft.pointage_type_id === null
                            ? "À choisir"
                            : (pointageLabel.get(draft.pointage_type_id) ?? "-")}
                        </span>
                      )}
                    </td>
                    <td className={CELL}>
                      <BankLabel code={analysis.bank_code} logo={logo} />
                    </td>
                    <td className={cn(CELL, "whitespace-nowrap")}>
                      {isEditing
                        ? field(draft, "date_operation", "Date d'opération")
                        : formatDate(ligne.date_operation)}
                    </td>
                    <td className={cn(CELL, "whitespace-nowrap")}>
                      {isEditing
                        ? field(draft, "date_valeur", "Date de valeur")
                        : formatDate(ligne.date_valeur)}
                    </td>
                    <td className={CELL}>
                      {isEditing ? (
                        <div className="min-w-[240px] space-y-1">
                          {field(draft, "libelle", "Libellé")}
                          {field(draft, "reference", "Référence")}
                        </div>
                      ) : (
                        <span className="block min-w-[220px]">
                          <span className="block">{ligne.libelle ?? "-"}</span>
                          {ligne.reference && (
                            <span className="block text-xs text-simtis-muted">
                              Réf. {ligne.reference}
                            </span>
                          )}
                        </span>
                      )}
                    </td>
                    <td className={cn(CELL, "text-right whitespace-nowrap tabular-nums")}>
                      {isEditing
                        ? field(draft, "debit", "Débit")
                        : amount(ligne.debit, draft.debit)}
                    </td>
                    <td className={cn(CELL, "text-right whitespace-nowrap tabular-nums")}>
                      {isEditing
                        ? field(draft, "credit", "Crédit")
                        : amount(ligne.credit, draft.credit)}
                    </td>
                    <td className={cn(CELL, "text-right whitespace-nowrap tabular-nums")}>
                      {isEditing
                        ? field(draft, "solde", "Solde")
                        : ligne.solde !== null
                          ? formatAmount(ligne.solde, suffix)
                          : amount(null, draft.solde)}
                    </td>
                    <td className={CELL}>
                      {isEditing
                        ? field(draft, "lettrage_escompte", "Lettrage / Escompte")
                        : (ligne.lettrage_escompte ?? "-")}
                    </td>
                    <td className={CELL}>
                      {isEditing
                        ? field(draft, "commentaire", "Commentaire")
                        : (ligne.commentaire ?? "-")}
                    </td>
                    <td className={cn(CELL, "whitespace-nowrap")}>
                      {isEditing ? (
                        <span className="inline-flex gap-1">
                          <button
                            type="button"
                            onClick={() => onEdit(null)}
                            aria-label={`Terminer la ligne ${draft.numero}`}
                            title="Terminer"
                            className={ICON}
                          >
                            <Check className="h-4 w-4" aria-hidden />
                          </button>
                          <button
                            type="button"
                            onClick={() => onReset(draft.numero)}
                            disabled={!corrected}
                            aria-label={`Annuler les corrections de la ligne ${draft.numero}`}
                            title="Annuler les corrections"
                            className={cn(ICON, "disabled:opacity-40")}
                          >
                            <RotateCcw className="h-4 w-4" aria-hidden />
                          </button>
                        </span>
                      ) : (
                        !locked && (
                          <button
                            type="button"
                            onClick={() => onEdit(draft.numero)}
                            aria-label={`Modifier la ligne ${draft.numero}`}
                            title="Modifier"
                            className={ICON}
                          >
                            <PenLine className="h-4 w-4" aria-hidden />
                          </button>
                        )
                      )}
                    </td>
                  </tr>
                  {notes.length > 0 && (
                    <tr>
                      <td />
                      <td
                        colSpan={13}
                        className={cn(
                          "px-3 pb-2 text-xs",
                          status === "Erreur" ? "text-simtis-danger-fg" : "text-simtis-warning-fg",
                        )}
                      >
                        {notes.join(" ")}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      {vue !== "ignorees" && shownDrafts.length > 0 && (
        <Pagination
          label="Pages de l'aperçu"
          page={pageDrafts.page}
          pages={pageDrafts.pages}
          total={shownDrafts.length}
          noun="ligne"
          onPage={setPage}
        />
      )}
    </>
  );
}
