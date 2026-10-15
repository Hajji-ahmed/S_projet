"use client";

import { Check, ChevronDown, ChevronRight, Landmark, PenLine, Trash2 } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { CodeBadge } from "@/components/rapprochement/CodeBadge";
import { ManualFeeModal } from "@/components/rapprochement/ManualFeeModal";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { Field, TextInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import { cleJour, selectionTimbres, sommeMontants } from "@/lib/frais";
import type { ReconciliationFilter } from "@/lib/reconciliation";
import { formatDateTime } from "@/lib/statements";
import { listFrais, supprimerEcritureFrais, validerFrais } from "@/services/frais";
import type { EcritureFrais, LigneGL, Timbre, Timbres } from "@/types/frais";

type FraisCardProps = {
  companyId: number;
  filter: ReconciliationFilter;
  reloadKey: number;
  canPrepare: boolean;
  onChanged: (message: string) => void;
  /** Nombre d'écritures pas encore exportées, pour le bouton d'export commun. */
  onAExporter: (nombre: number) => void;
  /** Lance le moteur de rapprochement (frais inclus dans une écriture Sage). */
  onLancer?: () => void;
};

function plural(n: number, word: string): string {
  return `${n} ${word}${n > 1 ? "s" : ""}`;
}

/** Libellé d'une ligne : « DT D'ENREGISTREMENT · 9 timbres », « COM · Commission effet ». */
function libelleLigne(famille: EcritureFrais["famille"], ligne: LigneGL, nb: number) {
  // Le libellé de la ligne, comme dans le fichier Sage (« TVA COM » pour une TVA, 14/10/2026)
  if (famille === "timbres") return `${ligne.libelle} · ${plural(nb, "timbre")}`;
  // Écriture manuelle sans TVA : une seule ligne, sans type
  return ligne.type_libelle ? `${ligne.libelle} · ${ligne.type_libelle}` : ligne.libelle;
}

/**
 * Frais comptabilisés par SIMTIS (13/10/2026), en UN tableau : droits de timbre (une ligne par
 * jour, « DT D'ENREGISTREMENT ») et commissions (« COM », une ligne par type), au format du grand
 * livre Sage, tous les montants au CRÉDIT du compte bancaire. La validation enregistre l'écriture
 * et la rapproche d'emblée de ses opérations ; l'export pour Sage est commun.
 */
export function FraisCard({
  companyId,
  filter,
  reloadKey,
  canPrepare,
  onChanged,
  onAExporter,
  onLancer,
}: FraisCardProps) {
  const { toast } = useToast();
  const [data, setData] = useState<Timbres | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [retry, setRetry] = useState(0);
  const [selection, setSelection] = useState<Set<string>>(new Set());
  const [ouverts, setOuverts] = useState<Set<string>>(new Set());
  // Autres frais cochés pour une écriture saisie à la main (décochés par défaut)
  const [manuels, setManuels] = useState<Set<number>>(new Set());
  const [saisie, setSaisie] = useState(false);
  const [busy, setBusy] = useState(false);
  const [suppression, setSuppression] = useState<EcritureFrais | null>(null);
  const [motif, setMotif] = useState("");
  const [modalError, setModalError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listFrais(companyId, filter).then(
      (result) => {
        if (cancelled) return;
        setData(result);
        // Toutes les écritures proposées sont cochées par défaut
        setSelection(new Set(result.propositions.map(cleJour)));
        setManuels(new Set());
        setState("ready");
        onAExporter(result.ecritures.filter((item) => !item.exportee_le).length);
      },
      () => {
        if (!cancelled) setState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [companyId, filter, reloadKey, retry, onAExporter]);

  const propositions = data?.propositions ?? [];
  const ecritures = data?.ecritures ?? [];
  const choisis = selectionTimbres(propositions, selection);
  const autres = data?.autres_frais ?? [];
  const inclus = data?.frais_inclus ?? [];
  const autresCoches = autres.filter((tx) => manuels.has(tx.id));
  const unSeulCompte = new Set(autresCoches.map((tx) => tx.bank_account_id)).size <= 1;

  function basculer(set: Set<string>, cle: string): Set<string> {
    const next = new Set(set);
    if (next.has(cle)) next.delete(cle);
    else next.add(cle);
    return next;
  }

  async function valider() {
    const jours = propositions
      .filter((item) => selection.has(cleJour(item)))
      .map((item) => ({
        famille: item.famille,
        bank_account_id: item.bank_account_id,
        date: item.date,
      }));
    setBusy(true);
    try {
      const result = await validerFrais(companyId, jours);
      const s = result.nb_ecritures > 1 ? "s" : "";
      onChanged(
        `${plural(result.nb_ecritures, "écriture")} de frais comptabilisée${s} et rapprochée${s}.`,
      );
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "La comptabilisation a échoué.", "error");
    } finally {
      setBusy(false);
    }
  }

  async function confirmerSuppression() {
    if (!suppression) return;
    setBusy(true);
    setModalError(null);
    try {
      await supprimerEcritureFrais(suppression.id, motif.trim());
      setSuppression(null);
      onChanged("Écriture supprimée : ses frais sont de nouveau à comptabiliser.");
    } catch (error) {
      setModalError(error instanceof ApiError ? error.message : "La suppression a échoué.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Frais bancaires" icon={Landmark}>
      <p className="-mt-2 mb-4 text-sm text-simtis-muted">
        Droits de timbre (« DT D&apos;ENREGISTREMENT », une ligne par jour) et commissions (« COM »,
        une ligne par type : COMMISSION, COMMISSION EFFET et leurs TVA), au crédit du compte
        bancaire. Rapprochés dès la validation. Les autres frais restent à passer à la main.
      </p>

      {state === "loading" && <LoadingState rows={3} />}
      {state === "error" && (
        <ErrorState
          message="Impossible de charger les frais bancaires."
          onRetry={() => {
            setState("loading");
            setRetry((n) => n + 1);
          }}
        />
      )}

      {state === "ready" && data && (
        <div className="space-y-6">
          <section aria-labelledby="frais-a-passer">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
              <h3 id="frais-a-passer" className="text-sm font-semibold text-simtis-text">
                À comptabiliser · {plural(propositions.length, "écriture")} ·{" "}
                <span className="tabular-nums">{formatAmount(data.total_propositions, "DH")}</span>
              </h3>
              {canPrepare && propositions.length > 0 && (
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="ghost"
                    onClick={() => setSelection(new Set(propositions.map(cleJour)))}
                  >
                    Tout cocher
                  </Button>
                  <Button variant="ghost" onClick={() => setSelection(new Set())}>
                    Tout décocher
                  </Button>
                  <Button icon={Check} disabled={busy || choisis.nb === 0} onClick={valider}>
                    Valider la sélection ({choisis.nb} · {formatAmount(choisis.total, "DH")})
                  </Button>
                </div>
              )}
            </div>
            {propositions.length === 0 ? (
              <Vide>Aucun frais à comptabiliser sur cette période.</Vide>
            ) : (
              <GrandLivre avecCase={canPrepare} fin={["Opérations"]}>
                {propositions.map((item) => {
                  const cle = cleJour(item);
                  const label = `${item.libelle} du ${formatDate(item.date)} ${item.bank_code}`;
                  const open = ouverts.has(cle);
                  const Chevron = open ? ChevronDown : ChevronRight;
                  return (
                    <Ecriture
                      key={cle}
                      famille={item.famille}
                      journal={item.journal}
                      date={item.date}
                      piece={null}
                      lignes={item.lignes}
                      nbOperations={item.nb_operations}
                      case={
                        canPrepare ? (
                          <input
                            type="checkbox"
                            className="h-4 w-4 accent-simtis-primary"
                            checked={selection.has(cle)}
                            onChange={() => setSelection((set) => basculer(set, cle))}
                            aria-label={`Comptabiliser ${label}`}
                          />
                        ) : undefined
                      }
                      fin={[
                        <button
                          key="detail"
                          type="button"
                          onClick={() => setOuverts((set) => basculer(set, cle))}
                          aria-expanded={open}
                          className="inline-flex items-center gap-1 text-simtis-primary hover:underline"
                        >
                          <Chevron className="h-4 w-4" aria-hidden />
                          {item.nb_operations}
                        </button>,
                      ]}
                      detail={open ? <Operations operations={item.operations} /> : null}
                    />
                  );
                })}
              </GrandLivre>
            )}
          </section>

          <section aria-labelledby="frais-manuels">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
              <h3 id="frais-manuels" className="text-sm font-semibold text-simtis-text">
                Autres frais à passer à la main · {plural(autres.length, "opération")}
              </h3>
              {canPrepare && autres.length > 0 && (
                <div className="flex flex-wrap items-center gap-2">
                  {autresCoches.length > 0 && (
                    <span className="text-sm text-simtis-muted tabular-nums">
                      {plural(autresCoches.length, "cochée")} ·{" "}
                      {formatAmount(sommeMontants(autresCoches.map((tx) => tx.montant)), "DH")}
                    </span>
                  )}
                  <Button
                    icon={PenLine}
                    disabled={busy || autresCoches.length === 0 || !unSeulCompte}
                    onClick={() => setSaisie(true)}
                  >
                    Créer l&apos;écriture
                  </Button>
                </div>
              )}
            </div>
            {!unSeulCompte && (
              <p className="mb-2 text-sm text-simtis-warning-fg">
                Une écriture ne regroupe que des opérations d&apos;un même compte bancaire.
              </p>
            )}
            {autres.length === 0 ? (
              <Vide>Aucun autre frais à comptabiliser sur cette période.</Vide>
            ) : (
              <div className="overflow-x-auto rounded-[12px] border border-simtis-border">
                <table className="w-full text-sm">
                  <thead className="bg-simtis-light text-left text-xs text-simtis-primary-dark">
                    <tr>
                      {canPrepare && (
                        <th className="w-10 px-3 py-2">
                          <span className="sr-only">Sélection</span>
                        </th>
                      )}
                      <th className={TH}>Date</th>
                      <th className={TH}>Banque</th>
                      <th className={TH}>Libellé</th>
                      <th className={cn(TH, "text-right")}>Montant</th>
                      <th className={TH}>Pointage</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-simtis-border">
                    {autres.map((tx) => (
                      <tr key={tx.id}>
                        {canPrepare && (
                          <td className="px-3 py-1.5">
                            <input
                              type="checkbox"
                              className="h-4 w-4 accent-simtis-primary"
                              checked={manuels.has(tx.id)}
                              onChange={() =>
                                setManuels((set) => {
                                  const next = new Set(set);
                                  if (next.has(tx.id)) next.delete(tx.id);
                                  else next.add(tx.id);
                                  return next;
                                })
                              }
                              aria-label={`Comptabiliser à la main ${tx.libelle} du ${formatDate(tx.date_operation)}`}
                            />
                          </td>
                        )}
                        <td className="px-3 py-1.5 whitespace-nowrap tabular-nums">
                          {formatDate(tx.date_operation)}
                        </td>
                        <td className="px-3 py-1.5">
                          <BankLabel code={tx.bank_code} logo={tx.bank_logo} />
                        </td>
                        <td className="px-3 py-1.5">{tx.libelle}</td>
                        <Montant value={tx.montant} />
                        <td className="px-3 py-1.5 text-simtis-muted">{tx.pointage ?? "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {inclus.length > 0 && (
            <details className="rounded-[12px] border border-simtis-border bg-simtis-orange-bg/40">
              <summary className="flex cursor-pointer flex-wrap items-center justify-between gap-3 px-3 py-2 text-sm font-semibold text-simtis-text">
                <span>
                  Inclus dans une écriture Sage, à rapprocher · {plural(inclus.length, "opération")}
                </span>
                {onLancer && (
                  <Button
                    variant="secondary"
                    onClick={(event) => {
                      event.preventDefault();
                      onLancer();
                    }}
                  >
                    Lancer le rapprochement
                  </Button>
                )}
              </summary>
              <p className="px-3 pb-2 text-sm text-simtis-muted">
                Ces frais font déjà partie d&apos;une écriture Sage encore libre : ils se
                rapprochent d&apos;elle et ne se comptabilisent pas dans SIMTIS.
              </p>
              <div className="overflow-x-auto border-t border-simtis-border bg-simtis-card">
                <table className="w-full text-sm">
                  <thead className="bg-simtis-light text-left text-xs text-simtis-primary-dark">
                    <tr>
                      <th className={TH}>Date</th>
                      <th className={TH}>Banque</th>
                      <th className={TH}>Frais</th>
                      <th className={cn(TH, "text-right")}>Montant</th>
                      <th className={TH}>Écriture Sage</th>
                      <th className={cn(TH, "text-right")}>Montant Sage</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-simtis-border">
                    {inclus.map((tx) => (
                      <tr key={tx.id}>
                        <td className="px-3 py-1.5 whitespace-nowrap tabular-nums">
                          {formatDate(tx.date_operation)}
                        </td>
                        <td className="px-3 py-1.5">
                          <BankLabel code={tx.bank_code} logo={tx.bank_logo} />
                        </td>
                        <td className="px-3 py-1.5">{tx.libelle}</td>
                        <Montant value={tx.montant} />
                        <td className="px-3 py-1.5">
                          {tx.ecriture.libelle}
                          <span className="block text-xs text-simtis-muted">
                            {formatDate(tx.ecriture.date)}
                            {tx.ecriture.journal && ` · Journal ${tx.ecriture.journal}`}
                            {tx.ecriture.numero_piece && ` · Pièce ${tx.ecriture.numero_piece}`}
                          </span>
                        </td>
                        <Montant value={tx.ecriture.montant} />
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}

          <section aria-labelledby="frais-comptabilises">
            <h3 id="frais-comptabilises" className="mb-2 text-sm font-semibold text-simtis-text">
              Comptabilisés par SIMTIS · {plural(ecritures.length, "écriture")}
            </h3>
            {ecritures.length === 0 ? (
              <Vide>Aucune écriture de frais comptabilisée par SIMTIS sur cette période.</Vide>
            ) : (
              <GrandLivre
                avecCase={false}
                fin={canPrepare ? ["Export Sage", "Actions"] : ["Export Sage"]}
              >
                {ecritures.map((item) => (
                  <Ecriture
                    key={item.id}
                    famille={item.famille}
                    journal={item.journal}
                    date={item.date}
                    piece={
                      <span className="inline-flex flex-col items-start gap-0.5">
                        <span className="font-medium tabular-nums">{item.numero_piece ?? "-"}</span>
                        <CodeBadge code={item.code} />
                      </span>
                    }
                    lignes={item.lignes}
                    nbOperations={item.nb_operations}
                    fin={[
                      item.exportee_le ? (
                        <span key="export" className="text-simtis-success-fg">
                          Exportée le {formatDateTime(item.exportee_le)}
                        </span>
                      ) : (
                        <span key="export" className="text-simtis-warning-fg">
                          À exporter
                        </span>
                      ),
                      ...(canPrepare
                        ? [
                            !item.exportee_le ? (
                              <Button
                                key="supprimer"
                                variant="ghost"
                                icon={Trash2}
                                aria-label={`Supprimer l'écriture ${item.libelle} du ${formatDate(item.date)}`}
                                onClick={() => {
                                  setMotif("");
                                  setModalError(null);
                                  setSuppression(item);
                                }}
                              >
                                Supprimer
                              </Button>
                            ) : null,
                          ]
                        : []),
                    ]}
                  />
                ))}
              </GrandLivre>
            )}
          </section>
        </div>
      )}

      {saisie && (
        <ManualFeeModal
          companyId={companyId}
          operations={autresCoches}
          onClose={() => setSaisie(false)}
          onDone={(message) => {
            setSaisie(false);
            onChanged(message);
          }}
        />
      )}

      <Modal
        open={suppression !== null}
        onClose={() => setSuppression(null)}
        title="Supprimer l'écriture de frais"
        footer={
          <>
            <Button variant="secondary" onClick={() => setSuppression(null)}>
              Retour
            </Button>
            <Button
              variant="danger"
              icon={Trash2}
              disabled={busy || !motif.trim()}
              onClick={confirmerSuppression}
            >
              Supprimer l&apos;écriture
            </Button>
          </>
        }
      >
        {modalError && (
          <p
            role="alert"
            className="mb-3 rounded-[10px] bg-simtis-danger-bg px-3 py-2 text-simtis-danger-fg"
          >
            {modalError}
          </p>
        )}
        <p className="mb-4 text-simtis-muted">
          L&apos;écriture n&apos;a pas encore été exportée pour Sage. Ses frais redeviennent à
          comptabiliser ; la suppression reste dans l&apos;historique des actions.
        </p>
        <Field label="Motif" htmlFor="frais-motif" required>
          <TextInput
            id="frais-motif"
            value={motif}
            maxLength={500}
            onChange={(event) => setMotif(event.target.value)}
          />
        </Field>
      </Modal>
    </Card>
  );
}

function Vide({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-[10px] bg-simtis-background px-3 py-3 text-sm text-simtis-muted">
      {children}
    </p>
  );
}

const TH = "px-3 py-2 font-semibold whitespace-nowrap";

/** Tableau au format du grand livre Sage ; chaque écriture est un `<tbody>`. */
function GrandLivre({
  avecCase,
  fin,
  children,
}: {
  avecCase: boolean;
  fin: string[];
  children: ReactNode;
}) {
  return (
    <div className="overflow-x-auto rounded-[12px] border border-simtis-border">
      <table className="w-full text-sm">
        <thead className="bg-simtis-light text-left text-xs text-simtis-primary-dark">
          <tr>
            {avecCase && (
              <th className="w-10 px-3 py-2">
                <span className="sr-only">Sélection</span>
              </th>
            )}
            <th className={TH}>Journal</th>
            <th className={TH}>Date</th>
            <th className={TH}>Compte</th>
            <th className={TH}>N° pièce</th>
            <th className={TH}>Libellé</th>
            <th className={cn(TH, "text-right")}>Débit</th>
            <th className={cn(TH, "text-right")}>Crédit</th>
            {fin.map((titre) => (
              <th key={titre} className={TH}>
                {titre === "Actions" ? <span className="sr-only">{titre}</span> : titre}
              </th>
            ))}
          </tr>
        </thead>
        {children}
      </table>
    </div>
  );
}

function Montant({ value }: { value: string | null }) {
  return (
    <td className="px-3 py-1.5 text-right whitespace-nowrap tabular-nums">
      {value ? formatAmount(value, "DH") : ""}
    </td>
  );
}

/** Une écriture : ses lignes du grand livre ; la case et les dernières colonnes portent sur toute
 * l'écriture (cellules fusionnées). */
function Ecriture({
  famille,
  journal,
  date,
  piece,
  lignes,
  nbOperations,
  case: caseACocher,
  fin,
  detail,
}: {
  famille: EcritureFrais["famille"];
  journal: string | null;
  date: string;
  piece: ReactNode;
  lignes: LigneGL[];
  nbOperations: number;
  case?: ReactNode;
  fin: ReactNode[];
  detail?: ReactNode;
}) {
  const span = lignes.length;
  const colonnes = (caseACocher !== undefined ? 1 : 0) + 7 + fin.length;
  return (
    <tbody className="border-t border-simtis-border first:border-t-0">
      {lignes.map((ligne, index) => (
        <tr key={`${ligne.type ?? "banque"}-${index}`}>
          {index === 0 && caseACocher !== undefined && (
            <td rowSpan={span} className="px-3 py-1.5 align-top">
              {caseACocher}
            </td>
          )}
          <td className="px-3 py-1.5 whitespace-nowrap">{journal ?? <ARenseigner />}</td>
          <td className="px-3 py-1.5 whitespace-nowrap tabular-nums">{formatDate(date)}</td>
          <td className="px-3 py-1.5 whitespace-nowrap tabular-nums">
            {ligne.compte ?? <ARenseigner />}
          </td>
          <td className="px-3 py-1.5 whitespace-nowrap">{piece ?? "-"}</td>
          <td className="px-3 py-1.5">{libelleLigne(famille, ligne, nbOperations)}</td>
          <Montant value={ligne.debit} />
          <Montant value={ligne.credit} />
          {index === 0 &&
            fin.map((cellule, position) => (
              <td key={position} rowSpan={span} className="px-3 py-1.5 align-top whitespace-nowrap">
                {cellule}
              </td>
            ))}
        </tr>
      ))}
      {detail && (
        <tr>
          <td colSpan={colonnes} className="bg-simtis-background px-3 py-2">
            {detail}
          </td>
        </tr>
      )}
    </tbody>
  );
}

function ARenseigner() {
  return <span className="text-simtis-warning-fg">à renseigner</span>;
}

function Operations({ operations }: { operations: Timbre[] }) {
  return (
    <ul className="space-y-0.5 text-sm text-simtis-muted" aria-label="Opérations du relevé">
      {operations.map((tx) => (
        <li key={tx.id} className="flex justify-between gap-3">
          <span className="min-w-0 truncate" title={tx.libelle}>
            {formatDate(tx.date_operation)} · {tx.libelle}
          </span>
          <span className="shrink-0 tabular-nums">{formatAmount(tx.montant, "DH")}</span>
        </li>
      ))}
    </ul>
  );
}
