"use client";

import { CheckCheck, ListChecks, X } from "lucide-react";
import { useState } from "react";

import { SignalDiscrepancyModal } from "@/components/ecarts/SignalDiscrepancyModal";
import { AmbiguousCard } from "@/components/rapprochement/AmbiguousCard";
import { EcritureAmbigueCard } from "@/components/rapprochement/EcritureAmbigueCard";
import { ProposalCard } from "@/components/rapprochement/ProposalCard";
import { StatButton } from "@/components/rapprochement/StatButton";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { ApiError } from "@/lib/api";
import { formatAmount } from "@/lib/format";
import {
  aRejeter,
  aValider,
  TYPES_OPERATION,
  defaultSelection,
  compteFiltre,
  filterProposals,
  LOT_MAX,
  formatScore,
  selectionSummary,
  unite,
  validable,
  type ProposalsFilter,
} from "@/lib/reconciliation";
import {
  aucuneEcriture,
  aucuneEcritureLot,
  aucuneOperation,
  aucuneOperationLot,
  rejectMatches,
  matchGroupe,
  matchManually,
  rejectMatch,
  validateMatch,
  validateMatches,
} from "@/services/reconciliation";
import type {
  Ambigue,
  Ambigues,
  Correspondance,
  Correspondances,
  EcritureAmbigue,
  EcrituresAmbigues,
  Operation,
} from "@/types/reconciliation";

type ProposalsTabProps = {
  companyId: number;
  /** Propositions en attente de la période, chargées par la vue (null : en cours). */
  pending: Correspondances | null;
  logos: Map<string, string | null>;
  canValidate: boolean;
  canManageDiscrepancies: boolean;
  /** Après une décision : la vue recharge tout et affiche le message. */
  onChanged: (message: string) => void;
  /** Ouvre la proposition dans l'onglet Rapprochement. */
  onOpen: (item: Correspondance) => void;
  /** Opérations ambiguës (à vérifier sans proposition), chargées par la vue (null : en cours). */
  ambigues: Ambigues | null;
  /** Page des opérations ambiguës (50 par page). */
  onAmbiguPage: (page: number) => void;
  /** Écritures ambiguës (15/10/2026), chargées par la vue (null : en cours). */
  ecrituresAmbigues: EcrituresAmbigues | null;
  onEcrituresAmbiguesPage: (page: number) => void;
  /** Ouvre une opération ambiguë dans l'onglet Rapprochement. */
  onOpenOperation: (operation: Operation) => void;
  /** Filtre « Type d'opération » de l'opération bancaire (14/10/2026) ; "" = tous. */
  typeOperation?: string;
  onTypeOperation?: (value: string) => void;
};

type LignesEcart = {
  operation: { id: number; date: string; libelle: string; montant: string };
  ecriture: { id: number; date: string; libelle: string; montant: string } | null;
};

/** Filtres de l'onglet ; le seuil « forte » vient du serveur (80 depuis le 08/10/2026). */
function filtres(seuil: string): { value: ProposalsFilter; label: string }[] {
  return [
    { value: "toutes", label: "Toutes" },
    { value: "fortes", label: `Fortes (≥ ${seuil})` },
    { value: "a_verifier", label: `À vérifier (< ${seuil})` },
    { value: "ambigues", label: "Opérations ambiguës" },
    { value: "ecritures_ambigues", label: "Écritures ambiguës" },
    { value: "eloignees", label: "Éloignées" },
  ];
}

function bascule(ids: ReadonlySet<number>, id: number): Set<number> {
  const suivants = new Set(ids);
  if (suivants.has(id)) suivants.delete(id);
  else suivants.add(id);
  return suivants;
}

/** Barre des ambiguës (15/10/2026) : sélection de la page et « Aucune correspondance » en lot. */
function BarreAucune({
  nb,
  total,
  mot,
  busy,
  onTout,
  onRien,
  onAucune,
}: {
  nb: number;
  total: number;
  mot: string;
  busy: boolean;
  onTout: () => void;
  onRien: () => void;
  onAucune: () => void;
}) {
  return (
    <div className="sticky bottom-0 z-10 -mx-1 rounded-card border border-simtis-border bg-simtis-card p-4 shadow-simtis">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm">
          <span className="font-semibold">
            {nb} sélectionnée{nb > 1 ? "s" : ""}
          </span>{" "}
          sur {total} {mot}
          {total > 1 ? "s" : ""} de la page
        </p>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" disabled={busy} onClick={onTout}>
            Tout sélectionner
          </Button>
          <Button variant="ghost" icon={X} disabled={busy || nb === 0} onClick={onRien}>
            Tout désélectionner
          </Button>
          <Button variant="danger" icon={X} disabled={busy || nb === 0} onClick={onAucune}>
            Aucune correspondance pour la sélection ({nb})
          </Button>
        </div>
      </div>
    </div>
  );
}

function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.message : "Une erreur est survenue.";
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n > 1 ? "s" : ""}`;
}

/**
 * Onglet « Propositions » : chaque proposition en grand (transaction | score | écriture), avec
 * Valider / Rejeter, et une barre en bas pour valider la sélection. Seules les fortes sont cochées
 * d'office ; une faible ne l'est que par l'utilisateur, après vérification (décision du 07/10/2026).
 */
export function ProposalsTab({
  companyId,
  pending,
  logos,
  canValidate,
  canManageDiscrepancies,
  onChanged,
  onOpen,
  ambigues,
  onAmbiguPage,
  ecrituresAmbigues,
  onEcrituresAmbiguesPage,
  onOpenOperation,
  typeOperation = "",
  onTypeOperation,
}: ProposalsTabProps) {
  const items = pending?.correspondances ?? null;
  const [filtre, setFiltre] = useState<ProposalsFilter>("toutes");
  // La sélection repart des fortes à chaque nouvelle liste (après une décision, un rechargement)
  const [selection, setSelection] = useState<{ source: Correspondance[] | null; ids: Set<number> }>(
    () => ({ source: items, ids: items ? defaultSelection(items) : new Set() }),
  );
  if (selection.source !== items) {
    setSelection({ source: items, ids: items ? defaultSelection(items) : new Set() });
  }
  const selected = selection.ids;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [rejecting, setRejecting] = useState<Correspondance | null>(null);
  // Opération ambiguë dont aucune écriture ne correspond (15/10/2026)
  const [aucune, setAucune] = useState<Ambigue | null>(null);
  const [aucuneOp, setAucuneOp] = useState<EcritureAmbigue | null>(null);
  // Sélections des ambiguës (15/10/2026), remises à zéro quand la liste change (page, filtre)
  const [selOps, setSelOps] = useState<{ source: unknown; ids: Set<number> }>({
    source: null,
    ids: new Set(),
  });
  const [selEcr, setSelEcr] = useState<{ source: unknown; ids: Set<number> }>({
    source: null,
    ids: new Set(),
  });
  // Traitement en lot à confirmer : rejet de propositions, ou « aucune correspondance »
  const [lot, setLot] = useState<{
    type: "propositions" | "operations" | "ecritures";
    ids: number[];
    /** Rejet de propositions : combien sont fortes, rappelé dans la confirmation. */
    fortes?: number;
  } | null>(null);
  const [comment, setComment] = useState("");
  const [signaling, setSignaling] = useState<LignesEcart | null>(null);
  // Cartes ambiguës déjà rapprochées (16/10/2026) : masquées aussitôt, sans attendre le
  // rechargement des listes ; la liste rechargée ne les contient plus
  const [masqueesOps, setMasqueesOps] = useState<{ source: unknown; ids: Set<number> }>({
    source: null,
    ids: new Set(),
  });
  const [masqueesEcr, setMasqueesEcr] = useState<{ source: unknown; ids: Set<number> }>({
    source: null,
    ids: new Set(),
  });
  // Carte en cours de rapprochement : son bouton affiche « Rapprochement… »
  const [enCours, setEnCours] = useState<string | null>(null);

  if (!items || !ambigues || !ecrituresAmbigues) {
    return (
      <Card title="Propositions en attente" icon={ListChecks}>
        <LoadingState rows={4} />
      </Card>
    );
  }

  const shown = filterProposals(items, filtre);
  // Seules les validables cochées partent à la validation (27/10/2026 : une proposition aux
  // montants différents se coche pour être rejetée)
  const valides = aValider(items, selected);
  const summary = selectionSummary(items, new Set(valides.map((item) => item.id)));
  // Jamais de somme entre devises (14/10/2026) : une sélection mêlant EUR et DH n'a pas de total
  const unites = new Set(
    (items ?? [])
      .filter((item) => selected.has(item.id))
      .map((item) => unite(item.operation.devise)),
  );
  const totalTexte =
    unites.size > 1 ? "plusieurs devises" : formatAmount(summary.total, [...unites][0] ?? "DH");
  const ambiguous = ambigues.ambigues;
  const seuil = formatScore(pending?.seuil_fort ?? ambigues.seuil_fort);
  const opsMasquees = masqueesOps.source === ambiguous ? masqueesOps.ids : new Set<number>();
  const ecrMasquees =
    masqueesEcr.source === ecrituresAmbigues.ecritures ? masqueesEcr.ids : new Set<number>();
  const shownAmbiguous = (filtre === "toutes" || filtre === "ambigues" ? ambiguous : []).filter(
    (item) => !opsMasquees.has(item.operation.id),
  );
  const opsCochees = selOps.source === ambiguous ? selOps.ids : new Set<number>();
  const ecrCochees = selEcr.source === ecrituresAmbigues.ecritures ? selEcr.ids : new Set<number>();
  // Rejet en lot (27/10/2026) : les propositions cochées ET affichées par le filtre en cours
  const rejets = aRejeter(shown, selected);
  const rejetsForts = rejets.filter((item) => item.forte).length;
  const shownEcritures = (
    filtre === "toutes" || filtre === "ecritures_ambigues" ? ecrituresAmbigues.ecritures : []
  ).filter((item) => !ecrMasquees.has(item.ecriture.id));
  const nothing = shown.length === 0 && shownAmbiguous.length === 0 && shownEcritures.length === 0;

  function setIds(update: (ids: Set<number>) => Set<number>) {
    setSelection((current) => ({ ...current, ids: update(new Set(current.ids)) }));
  }

  async function act(action: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setConfirming(false);
      setRejecting(null);
      setAucune(null);
      setAucuneOp(null);
      setLot(null);
      setSelOps({ source: null, ids: new Set() });
      setSelEcr({ source: null, ids: new Set() });
      setComment("");
      onChanged(message);
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setBusy(false);
    }
  }

  /** Rapprochement depuis une carte ambiguë : relance ciblée, carte masquée aussitôt. */
  async function rapprocherAmbigue(cote: "op" | "ec", id: number, action: () => Promise<unknown>) {
    setEnCours(`${cote}-${id}`);
    setBusy(true);
    setError(null);
    try {
      await action();
      if (cote === "op") {
        setMasqueesOps({ source: ambiguous, ids: new Set([...opsMasquees, id]) });
      } else {
        setMasqueesEcr({
          source: ecrituresAmbigues?.ecritures,
          ids: new Set([...ecrMasquees, id]),
        });
      }
      onChanged("Rapprochement enregistré.");
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setBusy(false);
      setEnCours(null);
    }
  }

  return (
    <div className="space-y-4">
      <Card title="Propositions en attente" icon={ListChecks}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div
            className="grid grid-cols-2 gap-2 text-sm sm:max-w-3xl sm:grid-cols-5"
            role="group"
            aria-label="Filtrer les propositions"
          >
            {filtres(seuil).map(({ value, label }) => (
              <StatButton
                key={value}
                label={label}
                value={compteFiltre(items, value, ambigues.total, ecrituresAmbigues.total)}
                active={filtre === value}
                onClick={() => setFiltre(value)}
              />
            ))}
          </div>
          {onTypeOperation && (
            <div className="w-full max-w-[170px]">
              <Field label="Type d'opération" htmlFor="propositions-type">
                <Select
                  id="propositions-type"
                  value={typeOperation}
                  placeholder="Tous les types"
                  options={TYPES_OPERATION.map((item) => ({ value: item, label: item }))}
                  onChange={(event) => onTypeOperation(event.target.value)}
                />
              </Field>
            </div>
          )}
          <p className="max-w-md text-sm text-simtis-muted">
            Les fortes correspondances sont cochées d&apos;office. Cochez une proposition à vérifier
            seulement après l&apos;avoir contrôlée. Une opération ambiguë se rapproche en
            choisissant son écriture.
          </p>
        </div>
        {error && (
          <p
            role="alert"
            className="mt-4 rounded-[10px] bg-simtis-danger-bg px-3 py-2 text-sm text-simtis-danger-fg"
          >
            {error}
          </p>
        )}
      </Card>

      {nothing ? (
        <Card>
          <EmptyState
            icon={ListChecks}
            message={
              items.length + ambigues.total + ecrituresAmbigues.total === 0
                ? "Rien à vérifier : lancez le rapprochement sur la période."
                : "Rien dans ce filtre."
            }
          />
        </Card>
      ) : (
        <ul className="space-y-3">
          {shown.map((item) => (
            <li key={item.id}>
              <ProposalCard
                item={item}
                logo={logos.get(item.operation.bank_code)}
                checked={selected.has(item.id)}
                canValidate={canValidate}
                canSignal={canManageDiscrepancies}
                busy={busy}
                onToggle={() =>
                  setIds((ids) => {
                    if (ids.has(item.id)) ids.delete(item.id);
                    else ids.add(item.id);
                    return ids;
                  })
                }
                onValidate={() => act(() => validateMatch(item.id), "Rapprochement validé.")}
                onReject={() => {
                  setComment("");
                  setRejecting(item);
                }}
                onSignal={() =>
                  setSignaling({
                    operation: {
                      id: item.operation.id,
                      date: item.operation.date_operation,
                      libelle: item.operation.libelle,
                      montant: item.operation.montant,
                    },
                    ecriture: {
                      id: item.ecriture.id,
                      date: item.ecriture.date_ecriture,
                      libelle: item.ecriture.libelle,
                      montant: item.ecriture.montant,
                    },
                  })
                }
                onOpen={() => onOpen(item)}
              />
            </li>
          ))}
          {shownAmbiguous.map((item) => (
            <li key={`ambigue-${item.operation.id}`}>
              <AmbiguousCard
                item={item}
                logo={logos.get(item.operation.bank_code)}
                seuilFort={ambigues.seuil_fort}
                canValidate={canValidate}
                canSignal={canManageDiscrepancies}
                busy={busy}
                enCours={enCours === `op-${item.operation.id}`}
                onChoose={(candidat) =>
                  rapprocherAmbigue("op", item.operation.id, () =>
                    matchManually(item.operation.id, candidat.ecriture.id, undefined, true),
                  )
                }
                onSignal={() =>
                  setSignaling({
                    operation: {
                      id: item.operation.id,
                      date: item.operation.date_operation,
                      libelle: item.operation.libelle,
                      montant: item.operation.montant,
                    },
                    ecriture: null,
                  })
                }
                onOpen={() => onOpenOperation(item.operation)}
                onAucune={() => setAucune(item)}
                selection={
                  canValidate && filtre === "ambigues"
                    ? {
                        checked: opsCochees.has(item.operation.id),
                        onToggle: () =>
                          setSelOps({
                            source: ambiguous,
                            ids: bascule(opsCochees, item.operation.id),
                          }),
                      }
                    : undefined
                }
              />
            </li>
          ))}
        </ul>
      )}
      {shownEcritures.length > 0 && (
        <ul className="space-y-3">
          {shownEcritures.map((item) => (
            <li key={`ecriture-ambigue-${item.ecriture.id}`}>
              <EcritureAmbigueCard
                item={item}
                logo={logos.get(item.ecriture.bank_code ?? "")}
                seuilFort={ambigues.seuil_fort}
                canValidate={canValidate}
                busy={busy}
                enCours={enCours === `ec-${item.ecriture.id}`}
                onRapprocher={(operationIds) =>
                  rapprocherAmbigue("ec", item.ecriture.id, () =>
                    matchGroupe(operationIds, [item.ecriture.id], undefined, true),
                  )
                }
                onAucune={() => {
                  setComment("");
                  setAucuneOp(item);
                }}
                selection={
                  canValidate && filtre === "ecritures_ambigues"
                    ? {
                        checked: ecrCochees.has(item.ecriture.id),
                        onToggle: () =>
                          setSelEcr({
                            source: ecrituresAmbigues.ecritures,
                            ids: bascule(ecrCochees, item.ecriture.id),
                          }),
                      }
                    : undefined
                }
              />
            </li>
          ))}
        </ul>
      )}
      {shownEcritures.length > 0 && ecrituresAmbigues.total > ecrituresAmbigues.taille && (
        <Pagination
          label="Pages des écritures ambiguës"
          page={ecrituresAmbigues.page}
          pages={Math.ceil(ecrituresAmbigues.total / ecrituresAmbigues.taille)}
          total={ecrituresAmbigues.total}
          noun="écriture"
          onPage={onEcrituresAmbiguesPage}
        />
      )}

      {shownAmbiguous.length > 0 && ambigues.total > ambigues.taille && (
        <Pagination
          label="Pages des opérations ambiguës"
          page={ambigues.page}
          pages={Math.ceil(ambigues.total / ambigues.taille)}
          total={ambigues.total}
          noun="opération"
          onPage={onAmbiguPage}
        />
      )}

      {canValidate &&
        ((filtre === "ambigues" && ambiguous.length > 0) ||
          (filtre === "ecritures_ambigues" && ecrituresAmbigues.ecritures.length > 0)) && (
          <BarreAucune
            nb={filtre === "ambigues" ? opsCochees.size : ecrCochees.size}
            total={filtre === "ambigues" ? ambiguous.length : ecrituresAmbigues.ecritures.length}
            mot={filtre === "ambigues" ? "opération" : "écriture"}
            busy={busy}
            onTout={() =>
              filtre === "ambigues"
                ? setSelOps({
                    source: ambiguous,
                    ids: new Set(ambiguous.map((item) => item.operation.id)),
                  })
                : setSelEcr({
                    source: ecrituresAmbigues.ecritures,
                    ids: new Set(ecrituresAmbigues.ecritures.map((item) => item.ecriture.id)),
                  })
            }
            onRien={() =>
              filtre === "ambigues"
                ? setSelOps({ source: ambiguous, ids: new Set() })
                : setSelEcr({ source: ecrituresAmbigues.ecritures, ids: new Set() })
            }
            onAucune={() => {
              setComment("");
              setLot(
                filtre === "ambigues"
                  ? { type: "operations", ids: [...opsCochees] }
                  : { type: "ecritures", ids: [...ecrCochees] },
              );
            }}
          />
        )}

      {canValidate &&
        items.length > 0 &&
        filtre !== "ambigues" &&
        filtre !== "ecritures_ambigues" && (
          <div className="sticky bottom-0 z-10 -mx-1 rounded-card border border-simtis-border bg-simtis-card p-4 shadow-simtis">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm">
                <span className="font-semibold">
                  {summary.nb} sélectionnée{summary.nb > 1 ? "s" : ""}
                </span>{" "}
                sur {items.length} ·{" "}
                <span className="font-semibold tabular-nums">{totalTexte}</span>
                {summary.faibles > 0 && (
                  <span className="text-simtis-warning-fg">
                    {" "}
                    · dont {plural(summary.faibles, "proposition")} à vérifier
                  </span>
                )}
                {summary.nb > LOT_MAX && (
                  <span role="alert" className="block text-simtis-danger-fg">
                    Sélection trop grande ({summary.nb}) : {LOT_MAX} au plus par validation. Filtrez
                    par compte ou par période.
                  </span>
                )}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() =>
                    setIds(() => new Set(shown.filter(validable).map((item) => item.id)))
                  }
                >
                  Tout sélectionner
                </Button>
                <Button
                  variant="ghost"
                  icon={X}
                  disabled={busy || summary.nb === 0}
                  onClick={() => setIds(() => new Set())}
                >
                  Tout désélectionner
                </Button>
                <Button
                  variant="danger"
                  icon={X}
                  disabled={busy || rejets.length === 0 || rejets.length > LOT_MAX}
                  onClick={() => {
                    setComment("");
                    setLot({
                      type: "propositions",
                      ids: rejets.map((item) => item.id),
                      fortes: rejetsForts,
                    });
                  }}
                >
                  Rejeter la sélection ({rejets.length})
                </Button>
                <Button
                  icon={CheckCheck}
                  disabled={busy || summary.nb === 0 || summary.nb > LOT_MAX}
                  onClick={() => setConfirming(true)}
                >
                  Valider la sélection ({summary.nb})
                </Button>
              </div>
            </div>
          </div>
        )}

      <Modal
        open={confirming}
        onClose={() => setConfirming(false)}
        title="Valider la sélection"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirming(false)}>
              Retour
            </Button>
            <Button
              icon={CheckCheck}
              disabled={busy}
              onClick={() =>
                act(
                  () => validateMatches(valides.map((item) => item.id)),
                  `${plural(summary.nb, "rapprochement")} validé${summary.nb > 1 ? "s" : ""}.`,
                )
              }
            >
              Valider {plural(summary.nb, "rapprochement")}
            </Button>
          </>
        }
      >
        <p>
          {plural(summary.nb, "proposition")} pour un total de{" "}
          <strong className="tabular-nums">{totalTexte}</strong> vont être validées en votre nom.
          Chaque validation est tracée dans l&apos;historique.
        </p>
        {summary.faibles > 0 && (
          <p className="mt-2 text-simtis-warning-fg">
            Dont {plural(summary.faibles, "proposition")} à vérifier (score inférieur à {seuil}) :
            confirmez que vous les avez contrôlées.
          </p>
        )}
        {error && (
          <p role="alert" className="mt-2 text-simtis-danger-fg">
            {error}
          </p>
        )}
      </Modal>

      <Modal
        open={rejecting !== null}
        onClose={() => setRejecting(null)}
        title="Rejeter la proposition"
        footer={
          <>
            <Button variant="secondary" onClick={() => setRejecting(null)}>
              Retour
            </Button>
            <Button
              variant="danger"
              icon={X}
              disabled={busy}
              onClick={() =>
                rejecting && act(() => rejectMatch(rejecting.id, comment), "Proposition rejetée.")
              }
            >
              Rejeter
            </Button>
          </>
        }
      >
        <p className="mb-4 text-simtis-muted">
          Cette écriture ne sera plus proposée pour cette opération avant le prochain lancement du
          rapprochement.
        </p>
        <Field label="Commentaire (facultatif)" htmlFor="proposition-rejet">
          <TextInput
            id="proposition-rejet"
            value={comment}
            maxLength={500}
            onChange={(event) => setComment(event.target.value)}
          />
        </Field>
      </Modal>

      <Modal
        open={aucune !== null}
        onClose={() => setAucune(null)}
        title="Aucune écriture ne correspond"
        footer={
          <>
            <Button variant="secondary" onClick={() => setAucune(null)}>
              Retour
            </Button>
            <Button
              variant="danger"
              icon={X}
              disabled={busy}
              onClick={() =>
                aucune &&
                act(
                  () => aucuneEcriture(aucune.operation.id, comment),
                  `${aucune.candidats.length} écriture${aucune.candidats.length > 1 ? "s" : ""} écartée${aucune.candidats.length > 1 ? "s" : ""} pour cette opération.`,
                )
              }
            >
              Écarter les écritures
            </Button>
          </>
        }
      >
        {aucune && (
          <p className="mb-4 text-simtis-muted">
            Les {aucune.candidats.length} écritures proposées seront écartées pour l&apos;opération
            « {aucune.operation.libelle} » : elles ne lui seront plus proposées avant le prochain
            lancement du rapprochement, et l&apos;opération repasse « Non rapprochée ». Une écriture
            importée plus tard sera comparée normalement.
          </p>
        )}
        <Field label="Commentaire (facultatif)" htmlFor="aucune-ecriture">
          <TextInput
            id="aucune-ecriture"
            value={comment}
            maxLength={500}
            onChange={(event) => setComment(event.target.value)}
          />
        </Field>
      </Modal>

      <Modal
        open={aucuneOp !== null}
        onClose={() => setAucuneOp(null)}
        title="Aucune opération ne correspond"
        footer={
          <>
            <Button variant="secondary" onClick={() => setAucuneOp(null)}>
              Retour
            </Button>
            <Button
              variant="danger"
              icon={X}
              disabled={busy}
              onClick={() =>
                aucuneOp &&
                act(
                  () => aucuneOperation(aucuneOp.ecriture.id, comment),
                  `${plural(aucuneOp.candidats.length, "opération")} écartée${aucuneOp.candidats.length > 1 ? "s" : ""} pour cette écriture.`,
                )
              }
            >
              Écarter les opérations
            </Button>
          </>
        }
      >
        {aucuneOp && (
          <p className="mb-4 text-simtis-muted">
            Les {aucuneOp.candidats.length} opérations proposées seront écartées pour
            l&apos;écriture « {aucuneOp.ecriture.libelle} » : elles ne lui seront plus proposées
            avant le prochain lancement du rapprochement, et l&apos;écriture repasse « Non
            rapprochée ».
          </p>
        )}
        <Field label="Commentaire (facultatif)" htmlFor="aucune-operation">
          <TextInput
            id="aucune-operation"
            value={comment}
            maxLength={500}
            onChange={(event) => setComment(event.target.value)}
          />
        </Field>
      </Modal>

      <Modal
        open={lot !== null}
        onClose={() => setLot(null)}
        title={
          lot?.type === "propositions"
            ? "Rejeter les propositions sélectionnées"
            : "Aucune correspondance pour la sélection"
        }
        footer={
          <>
            <Button variant="secondary" onClick={() => setLot(null)}>
              Retour
            </Button>
            <Button
              variant="danger"
              icon={X}
              disabled={busy}
              onClick={() =>
                lot &&
                act(
                  () =>
                    lot.type === "propositions"
                      ? rejectMatches(lot.ids, comment)
                      : lot.type === "operations"
                        ? aucuneEcritureLot(lot.ids, comment)
                        : aucuneOperationLot(lot.ids, comment),
                  lot.type === "propositions"
                    ? `${plural(lot.ids.length, "proposition")} rejetée${lot.ids.length > 1 ? "s" : ""}.`
                    : `${plural(lot.ids.length, lot.type === "operations" ? "opération" : "écriture")} sans correspondance.`,
                )
              }
            >
              {lot?.type === "propositions" ? "Rejeter" : "Écarter les candidates"}
            </Button>
          </>
        }
      >
        {lot && (
          <p className="mb-4 text-simtis-muted">
            {lot.type === "propositions"
              ? `${plural(lot.ids.length, "proposition")} seront rejetées : ces paires ne seront plus proposées avant le prochain lancement du rapprochement et leurs lignes repassent « Non rapprochée ».`
              : `Pour ${plural(lot.ids.length, lot.type === "operations" ? "opération" : "écriture")}, toutes les candidates seront écartées (plus proposées avant le prochain lancement du rapprochement) et la ligne repasse « Non rapprochée ».`}
          </p>
        )}
        {lot?.type === "propositions" && !!lot.fortes && (
          <p role="alert" className="-mt-2 mb-4 text-sm font-medium text-simtis-warning-fg">
            Dont {plural(lot.fortes, "forte correspondance")} (score d&apos;au moins {seuil}).
          </p>
        )}
        <Field label="Commentaire (facultatif)" htmlFor="lot-commentaire">
          <TextInput
            id="lot-commentaire"
            value={comment}
            maxLength={500}
            onChange={(event) => setComment(event.target.value)}
          />
        </Field>
      </Modal>

      {signaling && (
        <SignalDiscrepancyModal
          companyId={companyId}
          operation={signaling.operation}
          ecriture={signaling.ecriture}
          onClose={() => setSignaling(null)}
          onCreated={(ecart) => {
            setSignaling(null);
            onChanged(`Écart n° ${ecart.id} « ${ecart.type} » signalé.`);
          }}
        />
      )}
    </div>
  );
}
