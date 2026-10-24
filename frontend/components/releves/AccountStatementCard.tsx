"use client";

import { EnCoursBadge } from "@/components/releves/EnCoursBadge";
import { ChevronUp, Download, ListOrdered, PenLine, Plus, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { CodeBadge } from "@/components/rapprochement/CodeBadge";
import { DeleteImportModal } from "@/components/imports/DeleteImportModal";
import { ManualOperationModal } from "@/components/releves/ManualOperationModal";
import { TransactionEditModal } from "@/components/releves/TransactionEditModal";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/ErrorState";
import { DateInput, Field, Select, TextInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api";
import { currencySuffix, formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import {
  commentaireAEnregistrer,
  OPERATIONS_AFFICHEES,
  exportFilename,
  saveFile,
  showLast,
  type Period,
} from "@/lib/statements";
import { fromCents, toCents } from "@/lib/statementLines";
import { listPointageTypes } from "@/services/referentiel";
import {
  exportAccountStatement,
  getAccountStatement,
  updateTransaction,
  supprimerEnCours,
  supprimerOperation,
} from "@/services/statements";
import type { AccountStatement, PointageType, Transaction } from "@/types/statement";
import type { Status } from "@/types/status";

type LoadState = "loading" | "error" | "ready";

/** Compte qui a au moins un relevé importé (tiré du journal des imports). */
export type StatementAccount = {
  bank_account_id: number;
  bank_code: string;
  devise: string;
  compte_numero: string;
};

type AccountStatementCardProps = {
  accounts: StatementAccount[];
  selectedId: number;
  onSelect: (accountId: number) => void;
  logos: Map<string, string | null>;
  /** Incrémenté après un import : le relevé est rechargé avec ses nouvelles lignes. */
  reloadKey: number;
  /** Modification des champs métier (permission statements.import : Trésorerie). */
  canEdit: boolean;
};

/**
 * Relevé continu d'un compte : toutes ses opérations importées, quel que soit le fichier, au
 * format standard. Chaque nouvel import s'ajoute à la suite (décision métier du 02/10/2026).
 */
export function AccountStatementCard({
  accounts,
  selectedId,
  onSelect,
  logos,
  reloadKey,
  canEdit,
}: AccountStatementCardProps) {
  const { toast } = useToast();
  const [period, setPeriod] = useState<Period>({});
  const [data, setData] = useState<AccountStatement | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [retryKey, setRetryKey] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [pointages, setPointages] = useState<PointageType[]>([]);
  const [editing, setEditing] = useState<Transaction | null>(null);
  // Saisie et suppression manuelles (24/10/2026)
  const [ajout, setAjout] = useState(false);
  const [ligneASupprimer, setLigneASupprimer] = useState<Transaction | null>(null);
  // Nombre d'opérations affichées : les plus anciennes restent masquées jusqu'au clic
  const [shown, setShown] = useState(OPERATIONS_AFFICHEES);
  // Opérations en cours (21/10/2026) : filtre, sélection et suppression avant le relevé suivant
  const [enCoursSeules, setEnCoursSeules] = useState(false);
  const [aSupprimer, setASupprimer] = useState<Set<number>>(new Set());
  const [confirmation, setConfirmation] = useState(false);
  const [suppression, setSuppression] = useState(false);

  // Liste de choix de la fenêtre de modification (seulement pour qui peut modifier)
  useEffect(() => {
    if (!canEdit) return;
    let cancelled = false;
    listPointageTypes().then(
      (list) => {
        if (!cancelled) setPointages(list);
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [canEdit]);

  function replaceOperation(updated: Transaction) {
    setData((current) =>
      current
        ? {
            ...current,
            operations: current.operations.map((row) => (row.id === updated.id ? updated : row)),
          }
        : current,
    );
    setEditing(null);
  }

  useEffect(() => {
    let cancelled = false;
    getAccountStatement(selectedId, period).then(
      (result) => {
        if (cancelled) return;
        setData(result);
        // Autre compte, autre période ou nouvel import : retour aux dernières opérations
        setShown(OPERATIONS_AFFICHEES);
        setASupprimer(new Set());
        setState("ready");
      },
      () => {
        if (!cancelled) setState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [selectedId, period, reloadKey, retryKey]);

  // Pointage et commentaire modifiés directement dans le tableau, enregistrés aussitôt (10/10/2026)
  async function saveInline(
    row: Transaction,
    changes: { pointage_type_id?: number | null; commentaire?: string | null },
    message: string,
  ) {
    try {
      replaceOperation(
        await updateTransaction(row.id, {
          pointage_type_id: row.pointage_type_id,
          lettrage_escompte: row.lettrage_escompte,
          commentaire: row.commentaire,
          ...changes,
        }),
      );
      toast(message);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Enregistrement impossible.", "error");
    }
  }

  function changePeriod(next: Period) {
    setState("loading");
    setPeriod(next);
  }

  async function download() {
    if (!data) return;
    setExporting(true);
    try {
      saveFile(await exportAccountStatement(selectedId, period), exportFilename(data));
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Export impossible.", "error");
    } finally {
      setExporting(false);
    }
  }

  const enCours = (data?.operations ?? []).filter((row) => row.en_cours && !row.remplacee);
  const totalASupprimer = enCours
    .filter((row) => aSupprimer.has(row.id))
    .reduce((total, row) => total + toCents(row.montant), BigInt(0));

  async function confirmerSuppression() {
    setSuppression(true);
    try {
      const { nb } = await supprimerEnCours([...aSupprimer]);
      toast(`${nb} opération${nb > 1 ? "s" : ""} en cours supprimée${nb > 1 ? "s" : ""}.`);
      setConfirmation(false);
      setState("loading");
      setRetryKey((key) => key + 1);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Suppression impossible.", "error");
    } finally {
      setSuppression(false);
    }
  }

  const devise = data?.devise ?? accounts.find((a) => a.bank_account_id === selectedId)?.devise;
  const suffix = currencySuffix(devise ?? "MAD");
  const logo = data ? logos.get(data.bank_code) : undefined;
  // Seul le tableau est raccourci : le résumé et l'export portent sur tout le relevé
  const visible = showLast(
    enCoursSeules ? enCours : (data?.operations ?? []),
    shown,
    OPERATIONS_AFFICHEES,
  );

  // Les 11 colonnes du relevé standard, dans leur ordre, puis le statut de rapprochement
  const columns: Column<Transaction>[] = [
    ...(canEdit && enCoursSeules
      ? [
          {
            key: "choix",
            header: "",
            render: (row: Transaction) => (
              <input
                type="checkbox"
                aria-label={`Choisir l'opération en cours du ${formatDate(row.date_operation)} ${row.libelle}`}
                className="h-4 w-4 accent-simtis-primary"
                checked={aSupprimer.has(row.id)}
                disabled={row.statut !== "Non rapprochée"}
                onChange={() =>
                  setASupprimer((ids) => {
                    const suivants = new Set(ids);
                    if (suivants.has(row.id)) suivants.delete(row.id);
                    else suivants.add(row.id);
                    return suivants;
                  })
                }
              />
            ),
          } satisfies Column<Transaction>,
        ]
      : []),
    { key: "societe", header: "Société" },
    {
      key: "pointage",
      header: "Pointage",
      render: (row) =>
        canEdit ? (
          <Select
            aria-label={`Pointage de l'opération du ${formatDate(row.date_operation)} ${row.libelle}`}
            className="h-9 min-w-[150px]"
            value={row.pointage_type_id === null ? "" : String(row.pointage_type_id)}
            placeholder="À choisir"
            options={pointages.map((item) => ({ value: String(item.id), label: item.libelle }))}
            onChange={(event) =>
              saveInline(
                row,
                { pointage_type_id: event.target.value ? Number(event.target.value) : null },
                "Pointage enregistré.",
              )
            }
          />
        ) : (
          (row.pointage ?? "À choisir")
        ),
    },
    {
      key: "banque",
      header: "Banque",
      render: (row) => <BankLabel code={row.banque} logo={logo} />,
    },
    {
      key: "date_operation",
      header: "Date d'opération",
      render: (row) => <span className="whitespace-nowrap">{formatDate(row.date_operation)}</span>,
    },
    {
      key: "date_valeur",
      header: "Date de valeur",
      render: (row) => <span className="whitespace-nowrap">{formatDate(row.date_valeur)}</span>,
    },
    {
      key: "libelle",
      header: "Libellé",
      // Largeur minimale : avec les 12 colonnes du format standard, le libellé serait écrasé
      render: (row) => (
        <span className="block min-w-[300px] break-words">
          <span className="block">{row.libelle}</span>
          {row.reference && (
            <span className="block text-xs text-simtis-muted">Réf. {row.reference}</span>
          )}
          {row.origine === "Manuelle" && (
            <span className="block text-xs font-medium text-simtis-warning-fg">
              Saisie manuelle
            </span>
          )}
          {row.origine === "Corrigée" && (
            <span className="block text-xs font-medium text-simtis-primary">
              corrigée avant l&apos;import
            </span>
          )}
          {row.en_cours && <EnCoursBadge remplacee={row.remplacee} />}
        </span>
      ),
    },
    {
      key: "debit",
      header: "Débit",
      align: "right",
      render: (row) => formatAmount(row.debit, suffix, { dashForZero: true }),
    },
    {
      key: "credit",
      header: "Crédit",
      align: "right",
      render: (row) => formatAmount(row.credit, suffix, { dashForZero: true }),
    },
    {
      key: "solde",
      header: "Solde",
      align: "right",
      render: (row) => formatAmount(row.solde, suffix),
    },
    {
      key: "lettrage_escompte",
      header: "Lettrage / Escompte",
      render: (row) => row.lettrage_escompte ?? "-",
    },
    {
      key: "commentaire",
      header: "Commentaire",
      render: (row) =>
        canEdit ? (
          <TextInput
            // Recréé après chaque enregistrement : le champ repart de la valeur enregistrée
            key={`${row.id}-${row.commentaire ?? ""}`}
            aria-label={`Commentaire de l'opération du ${formatDate(row.date_operation)} ${row.libelle}`}
            className="h-9 min-w-[180px]"
            defaultValue={row.commentaire ?? ""}
            maxLength={1000}
            placeholder="Ajouter un commentaire"
            onKeyDown={(event) => {
              if (event.key === "Enter") event.currentTarget.blur();
            }}
            onBlur={(event) => {
              const valeur = commentaireAEnregistrer(row.commentaire, event.target.value);
              if (valeur !== undefined) {
                void saveInline(row, { commentaire: valeur }, "Commentaire enregistré.");
              }
            }}
          />
        ) : (
          (row.commentaire ?? "-")
        ),
    },
    {
      key: "statut",
      header: "Statut",
      render: (row) => <StatusBadge status={row.statut as Status} />,
    },
    {
      key: "code_rapprochement",
      header: "Code rapprochement",
      render: (row) => <CodeBadge code={row.code_rapprochement} />,
    },
  ];
  if (canEdit) {
    columns.push({
      key: "actions",
      header: "Actions",
      align: "right",
      render: (row) => (
        <span className="inline-flex gap-1">
          <button
            type="button"
            onClick={() => setEditing(row)}
            aria-label={`Modifier l'opération du ${formatDate(row.date_operation)} ${row.libelle}`}
            title="Modifier Lettrage / Escompte (et Pointage, Commentaire)"
            className="rounded-lg p-2 text-simtis-muted transition-colors hover:bg-simtis-light hover:text-simtis-primary"
          >
            <PenLine className="h-4 w-4" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => setLigneASupprimer(row)}
            disabled={row.statut === "Rapprochée"}
            aria-label={`Supprimer l'opération du ${formatDate(row.date_operation)} ${row.libelle}`}
            title={
              row.statut === "Rapprochée"
                ? "Opération rapprochée : annulez d'abord son rapprochement"
                : "Supprimer cette opération"
            }
            className="rounded-lg p-2 text-simtis-danger-fg transition-colors hover:bg-simtis-danger-bg disabled:pointer-events-none disabled:opacity-40"
          >
            <Trash2 className="h-4 w-4" aria-hidden />
          </button>
        </span>
      ),
    });
  }

  return (
    <Card title="Relevés par compte" icon={ListOrdered}>
      {/* Une seule ligne : faute de place (mobile, comptes nombreux), la rangée défile seule */}
      <div
        className="mb-4 flex gap-2 overflow-x-auto pb-1"
        role="group"
        aria-label="Compte affiché"
      >
        {accounts.map((account) => {
          const active = account.bank_account_id === selectedId;
          return (
            <button
              key={account.bank_account_id}
              type="button"
              aria-pressed={active}
              onClick={() => {
                if (active) return;
                setState("loading");
                onSelect(account.bank_account_id);
              }}
              className={cn(
                "flex shrink-0 flex-col items-start gap-0.5 rounded-[10px] border px-3 py-2 text-left text-sm font-medium transition-colors duration-200",
                active
                  ? "border-simtis-primary bg-simtis-light text-simtis-primary-dark"
                  : "border-simtis-border bg-simtis-card text-simtis-text hover:bg-simtis-light/50",
              )}
            >
              <BankLabel code={account.bank_code} logo={logos.get(account.bank_code)}>
                {account.bank_code} · {account.devise}
              </BankLabel>
              <span className="text-xs font-normal whitespace-nowrap text-simtis-muted tabular-nums">
                {account.compte_numero}
              </span>
            </button>
          );
        })}
      </div>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-full max-w-[180px]">
          <Field label="Du" htmlFor="releve-du">
            <DateInput
              id="releve-du"
              value={period.from ?? ""}
              onChange={(event) => changePeriod({ ...period, from: event.target.value })}
            />
          </Field>
        </div>
        <div className="w-full max-w-[180px]">
          <Field label="Au" htmlFor="releve-au">
            <DateInput
              id="releve-au"
              value={period.to ?? ""}
              onChange={(event) => changePeriod({ ...period, to: event.target.value })}
            />
          </Field>
        </div>
        {(period.from || period.to) && (
          <Button variant="ghost" icon={X} onClick={() => changePeriod({})}>
            Tout l&apos;historique
          </Button>
        )}
        <div className="ml-auto">
          <Button
            variant="secondary"
            icon={Download}
            onClick={download}
            disabled={exporting || state !== "ready" || !data || data.nb_operations === 0}
            aria-label="Exporter le relevé du compte au format standard"
          >
            {exporting ? "Export..." : "Exporter"}
          </Button>
        </div>
      </div>

      {state === "loading" && <LoadingState rows={5} />}
      {state === "error" && (
        <ErrorState
          message="Impossible de charger le relevé de ce compte."
          onRetry={() => {
            setState("loading");
            setRetryKey((key) => key + 1);
          }}
        />
      )}
      {state === "ready" && data && (
        <>
          <dl
            className="mb-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-5"
            aria-label="Résumé du relevé"
          >
            <div>
              <dt className="text-simtis-muted">Période</dt>
              <dd className="font-medium">
                {data.periode_debut
                  ? `${formatDate(data.periode_debut)} au ${formatDate(data.periode_fin)}`
                  : "-"}
              </dd>
            </div>
            <div>
              <dt className="text-simtis-muted">Opérations</dt>
              <dd className="font-medium tabular-nums">{data.nb_operations}</dd>
            </div>
            <div>
              <dt className="text-simtis-muted">Total débit / crédit</dt>
              <dd className="font-medium tabular-nums">
                {formatAmount(data.total_debit, suffix)} / {formatAmount(data.total_credit, suffix)}
              </dd>
            </div>
            <div>
              <dt className="text-simtis-muted">Solde d&apos;ouverture</dt>
              <dd className="font-medium tabular-nums">
                {formatAmount(data.solde_ouverture, suffix)}
              </dd>
            </div>
            <div>
              <dt className="text-simtis-muted">Solde de clôture</dt>
              <dd className="font-medium text-simtis-primary tabular-nums">
                {formatAmount(data.solde_cloture, suffix)}
              </dd>
            </div>
          </dl>
          <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
            {canEdit && (
              <Button variant="secondary" icon={Plus} onClick={() => setAjout(true)}>
                Ajouter une opération
              </Button>
            )}
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                className="h-4 w-4 accent-simtis-primary"
                checked={enCoursSeules}
                onChange={(event) => {
                  setEnCoursSeules(event.target.checked);
                  setShown(OPERATIONS_AFFICHEES);
                  setASupprimer(new Set());
                }}
              />
              Opérations en cours seulement ({enCours.length})
            </label>
            {canEdit && enCoursSeules && enCours.length > 0 && (
              <>
                <Button
                  variant="ghost"
                  onClick={() =>
                    setASupprimer(
                      new Set(
                        enCours.filter((r) => r.statut === "Non rapprochée").map((r) => r.id),
                      ),
                    )
                  }
                >
                  Tout cocher
                </Button>
                <Button
                  variant="ghost"
                  icon={X}
                  disabled={aSupprimer.size === 0}
                  onClick={() => setASupprimer(new Set())}
                >
                  Tout décocher
                </Button>
                <Button
                  variant="danger"
                  icon={Trash2}
                  disabled={aSupprimer.size === 0}
                  onClick={() => setConfirmation(true)}
                >
                  Supprimer la sélection ({aSupprimer.size})
                </Button>
              </>
            )}
          </div>
          {visible.hidden > 0 && (
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm">
              <p className="text-simtis-muted">
                {visible.rows.length} dernières opérations sur {data.operations.length}
              </p>
              <Button
                variant="ghost"
                icon={ChevronUp}
                onClick={() => setShown((count) => count + OPERATIONS_AFFICHEES)}
                className="h-auto min-h-10 px-0 whitespace-normal"
              >
                Afficher {visible.next}{" "}
                {visible.next > 1 ? "opérations plus anciennes" : "opération plus ancienne"}
              </Button>
            </div>
          )}
          <DataTable
            columns={columns}
            rows={visible.rows}
            getRowKey={(row) => String(row.id)}
            emptyMessage="Aucune opération sur cette période."
          />
        </>
      )}
      <Modal
        open={confirmation}
        onClose={() => setConfirmation(false)}
        title="Supprimer les opérations en cours"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmation(false)}>
              Retour
            </Button>
            <Button
              variant="danger"
              icon={Trash2}
              disabled={suppression}
              onClick={confirmerSuppression}
            >
              Supprimer ({aSupprimer.size})
            </Button>
          </>
        }
      >
        <p className="text-simtis-muted">
          {aSupprimer.size} opération{aSupprimer.size > 1 ? "s" : ""} en cours, total{" "}
          <span className="font-medium text-simtis-text tabular-nums">
            {formatAmount(fromCents(totalASupprimer), suffix)}
          </span>
          . À faire avant d&apos;importer le relevé suivant, qui contient leurs opérations
          définitives. La suppression est tracée dans l&apos;Historique.
        </p>
      </Modal>
      {ajout && selectedId !== undefined && (
        <ManualOperationModal
          accountId={selectedId}
          compte={(() => {
            const compte = accounts.find((a) => a.bank_account_id === selectedId);
            return compte ? `${compte.bank_code} · ${compte.devise} · ${compte.compte_numero}` : "";
          })()}
          pointages={pointages}
          onClose={() => setAjout(false)}
          onSaved={() => {
            setAjout(false);
            toast("Opération ajoutée au relevé.");
            setState("loading");
            setRetryKey((key) => key + 1);
          }}
        />
      )}
      {ligneASupprimer && (
        <DeleteImportModal
          titre="Supprimer cette opération ?"
          bouton="Supprimer l'opération"
          avertissement="Cette ligne sera supprimée (refusé si elle est rapprochée : annulez d'abord son rapprochement). Ses propositions en attente sont retirées. La suppression est tracée dans l'Historique."
          fichier={ligneASupprimer.libelle}
          resume={`${formatDate(ligneASupprimer.date_operation)} · ${formatAmount(ligneASupprimer.montant, suffix)}`}
          onClose={() => setLigneASupprimer(null)}
          onConfirm={async (motif) => {
            await supprimerOperation(ligneASupprimer.id, motif);
            setLigneASupprimer(null);
            toast("Opération supprimée.");
            setState("loading");
            setRetryKey((key) => key + 1);
          }}
        />
      )}
      {editing && (
        <TransactionEditModal
          transaction={editing}
          pointages={pointages}
          suffix={suffix}
          onClose={() => setEditing(null)}
          onSaved={replaceOperation}
        />
      )}
    </Card>
  );
}
