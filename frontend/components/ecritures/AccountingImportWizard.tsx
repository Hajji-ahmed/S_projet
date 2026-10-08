"use client";

import { ArrowLeft, CircleAlert, Upload } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { FilterTile } from "@/components/releves/FilterTile";
import { IgnoredLinesTable } from "@/components/releves/IgnoredLinesTable";
import { FileDropzone, ImportStepper } from "@/components/releves/ImportSteps";
import { Button } from "@/components/ui/Button";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Field, Select } from "@/components/ui/Field";
import { Pagination } from "@/components/ui/Pagination";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import { pageOf, sageLinesFor, toggleVue, type VueLignes } from "@/lib/importLines";
import { fileProblem } from "@/lib/statements";
import { analyseEntries, confirmEntries } from "@/services/accounting";
import type {
  AccountingFieldCode,
  AccountingMapping,
  AnalyseComptable,
  ConfirmationComptable,
  LigneComptable,
} from "@/types/accounting";
import type { ImportColumn } from "@/types/statement";

const NO_JOURNAL = "Renseignez le journal Sage";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Une erreur est survenue.";
}

function Alert({ tone, children }: { tone: "danger" | "warning"; children: ReactNode }) {
  return (
    <div
      role="alert"
      className={cn(
        "mb-4 flex items-start gap-2 rounded-lg px-3 py-2.5 text-sm",
        tone === "danger"
          ? "bg-simtis-danger-bg text-simtis-danger-fg"
          : "bg-simtis-warning-bg text-simtis-warning-fg",
      )}
    >
      <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

type AccountingImportWizardProps = {
  companyId: number;
  logos: Map<string, string | null>;
  onDone: (result: ConfirmationComptable) => void;
  onCancel: () => void;
};

/**
 * Import d'un export Sage en deux étapes : Fichier, puis Validation. L'analyse se lance dès que le
 * fichier est choisi ; la correspondance des colonnes ne s'affiche que si elles ne sont pas
 * reconnues. Aperçu en lecture seule : SIMTIS n'est pas un second Sage, une ligne en erreur se
 * corrige dans Sage ou s'écarte. Rien n'est enregistré avant « Confirmer l'import ».
 */
export function AccountingImportWizard({
  companyId,
  logos,
  onDone,
  onCancel,
}: AccountingImportWizardProps) {
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [step, setStep] = useState(0);
  const [analysis, setAnalysis] = useState<AnalyseComptable | null>(null);
  const [mapping, setMapping] = useState<AccountingMapping>({});
  const [feuille, setFeuille] = useState<string | undefined>(undefined);
  const [ecarter, setEcarter] = useState(false);
  // Tuile choisie à l'étape Validation : le tableau ne montre que ces lignes
  const [vue, setVue] = useState<VueLignes>("toutes");
  const [pageLignes, setPageLignes] = useState(1);
  const [garder, setGarder] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(
    chosen: File,
    options: { mapping?: AccountingMapping; feuille?: string } = {},
  ) {
    setBusy(true);
    setError(null);
    try {
      const result = await analyseEntries(chosen, companyId, options);
      setAnalysis(result);
      setMapping(result.mapping);
      setFeuille(result.feuille);
      setEcarter(false);
      setGarder(new Set());
      setStep(result.erreurs_mapping.length > 0 ? 0 : 1);
    } catch (caught) {
      setAnalysis(null);
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  function chooseFile(chosen: File) {
    const problem = fileProblem(chosen);
    setFileError(problem);
    setFile(problem ? null : chosen);
    setAnalysis(null);
    if (!problem) void run(chosen);
  }

  const resume = analysis?.resume;
  const toImport = (resume?.nb_valides ?? 0) + garder.size;
  const blocked =
    !analysis ||
    analysis.deja_importe ||
    toImport === 0 ||
    ((resume?.nb_erreurs ?? 0) > 0 && !ecarter);

  async function confirm() {
    if (!file || blocked) return;
    setBusy(true);
    setError(null);
    try {
      onDone(
        await confirmEntries(file, companyId, {
          mapping,
          feuille,
          garderDoublons: [...garder],
          ecarterErreurs: ecarter,
        }),
      );
    } catch (caught) {
      setError(errorMessage(caught));
      setBusy(false);
    }
  }

  function sheetPicker(current: AnalyseComptable) {
    if (current.feuilles.length < 2) return null;
    return (
      <div className="mb-4 w-full max-w-xs">
        <Field label="Feuille" htmlFor="sage-feuille">
          <Select
            id="sage-feuille"
            value={current.feuille}
            disabled={busy}
            options={current.feuilles.map((name) => ({ value: name, label: name }))}
            onChange={(event) => file && run(file, { feuille: event.target.value })}
          />
        </Field>
      </div>
    );
  }

  // --- Secours : colonnes non reconnues -----------------------------------------------------------

  function stepMapping(current: AnalyseComptable) {
    const byColumn: Record<number, AccountingFieldCode> = {};
    for (const [code, index] of Object.entries(mapping)) {
      if (index !== null && index !== undefined) byColumn[index] = code as AccountingFieldCode;
    }
    const options = current.champs.map((champ) => ({
      value: champ.code,
      label: champ.obligatoire ? `${champ.libelle} (obligatoire)` : champ.libelle,
    }));
    function assign(column: number, code: AccountingFieldCode | null) {
      setMapping((value) => {
        const next: AccountingMapping = {};
        for (const [field, index] of Object.entries(value)) {
          next[field as AccountingFieldCode] = index === column ? null : index;
        }
        if (code) next[code] = column;
        return next;
      });
    }
    const columns: Column<ImportColumn>[] = [
      {
        key: "colonne",
        header: "Colonne fichier",
        render: (column) => (
          <span className="whitespace-nowrap">
            <span className="mr-2 text-xs text-simtis-muted">{column.lettre}</span>
            <span className="font-medium">{column.entete || "(sans en-tête)"}</span>
          </span>
        ),
      },
      {
        key: "exemples",
        header: "Exemples",
        render: (column) => (
          <span className="text-simtis-muted">{column.exemples.join(" · ") || "-"}</span>
        ),
      },
      {
        key: "champ",
        header: "Champ SIMTIS",
        render: (column) => (
          <div className="min-w-[200px]">
            <Select
              id={`sage-champ-${column.index}`}
              aria-label={`Champ SIMTIS de la colonne ${column.lettre}`}
              value={byColumn[column.index] ?? ""}
              placeholder="Ignorer cette colonne"
              options={options}
              onChange={(event) =>
                assign(column.index, (event.target.value || null) as AccountingFieldCode | null)
              }
            />
          </div>
        ),
      },
    ];
    return (
      <section
        aria-label="Colonnes non reconnues"
        className="mt-6 rounded-[12px] border border-simtis-warning/40 bg-simtis-background p-4"
      >
        <h3 className="text-[15px] font-semibold text-simtis-text">Colonnes non reconnues</h3>
        <p className="mt-1 mb-4 text-sm text-simtis-muted">
          {current.fichier_nom} · en-têtes lus à la ligne {current.ligne_entete}. Associez chaque
          colonne utile à son champ : la correspondance sera reprise au prochain export de cette
          société.
        </p>
        {sheetPicker(current)}
        <Alert tone="warning">
          <ul className="space-y-0.5">
            {current.erreurs_mapping.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </Alert>
        <DataTable columns={columns} rows={current.colonnes} getRowKey={(c) => String(c.index)} />
        <div className="mt-4 flex justify-end">
          <Button onClick={() => file && run(file, { mapping, feuille })} disabled={busy}>
            {busy ? "Analyse en cours..." : "Valider les colonnes"}
          </Button>
        </div>
      </section>
    );
  }

  // --- Étape 2 : validation (lecture seule) -------------------------------------------------------

  function stepValidation(current: AnalyseComptable) {
    const summary = current.resume;
    const columns: Column<LigneComptable>[] = [
      {
        key: "statut",
        header: "État",
        render: (line) => (
          <span className="block min-w-[150px]">
            <StatusBadge status={line.statut} />
            {line.motifs.map((motif) => (
              <span key={motif} className="mt-1 block text-xs text-simtis-muted">
                {motif}
              </span>
            ))}
            {line.doublon_de !== null && (
              <label className="mt-1 flex items-center gap-1.5 text-xs text-simtis-text">
                <input
                  type="checkbox"
                  checked={garder.has(line.numero)}
                  onChange={(event) =>
                    setGarder((value) => {
                      const next = new Set(value);
                      if (event.target.checked) next.add(line.numero);
                      else next.delete(line.numero);
                      return next;
                    })
                  }
                />
                Garder la ligne {line.numero}
              </label>
            )}
          </span>
        ),
      },
      {
        key: "date_ecriture",
        header: "Date",
        render: (line) => (
          <span className="whitespace-nowrap">{formatDate(line.date_ecriture)}</span>
        ),
      },
      { key: "journal", header: "Journal", render: (line) => line.journal ?? "-" },
      {
        key: "bank_code",
        header: "Compte bancaire",
        render: (line) =>
          line.bank_code ? (
            <BankLabel code={line.bank_code} logo={logos.get(line.bank_code)} />
          ) : (
            "-"
          ),
      },
      { key: "compte", header: "Compte", render: (line) => line.compte ?? "-" },
      { key: "numero_piece", header: "N° pièce", render: (line) => line.numero_piece ?? "-" },
      {
        key: "libelle",
        header: "Libellé",
        render: (line) => <span className="block min-w-[200px]">{line.libelle ?? "-"}</span>,
      },
      {
        key: "debit",
        header: "Débit",
        align: "right",
        render: (line) => formatAmount(line.debit, "DH", { dashForZero: true }),
      },
      {
        key: "credit",
        header: "Crédit",
        align: "right",
        render: (line) => formatAmount(line.credit, "DH", { dashForZero: true }),
      },
      {
        key: "echeance",
        header: "Échéance",
        render: (line) => <span className="whitespace-nowrap">{formatDate(line.echeance)}</span>,
      },
      { key: "tiers", header: "Tiers", render: (line) => line.tiers ?? "-" },
    ];
    const filters: [VueLignes, string, number, string][] = [
      ["importer", "Lignes à importer", toImport, "text-simtis-success"],
      ["erreurs", "Lignes en erreur", summary.nb_erreurs, "text-simtis-danger"],
      ["doublons", "Doublons", summary.nb_doublons, "text-simtis-warning"],
      ["ignorees", "Lignes ignorées", summary.nb_ignorees, "text-simtis-muted"],
    ];
    const shown = sageLinesFor(current.lignes, vue, garder);
    // 100 lignes par page ; les tuiles et les totaux portent sur tout le fichier
    const pageLignesView = pageOf(shown, pageLignes);
    const tiles: [string, ReactNode][] = [
      [
        "Total débit / crédit",
        `${formatAmount(summary.total_debit, "DH")} / ${formatAmount(summary.total_credit, "DH")}`,
      ],
      [
        "Période",
        summary.periode_debut
          ? `${formatDate(summary.periode_debut)} au ${formatDate(summary.periode_fin)}`
          : "-",
      ],
    ];
    return (
      <>
        {current.deja_importe && (
          <Alert tone="danger">Ce fichier a déjà été importé pour cette société.</Alert>
        )}
        <p className="mb-4 text-sm text-simtis-muted">
          {current.fichier_nom} · seules les lignes banque des journaux de banque sont retenues
          (journal Sage de vos comptes) ; les contreparties et les autres journaux sont ignorés.
        </p>
        {sheetPicker(current)}
        <div className="mb-3 grid grid-cols-2 gap-3 md:grid-cols-4">
          {filters.map(([value, label, count, tone]) => (
            <FilterTile
              key={value}
              label={label}
              value={count}
              tone={tone}
              active={vue === value}
              onClick={() => {
                setVue((currentVue) => toggleVue(currentVue, value));
                setPageLignes(1);
              }}
            />
          ))}
        </div>
        <dl className="mb-4 grid gap-3 sm:grid-cols-2">
          {tiles.map(([label, value]) => (
            <div
              key={label}
              className="rounded-[12px] border border-simtis-border bg-simtis-background px-3 py-2"
            >
              <dt className="text-xs text-simtis-muted">{label}</dt>
              <dd className="font-semibold text-simtis-text tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
        {summary.par_compte.length > 0 && (
          <ul
            aria-label="Écritures par compte"
            className="mb-4 flex flex-wrap gap-x-6 gap-y-2 text-sm"
          >
            {summary.par_compte.map((item) => (
              <li key={item.bank_account_id} className="flex items-center gap-2">
                <BankLabel code={item.bank_code} logo={logos.get(item.bank_code)}>
                  {item.bank_code} · {item.journal}
                </BankLabel>
                <span className="text-simtis-muted tabular-nums">
                  {item.nb} écriture{item.nb > 1 ? "s" : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
        {vue === "ignorees" ? (
          <IgnoredLinesTable lignes={current.lignes_ignorees ?? []} />
        ) : (
          <>
            <DataTable
              columns={columns}
              rows={pageLignesView.rows}
              getRowKey={(line) => String(line.numero)}
              emptyMessage={
                vue === "toutes"
                  ? "Aucune ligne banque dans ce fichier."
                  : "Aucune ligne dans ce filtre."
              }
            />
            {shown.length > 0 && (
              <Pagination
                label="Pages de l'aperçu"
                page={pageLignesView.page}
                pages={pageLignesView.pages}
                total={shown.length}
                noun="ligne"
                onPage={setPageLignes}
              />
            )}
          </>
        )}
        {summary.nb_erreurs > 0 && (
          <label className="mt-4 flex items-center gap-2 text-sm text-simtis-text">
            <input
              type="checkbox"
              checked={ecarter}
              onChange={(event) => setEcarter(event.target.checked)}
            />
            Écarter les lignes en erreur ({summary.nb_erreurs}) : elles se corrigent dans Sage.
          </label>
        )}
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <Button
            variant="secondary"
            icon={ArrowLeft}
            onClick={() => {
              setAnalysis(null);
              setStep(0);
            }}
            disabled={busy}
          >
            Changer de fichier
          </Button>
          <Button icon={Upload} onClick={confirm} disabled={busy || blocked}>
            {busy ? "Import en cours..." : "Confirmer l'import"}
          </Button>
        </div>
      </>
    );
  }

  return (
    <div>
      <ImportStepper current={step} />
      {error && (
        <Alert tone="danger">
          {error}
          {error.startsWith(NO_JOURNAL) && (
            <>
              {" "}
              <Link href="/comptes" className="font-medium underline">
                Aller à l&apos;écran Comptes
              </Link>
            </>
          )}
        </Alert>
      )}
      {step === 0 && (
        <>
          {fileError && <Alert tone="danger">{fileError}</Alert>}
          <FileDropzone file={file} onFile={chooseFile} disabled={busy} />
          <p className="mt-3 text-sm text-simtis-muted" role={busy ? "status" : undefined}>
            {busy
              ? "Analyse du fichier en cours..."
              : "L'export est analysé dès qu'il est choisi, pour la société active."}
          </p>
          {analysis && analysis.erreurs_mapping.length > 0 && stepMapping(analysis)}
          <div className="mt-6 flex justify-end">
            <Button variant="secondary" onClick={onCancel} disabled={busy}>
              Annuler
            </Button>
          </div>
        </>
      )}
      {step === 1 && analysis && stepValidation(analysis)}
    </div>
  );
}
