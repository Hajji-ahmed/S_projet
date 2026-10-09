"use client";

import { ArrowLeft, CircleAlert, Upload } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { useCompany } from "@/components/company/CompanyProvider";
import { AccountPicker } from "@/components/releves/AccountPicker";
import { CheckAllButtons } from "@/components/releves/CheckAllButtons";
import { EditablePreview, alreadyImported } from "@/components/releves/EditablePreview";
import { blocageImport, defaultChecked } from "@/lib/importLines";
import { FileDropzone, ImportStepper } from "@/components/releves/ImportSteps";
import { Button } from "@/components/ui/Button";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/ErrorState";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { ApiError } from "@/lib/api";
import { businessToday, currencySuffix, normalizeSignedAmountInput } from "@/lib/balances";
import { cn } from "@/lib/cn";
import {
  amountToInput,
  draftFromLine,
  draftToLigne,
  lineMotifs,
  type LineDraft,
} from "@/lib/statementLines";
import { assignField, fieldsByColumn, fileProblem } from "@/lib/statements";
import { listAccounts } from "@/services/accounts";
import { listPointageTypes } from "@/services/referentiel";
import { analyseStatement, confirmStatement } from "@/services/statements";
import type { Account } from "@/types/account";
import type {
  Analysis,
  ColumnMapping,
  Confirmation,
  FieldCode,
  ImportColumn,
  PointageType,
} from "@/types/statement";

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

type ImportWizardProps = {
  companyId: number;
  onDone: (result: Confirmation) => void;
  onCancel: () => void;
};

/**
 * Import d'un relevé en deux étapes : Fichier, puis Validation. Dès que le compte et le fichier
 * sont choisis, l'analyse se lance seule et mène directement à la Validation. La correspondance
 * des colonnes ne s'affiche que si le fichier n'est pas reconnu.
 *
 * La Validation montre le relevé tel qu'il sera enregistré, au format standard, modifiable ligne
 * par ligne, sans ajout de ligne (décision métier du 02/10/2026). Rien n'est enregistré avant
 * « Confirmer l'import » : l'API analyse alors à nouveau le fichier et revérifie chaque ligne.
 */
export function ImportWizard({ companyId, onDone, onCancel }: ImportWizardProps) {
  const { company } = useCompany();
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [accountsError, setAccountsError] = useState(false);
  const [accountId, setAccountId] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [pointages, setPointages] = useState<PointageType[]>([]);

  const [step, setStep] = useState(0);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [mapping, setMapping] = useState<ColumnMapping>({});
  const [feuille, setFeuille] = useState<string | undefined>(undefined);
  // Aperçu modifiable : lignes telles que saisies, telles que lues, cochées, ligne en édition
  const [drafts, setDrafts] = useState<LineDraft[]>([]);
  const [originals, setOriginals] = useState<LineDraft[]>([]);
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [editing, setEditing] = useState<number | null>(null);
  // Fichier sans soldes : solde d'ouverture du calcul, tel que saisi (pré-rempli par la proposition)
  const [ouvertureText, setOuvertureText] = useState("");
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
    // Sans la liste des Pointages, la ligne garde son pointage (sans pointage : « À choisir »)
    listPointageTypes().then(
      (list) => {
        if (!cancelled) setPointages(list);
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  const account = accounts?.find((item) => item.id === accountId);
  const suffix = currencySuffix(analysis?.devise ?? account?.devise ?? "MAD");
  const today = businessToday();

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
      const read = result.lignes.map(draftFromLine);
      setAnalysis(result);
      setOuvertureText(amountToInput(result.solde_ouverture_propose));
      setMapping(result.mapping);
      setFeuille(result.feuille);
      setOriginals(read);
      setDrafts(read);
      // Cochées par défaut (08/10/2026) : valides, en erreur et doublons internes ; jamais une
      // ligne déjà importée. Une ligne en erreur cochée bloque jusqu'à sa correction.
      setChecked(defaultChecked(result.lignes));
      setEditing(null);
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

  function chooseFile(chosen: File) {
    const problem = fileProblem(chosen);
    setFileError(problem);
    setFile(problem ? null : chosen);
    setAnalysis(null);
    if (!problem && accountId !== null) void run(chosen, accountId);
  }

  function changeDraft(next: LineDraft) {
    setDrafts((current) => current.map((draft) => (draft.numero === next.numero ? next : draft)));
    // Une ligne en erreur corrigée se coche d'elle-même
    const line = analysis?.lignes.find((item) => item.numero === next.numero);
    const original = originals.find((draft) => draft.numero === next.numero) ?? next;
    if (line?.statut === "Erreur" && lineMotifs(line, next, original, today).length === 0) {
      setChecked((current) => new Set(current).add(next.numero));
    }
  }

  function toggle(numero: number, value: boolean) {
    setChecked((current) => {
      const next = new Set(current);
      if (value) next.add(numero);
      else next.delete(numero);
      return next;
    });
  }

  function reset(numero: number) {
    const original = originals.find((draft) => draft.numero === numero);
    if (original) changeDraft(original);
  }

  const lines = new Map(analysis?.lignes.map((line) => [line.numero, line]) ?? []);
  const toImport = drafts.filter(
    (draft) => checked.has(draft.numero) && !alreadyImported(lines.get(draft.numero)),
  );
  const originalOf = new Map(originals.map((draft) => [draft.numero, draft]));
  const invalid = toImport.filter(
    (draft) =>
      lineMotifs(lines.get(draft.numero), draft, originalOf.get(draft.numero) ?? draft, today)
        .length > 0,
  );
  // Fichier sans soldes : le solde d'ouverture est obligatoire (saisi ou proposé)
  const ouverture = ouvertureText.trim() ? normalizeSignedAmountInput(ouvertureText) : null;
  const ouvertureManquante = !!analysis?.soldes_calcules && ouverture === null;
  // Raison affichée à côté du bouton quand la confirmation est impossible
  const blocage = blocageImport({
    dejaImporte: !!analysis?.deja_importe,
    cochees: toImport.length,
    erreursCochees: invalid.length,
    ouvertureManquante,
  });
  const blocked = blocage !== null;

  function goToOpening() {
    const input = document.getElementById("releve-solde-ouverture");
    input?.scrollIntoView({ behavior: "smooth", block: "center" });
    input?.focus({ preventScroll: true });
  }

  async function confirm() {
    if (!file || !account || !analysis || blocked) return;
    setBusy(true);
    setError(null);
    try {
      onDone(
        await confirmStatement(
          {
            file,
            accountId: account.id,
            mapping,
            feuille,
            // Solde verrouillé (banque ou relevé précédent) : le serveur le retrouve seul
            soldeOuverture:
              analysis.soldes_calcules && analysis.solde_ouverture_modifiable !== false
                ? (ouverture ?? undefined)
                : undefined,
          },
          { lignes: toImport.map(draftToLigne) },
        ),
      );
    } catch (caught) {
      setError(errorMessage(caught));
      setBusy(false);
    }
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

  // --- Étape 2 : validation (aperçu au format standard, modifiable) ------------------------------

  function stepValidation(current: Analysis) {
    return (
      <>
        {current.deja_importe && (
          <Alert tone="danger">Ce fichier a déjà été importé pour cette société.</Alert>
        )}
        <p className="mb-4 text-sm text-simtis-muted">
          {current.fichier_nom} · compte {current.bank_code} {current.devise} · le relevé tel
          qu&apos;il sera enregistré : corrigez une ligne avec le crayon, décochez celles à ne pas
          importer.
        </p>
        {sheetPicker(current)}
        {current.soldes_calcules && (
          <div className="mb-4 flex flex-wrap items-end gap-4 rounded-[12px] border border-simtis-border bg-simtis-background px-4 py-3">
            <div className="w-full max-w-[240px]">
              <Field
                label="Solde d'ouverture"
                htmlFor="releve-solde-ouverture"
                required
                error={
                  ouvertureText.trim() && ouverture === null
                    ? "Montant illisible (ex. 5 000 000 ou -1 250,50)."
                    : ouvertureManquante
                      ? "Obligatoire pour importer ce fichier."
                      : undefined
                }
              >
                <TextInput
                  id="releve-solde-ouverture"
                  value={ouvertureText}
                  inputMode="decimal"
                  placeholder="À saisir"
                  disabled={current.solde_ouverture_modifiable === false}
                  onChange={(event) => setOuvertureText(event.target.value)}
                />
              </Field>
            </div>
            <p className="max-w-xl pb-2 text-sm text-simtis-muted">
              Ce fichier n&apos;a pas de soldes : chaque solde est calculé (solde précédent − débit
              + crédit) à partir de ce solde d&apos;ouverture.{" "}
              {current.solde_ouverture_modifiable === false
                ? `Repris automatiquement : ${current.solde_ouverture_source?.toLowerCase()} (il ne se modifie pas après le premier import).`
                : current.solde_ouverture_source && current.solde_ouverture_propose !== null
                  ? `Proposé : ${current.solde_ouverture_source.toLowerCase()} (premier import : modifiable).`
                  : "Premier import de ce compte, aucun solde connu : saisissez-le."}
            </p>
            {current.solde_ouverture_avertissement && (
              <p
                role="alert"
                className="flex w-full items-start gap-2 rounded-lg bg-simtis-warning-bg px-3 py-2 text-sm text-simtis-warning-fg"
              >
                <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                {current.solde_ouverture_avertissement}
              </p>
            )}
          </div>
        )}
        <CheckAllButtons
          checked={checked.size}
          total={defaultChecked(current.lignes).size}
          onCheckAll={() => setChecked(defaultChecked(current.lignes))}
          onUncheckAll={() => setChecked(new Set())}
        />
        <EditablePreview
          ouverture={ouverture}
          analysis={current}
          societe={company?.nom ?? ""}
          logo={account?.bank_logo}
          suffix={suffix}
          pointages={pointages}
          drafts={drafts}
          originals={originals}
          checked={checked}
          editing={editing}
          today={today}
          onChange={changeDraft}
          onToggle={toggle}
          onEdit={setEditing}
          onReset={reset}
        />
        <p
          className={cn(
            "mt-4 flex flex-wrap items-center gap-x-2 text-sm",
            blocage ? "font-medium text-simtis-danger-fg" : "text-simtis-muted",
          )}
          aria-live="polite"
        >
          {blocage ? (
            <>
              <CircleAlert className="h-4 w-4 shrink-0" aria-hidden />
              {blocage.message}
              {blocage.raison === "ouverture" && (
                <button
                  type="button"
                  onClick={goToOpening}
                  className="text-simtis-primary underline underline-offset-2 hover:text-simtis-primary-dark"
                >
                  Saisir le solde d&apos;ouverture
                </button>
              )}
            </>
          ) : (
            `${toImport.length} opération${toImport.length > 1 ? "s" : ""} seront enregistrée${toImport.length > 1 ? "s" : ""} sur le compte ${current.bank_code} ${current.devise}.`
          )}
        </p>
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
