"use client";

import { ArrowLeft, CircleAlert, Upload } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { AccountPicker } from "@/components/releves/AccountPicker";
import { FileDropzone, ImportStepper } from "@/components/releves/ImportSteps";
import { Button } from "@/components/ui/Button";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/ErrorState";
import { Field, Select } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api";
import { currencySuffix, formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import { assignField, fieldsByColumn, fileProblem } from "@/lib/statements";
import { listAccounts } from "@/services/accounts";
import { analyseStatement, confirmStatement } from "@/services/statements";
import type { Account } from "@/types/account";
import type {
  AnalysedLine,
  Analysis,
  ColumnMapping,
  Confirmation,
  FieldCode,
  ImportColumn,
  LineStatus,
} from "@/types/statement";

/** Lignes affichées au plus dans l'aperçu (un relevé peut en compter 5 000). */
const PREVIEW_LIMIT = 500;

type Filter = "Toutes" | LineStatus;

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

function Tile({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-[12px] border border-simtis-border bg-simtis-card px-4 py-3">
      <p className="text-xs text-simtis-muted">{label}</p>
      <p className={cn("mt-1 text-2xl font-semibold tabular-nums", tone)}>{value}</p>
    </div>
  );
}

type ImportWizardProps = {
  companyId: number;
  onDone: (result: Confirmation) => void;
  onCancel: () => void;
};

/**
 * Import d'un relevé en deux étapes : Fichier, puis Validation. Dès que le compte et le fichier
 * sont choisis, l'analyse se lance seule et mène directement à la Validation. La correspondance
 * des colonnes ne s'affiche que si le fichier n'est pas reconnu (décision métier du 02/10/2026).
 * Rien n'est enregistré avant « Confirmer l'import » ; l'API analyse alors à nouveau le fichier.
 */
export function ImportWizard({ companyId, onDone, onCancel }: ImportWizardProps) {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [accountsError, setAccountsError] = useState(false);
  const [accountId, setAccountId] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  const [step, setStep] = useState(0);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [mapping, setMapping] = useState<ColumnMapping>({});
  const [feuille, setFeuille] = useState<string | undefined>(undefined);
  const [keep, setKeep] = useState<number[]>([]);
  const [ecarter, setEcarter] = useState(false);
  const [filter, setFilter] = useState<Filter>("Toutes");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listAccounts(companyId, { actif: true }).then(
      (list) => {
        if (!cancelled) setAccounts(list);
      },
      () => {
        if (!cancelled) setAccountsError(true);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  const account = accounts?.find((item) => item.id === accountId);
  const suffix = currencySuffix(analysis?.devise ?? account?.devise ?? "MAD");

  /**
   * Analyse le fichier. Colonnes reconnues : directement la Validation. Sinon on reste sur l'étape
   * Fichier, où la correspondance des colonnes s'affiche.
   */
  async function run(
    chosenFile: File,
    chosenAccount: number,
    options: { mapping?: ColumnMapping; feuille?: string } = {},
  ) {
    setBusy(true);
    setError(null);
    try {
      const result = await analyseStatement({
        file: chosenFile,
        accountId: chosenAccount,
        mapping: options.mapping,
        feuille: options.feuille,
      });
      setAnalysis(result);
      setMapping(result.mapping);
      setFeuille(result.feuille);
      setKeep([]);
      setEcarter(false);
      setFilter("Toutes");
      setStep(result.erreurs_mapping.length > 0 ? 0 : 1);
    } catch (caught) {
      setAnalysis(null);
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  function chooseAccount(id: number) {
    setAccountId(id);
    setAnalysis(null);
    if (file) void run(file, id);
  }

  async function confirm() {
    if (!file || !account || !analysis) return;
    setBusy(true);
    setError(null);
    try {
      onDone(
        await confirmStatement(
          { file, accountId: account.id, mapping, feuille },
          { garderDoublons: keep, ecarterErreurs: ecarter },
        ),
      );
    } catch (caught) {
      setError(errorMessage(caught));
      setBusy(false);
    }
  }

  function chooseFile(chosen: File) {
    const problem = fileProblem(chosen);
    setFileError(problem);
    setFile(problem ? null : chosen);
    setAnalysis(null);
    if (!problem && accountId !== null) void run(chosen, accountId);
  }

  // --- Étape 1 : compte et fichier (analyse automatique) -----------------------------------------

  function stepFile() {
    if (accountsError) return <ErrorState message="Impossible de charger les comptes." />;
    if (accounts === null) return <LoadingState rows={2} />;
    return (
      <div className="grid gap-5 lg:grid-cols-[minmax(0,340px)_1fr]">
        <div className="space-y-4">
          <Field
            label="Compte du relevé"
            htmlFor="releve-compte"
            required
            hint={accounts.length === 0 ? "Aucun compte actif pour cette société." : undefined}
          >
            <AccountPicker
              id="releve-compte"
              value={accountId}
              onChange={chooseAccount}
              disabled={busy}
              placeholder="Sélectionner un compte"
              options={accounts.map((item) => ({
                id: item.id,
                bankCode: item.bank_code,
                logo: item.bank_logo,
                label: `${item.bank_code} · ${item.type_compte === "DH convertible" ? "DH convertible" : item.devise} · ${item.libelle}`,
              }))}
            />
          </Field>
          <p className="text-xs text-simtis-muted">
            Le compte fixe la société et la banque du relevé. Le fichier est analysé dès qu&apos;il
            est choisi : ses colonnes sont reconnues, ou reprises du dernier import de la même
            banque.
          </p>
        </div>
        <div>
          {fileError && <Alert tone="danger">{fileError}</Alert>}
          <FileDropzone file={file} onFile={chooseFile} disabled={busy} />
          {busy && (
            <p role="status" className="mt-3 text-sm text-simtis-muted">
              Analyse du fichier en cours...
            </p>
          )}
          {!busy && file && accountId === null && (
            <p className="mt-3 text-sm text-simtis-muted">
              Choisissez le compte du relevé pour lancer l&apos;analyse.
            </p>
          )}
        </div>
      </div>
    );
  }

  // --- Secours : colonnes non reconnues -----------------------------------------------------------

  function stepMapping(current: Analysis) {
    const byColumn = fieldsByColumn(mapping);
    const options = current.champs.map((champ) => ({
      value: champ.code,
      label: champ.obligatoire ? `${champ.libelle} (obligatoire)` : champ.libelle,
    }));
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
              id={`champ-${column.index}`}
              aria-label={`Champ SIMTIS de la colonne ${column.lettre}`}
              value={byColumn[column.index] ?? ""}
              placeholder="Ignorer cette colonne"
              options={options}
              onChange={(event) =>
                setMapping((value) =>
                  assignField(
                    value,
                    column.index,
                    (event.target.value || null) as FieldCode | null,
                  ),
                )
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
          colonne utile à son champ, une seule fois : la correspondance sera reprise automatiquement
          au prochain relevé {current.bank_code}.
        </p>
        {sheetPicker(current)}
        <Alert tone="warning">
          <ul className="space-y-0.5">
            {current.erreurs_mapping.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </Alert>
        <DataTable
          columns={columns}
          rows={current.colonnes}
          getRowKey={(column) => String(column.index)}
        />
        <div className="mt-4 flex justify-end">
          <Button
            onClick={() => file && accountId !== null && run(file, accountId, { mapping, feuille })}
            disabled={busy}
          >
            {busy ? "Analyse en cours..." : "Valider les colonnes"}
          </Button>
        </div>
      </section>
    );
  }

  /** Choix de la feuille, seulement pour un classeur qui en a plusieurs. */
  function sheetPicker(current: Analysis) {
    if (current.feuilles.length < 2) return null;
    return (
      <div className="mb-4 w-full max-w-xs">
        <Field label="Feuille" htmlFor="releve-feuille">
          <Select
            id="releve-feuille"
            value={current.feuille}
            disabled={busy}
            options={current.feuilles.map((name) => ({ value: name, label: name }))}
            onChange={(event) =>
              file && accountId !== null && run(file, accountId, { feuille: event.target.value })
            }
          />
        </Field>
      </div>
    );
  }

  // --- Étape 3 : validation -----------------------------------------------------------------------

  function stepValidation(current: Analysis) {
    const { resume } = current;
    const visible = current.lignes.filter((line) => filter === "Toutes" || line.statut === filter);
    const columns: Column<AnalysedLine>[] = [
      { key: "numero", header: "Ligne", render: (line) => line.numero },
      { key: "statut", header: "Statut", render: (line) => <StatusBadge status={line.statut} /> },
      {
        key: "date_operation",
        header: "Date",
        render: (line) => (
          <span className="whitespace-nowrap">{formatDate(line.date_operation)}</span>
        ),
      },
      {
        key: "libelle",
        header: "Libellé",
        render: (line) => (
          <span>
            <span className="block">{line.libelle ?? "-"}</span>
            {line.reference && (
              <span className="block text-xs text-simtis-muted">Réf. {line.reference}</span>
            )}
          </span>
        ),
      },
      {
        key: "debit",
        header: "Débit",
        align: "right",
        render: (line) => formatAmount(line.debit, suffix, { dashForZero: true }),
      },
      {
        key: "credit",
        header: "Crédit",
        align: "right",
        render: (line) => formatAmount(line.credit, suffix, { dashForZero: true }),
      },
      {
        key: "solde",
        header: "Solde",
        align: "right",
        render: (line) => formatAmount(line.solde, suffix),
      },
      {
        key: "motifs",
        header: "Motif",
        render: (line) =>
          line.doublon_de !== null ? (
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 accent-simtis-primary"
                checked={keep.includes(line.numero)}
                onChange={(event) =>
                  setKeep((value) =>
                    event.target.checked
                      ? [...value, line.numero]
                      : value.filter((numero) => numero !== line.numero),
                  )
                }
                aria-label={`Garder la ligne ${line.numero}`}
              />
              <span>{line.motifs.join(" ")} Cochez pour la garder.</span>
            </label>
          ) : (
            <span className={cn(line.statut === "Erreur" && "text-simtis-danger-fg")}>
              {line.motifs.join(" ") || "-"}
            </span>
          ),
      },
    ];

    const toImport = resume.nb_valides + keep.length;
    const blocked = current.deja_importe || toImport === 0 || (resume.nb_erreurs > 0 && !ecarter);

    return (
      <>
        {current.deja_importe && (
          <Alert tone="danger">Ce fichier a déjà été importé pour cette société.</Alert>
        )}
        {resume.soldes_coherents === false && (
          <Alert tone="warning">
            Les mouvements du relevé ne retrouvent pas son solde de clôture : vérifiez le fichier.
          </Alert>
        )}
        <p className="mb-4 text-sm text-simtis-muted">
          {current.fichier_nom} · compte {current.bank_code} {current.devise}
        </p>
        {sheetPicker(current)}
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Tile label="Lignes valides" value={resume.nb_valides} tone="text-simtis-success" />
          <Tile label="Lignes en erreur" value={resume.nb_erreurs} tone="text-simtis-danger" />
          <Tile label="Doublons" value={resume.nb_doublons} tone="text-simtis-warning" />
          <Tile label="Lignes ignorées" value={resume.nb_ignorees} tone="text-simtis-muted" />
        </div>
        <dl className="mb-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-simtis-muted">Période</dt>
            <dd className="font-medium">
              {resume.periode_debut
                ? `${formatDate(resume.periode_debut)} au ${formatDate(resume.periode_fin)}`
                : "-"}
            </dd>
          </div>
          <div>
            <dt className="text-simtis-muted">Total débit / crédit (lignes valides)</dt>
            <dd className="font-medium tabular-nums">
              {formatAmount(resume.total_debit, suffix)} /{" "}
              {formatAmount(resume.total_credit, suffix)}
            </dd>
          </div>
          <div>
            <dt className="text-simtis-muted">Solde d&apos;ouverture</dt>
            <dd className="font-medium tabular-nums">
              {formatAmount(resume.solde_ouverture, suffix)}
            </dd>
          </div>
          <div>
            <dt className="text-simtis-muted">Solde de clôture</dt>
            <dd className="font-medium tabular-nums">
              {formatAmount(resume.solde_cloture, suffix)}
            </dd>
          </div>
        </dl>

        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div className="w-full max-w-[220px]">
            <Field label="Afficher" htmlFor="releve-filtre">
              <Select
                id="releve-filtre"
                value={filter}
                onChange={(event) => setFilter(event.target.value as Filter)}
                options={[
                  { value: "Toutes", label: `Toutes les lignes (${resume.nb_lignes})` },
                  { value: "Valide", label: `Valides (${resume.nb_valides})` },
                  { value: "Erreur", label: `En erreur (${resume.nb_erreurs})` },
                  { value: "Doublon", label: `Doublons (${resume.nb_doublons})` },
                ]}
              />
            </Field>
          </div>
          {resume.nb_erreurs > 0 && (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4 accent-simtis-primary"
                checked={ecarter}
                onChange={(event) => setEcarter(event.target.checked)}
              />
              Écarter les {resume.nb_erreurs} ligne{resume.nb_erreurs > 1 ? "s" : ""} en erreur et
              importer les autres
            </label>
          )}
        </div>
        <DataTable
          columns={columns}
          rows={visible.slice(0, PREVIEW_LIMIT)}
          getRowKey={(line) => String(line.numero)}
          emptyMessage="Aucune ligne dans cette sélection."
        />
        {visible.length > PREVIEW_LIMIT && (
          <p className="mt-2 text-xs text-simtis-muted">
            {PREVIEW_LIMIT} premières lignes affichées sur {visible.length}.
          </p>
        )}
        <p className="mt-4 text-sm text-simtis-muted">
          {blocked && resume.nb_erreurs > 0 && !ecarter
            ? "Corrigez le fichier, ou cochez « Écarter les lignes en erreur » pour importer les autres."
            : `${toImport} opération${toImport > 1 ? "s" : ""} seront enregistrée${toImport > 1 ? "s" : ""} sur le compte ${current.bank_code} ${current.devise}.`}
        </p>
        <div className="sr-only" aria-live="polite">
          {blocked ? "Import impossible en l'état." : "Import prêt à être confirmé."}
        </div>
        <FooterButtons>
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
        </FooterButtons>
      </>
    );
  }

  return (
    <div>
      <ImportStepper current={step} />
      {error && <Alert tone="danger">{error}</Alert>}

      {step === 0 && (
        <>
          {stepFile()}
          {analysis && analysis.erreurs_mapping.length > 0 && stepMapping(analysis)}
          <FooterButtons>
            <Button variant="secondary" onClick={onCancel} disabled={busy}>
              Annuler
            </Button>
          </FooterButtons>
        </>
      )}

      {step === 1 && analysis && stepValidation(analysis)}
    </div>
  );
}

function FooterButtons({ children }: { children: ReactNode }) {
  return <div className="mt-6 flex flex-wrap justify-end gap-3">{children}</div>;
}
