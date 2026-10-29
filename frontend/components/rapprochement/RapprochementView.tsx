"use client";

import {
  Download,
  FileSpreadsheet,
  GitCompareArrows,
  History,
  ListChecks,
  Play,
  Search,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
} from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { AccountChipLabel } from "@/components/banks/AccountChipLabel";
import { useCompany } from "@/components/company/CompanyProvider";
import { AccountButton } from "@/components/ecritures/EntriesCard";
import { EntriesPane } from "@/components/rapprochement/EntriesPane";
import { FraisCard } from "@/components/rapprochement/FraisCard";
import { HistoryTab } from "@/components/rapprochement/HistoryTab";
import { MatchPanel } from "@/components/rapprochement/MatchPanel";
import { PanierPanel } from "@/components/rapprochement/PanierPanel";
import { ProposalsTab } from "@/components/rapprochement/ProposalsTab";
import { StatButton } from "@/components/rapprochement/StatButton";
import { TransactionsPane } from "@/components/rapprochement/TransactionsPane";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DateInput, Field } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { PageHeader } from "@/components/ui/PageHeader";
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api";
import { businessToday } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { ECARTS_ACTIFS } from "@/lib/features";
import {
  basculerLigne,
  CLE_PERIODE,
  compteurStatut,
  operationOf,
  periodeAStocker,
  periodeMemorisee,
  periodeRapprochement,
  toggleStatut,
  A_COMPTABILISER,
  type ReconciliationFilter,
} from "@/lib/reconciliation";
import { PERMISSIONS, hasAnyPermission } from "@/lib/permissions";
import { estPleinEcran, setPleinEcran, subscribe as subscribePleinEcran } from "@/lib/pleinEcran";
import { saveFile } from "@/lib/statements";
import { listAccounts } from "@/services/accounts";
import { exporterFrais, exporterJustificatif } from "@/services/frais";
import {
  listAmbiguous,
  listAmbiguousEntries,
  listProposals,
  runReconciliation,
  runReconciliationElargie,
} from "@/services/reconciliation";
import type { Account } from "@/types/account";
import type { Ecriture, StatutRapprochement } from "@/types/accounting";
import type {
  Ambigues,
  Correspondances,
  EcrituresAmbigues,
  Operation,
  OperationsPage,
} from "@/types/reconciliation";

/**
 * Page Rapprochement (P11) : le moteur propose des correspondances 1→1 entre les opérations
 * bancaires et les écritures Sage de la société active ; un utilisateur autorisé valide, rejette ou
 * rapproche à la main. Rien n'est validé automatiquement.
 */
export function RapprochementView() {
  const { company } = useCompany();
  // Changer de société repart d'une page vierge : rien ne se mélange entre deux sociétés
  return company ? <Rapprochement key={company.id} companyId={company.id} /> : null;
}

// Compteurs qui filtrent le volet « Transactions bancaires ». Une opération en proposition
// (« À vérifier ») reste comptée « Non rapprochée » jusqu'à la validation (28/10/2026).
const COMPTEURS: { statut: StatutRapprochement; label: string }[] = [
  { statut: "Rapprochée", label: "Rapprochées" },
  { statut: "Non rapprochée", label: "Non rapprochées" },
];

function plural(n: number, word: string): string {
  return `${n} ${word}${n > 1 ? "s" : ""}`;
}

function Rapprochement({ companyId }: { companyId: number }) {
  const { user } = useAuth();
  const { toast } = useToast();
  const canValidate =
    !!user && hasAnyPermission(user.permissions, [PERMISSIONS.RECONCILIATION_VALIDATE]);
  // Comptabilisation des droits de timbre (13/10/2026)
  const canPrepare = !!user && hasAnyPermission(user.permissions, [PERMISSIONS.ACCOUNTING_PREPARE]);
  // Tous les boutons « Signaler un écart » de la page en dépendent
  const canManageDiscrepancies =
    ECARTS_ACTIFS &&
    !!user &&
    hasAnyPermission(user.permissions, [PERMISSIONS.DISCREPANCIES_MANAGE]);

  // Du 1er janvier à aujourd'hui, ou la dernière période choisie sur ce poste (27/10/2026)
  const [filter, setFilter] = useState<ReconciliationFilter>(() =>
    periodeRapprochement(businessToday()),
  );
  // La période gardée par le navigateur est lue avant le premier chargement des volets
  const [periodeLue, setPeriodeLue] = useState(false);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [reloadKey, setReloadKey] = useState(0);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [entry, setEntry] = useState<Ecriture | null>(null);
  const pleinEcran = useSyncExternalStore(subscribePleinEcran, estPleinEcran, () => false);
  const [panierOps, setPanierOps] = useState<Operation[]>([]);
  const [panierEcr, setPanierEcr] = useState<Ecriture[]>([]);
  const [parStatut, setParStatut] = useState<Record<StatutRapprochement, number> | null>(null);
  // Frais bancaires non rapprochés : compteur « À comptabiliser » (12/10/2026)
  const [aComptabiliser, setAComptabiliser] = useState<number | null>(null);
  // Opérations en cours (« (*) », 20/10/2026) : jamais rapprochées, comptées à part
  const [enCours, setEnCours] = useState<number | null>(null);
  const [pending, setPending] = useState<Correspondances | null>(null);
  const [ambigues, setAmbigues] = useState<Ambigues | null>(null);
  // Écritures ambiguës (15/10/2026) : leur propre page, revenue à 1 quand le filtre change
  const [ecrituresAmbigues, setEcrituresAmbigues] = useState<EcrituresAmbigues | null>(null);
  // Page des opérations ambiguës (50 par page) ; revient à 1 quand le filtre change
  const cleAmbigues = `${companyId}|${filter.bankAccountId ?? "tous"}|${filter.from}|${filter.to}`;
  const [ambiguPage, setAmbiguPage] = useState({ cle: cleAmbigues, page: 1 });
  const pageAmbigues = ambiguPage.cle === cleAmbigues ? ambiguPage.page : 1;
  const [ecrAmbiguPage, setEcrAmbiguPage] = useState({ cle: cleAmbigues, page: 1 });
  const pageEcrAmbigues = ecrAmbiguPage.cle === cleAmbigues ? ecrAmbiguPage.page : 1;
  const [running, setRunning] = useState(false);
  // Filtre « Type » de l'onglet Propositions (14/10/2026)
  const [typePropositions, setTypePropositions] = useState("");
  // Écritures de frais pas encore exportées : un seul export pour Sage (13/10/2026)
  const [totalAExporter, setTotalAExporter] = useState(0);
  const [exporting, setExporting] = useState(false);

  /** Frais de plus de 200 DH à envoyer à la banque (19/10/2026) : ne marque rien. */
  async function exporterPourBanque() {
    setExporting(true);
    try {
      const blob = await exporterJustificatif(companyId, filter);
      saveFile(blob, `frais-a-justifier-${filter.from}-${filter.to}.xlsx`);
      toast("Frais à justifier exportés pour la banque.");
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "L'export a échoué.", "error");
    } finally {
      setExporting(false);
    }
  }

  async function exporterPourSage() {
    setExporting(true);
    try {
      const blob = await exporterFrais(companyId, filter);
      saveFile(blob, `ecritures-frais-${filter.from}-${filter.to}.csv`);
      reload(
        `${plural(totalAExporter, "écriture")} exportée${totalAExporter > 1 ? "s" : ""} pour Sage.`,
      );
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "L'export a échoué.", "error");
    } finally {
      setExporting(false);
    }
  }
  const [statut, setStatut] = useState("");
  const [tab, setTab] = useState<"rapprochement" | "propositions" | "historique">("rapprochement");

  const periodError =
    filter.from && filter.to && filter.from > filter.to
      ? "La date de début doit précéder la date de fin."
      : !filter.from || !filter.to
        ? "Choisissez une période."
        : null;

  useEffect(() => {
    let brut: string | null = null;
    try {
      brut = window.localStorage.getItem(CLE_PERIODE);
    } catch {
      // Stockage indisponible : période par défaut
    }
    const periode = periodeMemorisee(brut, businessToday());
    // eslint-disable-next-line react-hooks/set-state-in-effect -- lecture unique du navigateur
    setFilter((current) => ({ ...current, ...periode }));
    setPeriodeLue(true);
  }, []);

  useEffect(() => {
    let cancelled = false;
    listAccounts(companyId, { actif: true }).then(
      (list) => {
        if (!cancelled) setAccounts(list.filter((account) => account.journal_sage));
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  useEffect(() => {
    if (periodError) return;
    let cancelled = false;
    const filtreType = { ...filter, typeOperation: typePropositions || undefined };
    listProposals(companyId, filtreType).then(
      (result) => {
        if (!cancelled) setPending(result);
      },
      () => {
        if (!cancelled) setPending(null);
      },
    );
    listAmbiguous(companyId, filtreType, pageAmbigues).then(
      (result) => {
        if (!cancelled) setAmbigues(result);
      },
      () => {
        if (!cancelled) setAmbigues(null);
      },
    );
    listAmbiguousEntries(companyId, filtreType, pageEcrAmbigues).then(
      (result) => {
        if (!cancelled) setEcrituresAmbigues(result);
      },
      () => {
        if (!cancelled) setEcrituresAmbigues(null);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [companyId, filter, reloadKey, periodError, pageAmbigues, pageEcrAmbigues, typePropositions]);

  // Les volets rechargés : la sélection suit les nouvelles valeurs (statut, correspondance)
  const handleOperations = useCallback((page: OperationsPage) => {
    setParStatut(page.par_statut);
    setAComptabiliser(page.a_comptabiliser ?? 0);
    setEnCours(page.en_cours ?? 0);
    setOperation((current) =>
      current ? (page.operations.find((row) => row.id === current.id) ?? current) : current,
    );
  }, []);
  const handleEntries = useCallback((rows: Ecriture[]) => {
    setEntry((current) =>
      current ? (rows.find((row) => row.id === current.id) ?? current) : current,
    );
  }, []);

  // Le plein écran se quitte avec Échap (sauf dans une fenêtre ouverte) et en quittant la page
  useEffect(() => {
    if (!pleinEcran) return;
    const quitter = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !document.querySelector('dialog[open], [role="dialog"]')) {
        setPleinEcran(false);
      }
    };
    window.addEventListener("keydown", quitter);
    return () => window.removeEventListener("keydown", quitter);
  }, [pleinEcran]);
  useEffect(() => () => setPleinEcran(false), []);

  // Plein écran (29/10/2026) : la page descend jusqu'au bandeau de correspondance, et les deux
  // volets prennent la hauteur restante de la fenêtre (mesurée sous le bandeau, qui peut s'ouvrir)
  const zoneRef = useRef<HTMLDivElement>(null);
  const bandeauRef = useRef<HTMLDivElement>(null);
  const [hauteurBandeau, setHauteurBandeau] = useState(0);
  useEffect(() => {
    const bandeau = bandeauRef.current;
    if (!bandeau || typeof ResizeObserver === "undefined") return;
    const observateur = new ResizeObserver(() => setHauteurBandeau(bandeau.offsetHeight));
    observateur.observe(bandeau);
    return () => observateur.disconnect();
  }, [tab, periodeLue]);
  useEffect(() => {
    if (!pleinEcran) return;
    // Après le retrait du menu et de l'en-tête : la mise en page a changé
    const image = requestAnimationFrame(() => {
      const zone = zoneRef.current;
      if (!zone) return;
      const doux = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({
        top: zone.getBoundingClientRect().top + window.scrollY,
        behavior: doux ? "smooth" : "auto",
      });
    });
    return () => cancelAnimationFrame(image);
  }, [pleinEcran]);

  // Détail d'une ligne rapprochée ou d'une proposition ouverte depuis l'onglet Propositions : le
  // panneau Correspondance dans une fenêtre (28/10/2026), les lignes libres se cochent
  function fermerDetail() {
    setOperation(null);
    setEntry(null);
  }

  function changeFilter(next: Partial<ReconciliationFilter>) {
    setOperation(null);
    setEntry(null);
    setFilter((current) => {
      const suivant = { ...current, ...next };
      if ("from" in next || "to" in next) {
        try {
          window.localStorage.setItem(CLE_PERIODE, periodeAStocker(suivant, businessToday()));
        } catch {
          // Stockage indisponible : le choix vaut pour la visite en cours
        }
      }
      return suivant;
    });
  }

  function reload(message: string) {
    toast(message);
    setReloadKey((key) => key + 1);
  }

  function viderPanier() {
    setPanierOps([]);
    setPanierEcr([]);
  }

  async function run() {
    setRunning(true);
    try {
      const result = await runReconciliation(companyId, filter);
      const parts = [
        `${plural(result.nb_propositions, "proposition")}, dont ${plural(result.nb_fortes, "forte")}`,
      ];
      if (result.nb_groupes) {
        parts.push(`${plural(result.nb_groupes, "groupe")} de plusieurs opérations`);
      }
      if (result.nb_operations_ambigues > 0) {
        parts.push(`${plural(result.nb_operations_ambigues, "opération")} ambiguë(s) à vérifier`);
      }
      reload(`Rapprochement lancé : ${parts.join(" ; ")}.`);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Le rapprochement a échoué.", "error");
    } finally {
      setRunning(false);
    }
  }

  /** Recherche élargie (20/10/2026) : lignes encore libres, même n° et même montant, ± 1 an. */
  async function runElargie() {
    setRunning(true);
    try {
      const result = await runReconciliationElargie(companyId, filter);
      reload(
        `Recherche élargie (${result.fenetre_jours} jours) : ${plural(result.nb_propositions, "proposition")} éloignée(s).`,
      );
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "La recherche élargie a échoué.", "error");
    } finally {
      setRunning(false);
    }
  }

  // Tout ce qui est à vérifier : les propositions en attente et les opérations ambiguës
  const aVerifier =
    pending && ambigues && ecrituresAmbigues
      ? pending.correspondances.length + ambigues.total + ecrituresAmbigues.total
      : null;
  const logos = new Map(accounts.map((account) => [account.bank_code, account.bank_logo]));

  const filterKey = `${filter.bankAccountId ?? "tous"}|${filter.from}|${filter.to}`;

  return (
    <>
      {!pleinEcran && (
        <PageHeader
          title="Rapprochement"
          description="Rapprochement des transactions bancaires et des écritures comptables"
          actions={
            <div className="flex flex-wrap gap-2">
              {canValidate && (
                <>
                  <Button
                    variant="secondary"
                    icon={Search}
                    disabled={running || !!periodError}
                    onClick={runElargie}
                    title="Lignes encore libres : même n° et même montant, jusqu'à 1 an d'écart"
                  >
                    Recherche élargie (1 an)
                  </Button>
                  <Button icon={Play} disabled={running || !!periodError} onClick={run}>
                    {running ? "Rapprochement en cours…" : "Lancer le rapprochement"}
                  </Button>
                </>
              )}
            </div>
          }
        />
      )}

      <Card>
        <div className="space-y-4">
          <div
            className="flex gap-2 overflow-x-auto pb-1"
            role="group"
            aria-label="Compte bancaire"
          >
            <AccountButton
              active={filter.bankAccountId === undefined}
              onClick={() => changeFilter({ bankAccountId: undefined })}
            >
              Tous les comptes
            </AccountButton>
            {accounts.map((account) => (
              <AccountButton
                key={account.id}
                active={filter.bankAccountId === account.id}
                onClick={() => changeFilter({ bankAccountId: account.id })}
              >
                <AccountChipLabel account={account} />
              </AccountButton>
            ))}
          </div>

          <div className="flex flex-wrap items-end gap-x-3 gap-y-2">
            <div className="w-full max-w-[170px]">
              <Field label="Du" htmlFor="rapprochement-du">
                <DateInput
                  id="rapprochement-du"
                  value={filter.from}
                  onChange={(event) => changeFilter({ from: event.target.value })}
                />
              </Field>
            </div>
            <div className="w-full max-w-[170px]">
              <Field label="Au" htmlFor="rapprochement-au">
                <DateInput
                  id="rapprochement-au"
                  value={filter.to}
                  onChange={(event) => changeFilter({ to: event.target.value })}
                />
              </Field>
            </div>
            {periodError && (
              <p role="alert" className="pb-2 text-sm text-simtis-danger-fg">
                {periodError}
              </p>
            )}
            {/* Compteurs sur la ligne des dates (29/10/2026), visibles aussi en plein écran */}
            {periodeLue && !periodError && (
              <div
                className="ml-auto flex flex-wrap items-end gap-1 text-sm"
                role="group"
                aria-label="Résumé du rapprochement : un clic filtre les transactions"
              >
                {COMPTEURS.map(({ statut: value, label }) => (
                  <StatButton
                    key={value}
                    label={label}
                    value={compteurStatut(parStatut, value)}
                    active={tab === "rapprochement" && statut === value}
                    description={`Afficher les transactions « ${value} »`}
                    onClick={() => {
                      setTab("rapprochement");
                      setStatut((current) => toggleStatut(current, value));
                    }}
                  />
                ))}
                <StatButton
                  label={A_COMPTABILISER}
                  value={aComptabiliser ?? undefined}
                  active={tab === "rapprochement" && statut === A_COMPTABILISER}
                  description="Afficher les frais bancaires à passer dans Sage"
                  onClick={() => {
                    setTab("rapprochement");
                    setStatut((current) => toggleStatut(current, A_COMPTABILISER));
                  }}
                />
                <StatButton
                  label="Propositions en attente"
                  value={aVerifier ?? undefined}
                  active={tab === "propositions"}
                  description="Voir les propositions en attente"
                  onClick={() => setTab("propositions")}
                />
                {!!enCours && (
                  <div
                    className="rounded-[10px] px-3 py-2"
                    title="Opérations « (*) » en attente de leur définitive : jamais rapprochées"
                  >
                    <span className="block text-simtis-muted">En cours</span>
                    <span className="block text-[17px] font-semibold text-simtis-warning-fg tabular-nums">
                      {enCours}
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </Card>

      {periodeLue && !periodError && (
        <div className="flex flex-wrap items-end justify-between gap-2 border-b border-simtis-border">
          <div className="flex gap-2" role="tablist" aria-label="Vue du rapprochement">
            {(
              [
                ["rapprochement", "Rapprochement", GitCompareArrows],
                [
                  "propositions",
                  `Propositions${aVerifier !== null ? ` (${aVerifier})` : ""}`,
                  ListChecks,
                ],
                ["historique", "Historique", History],
              ] as const
            ).map(([value, label, Icon]) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={tab === value}
                onClick={() => setTab(value)}
                className={cn(
                  "-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition-colors duration-200",
                  tab === value
                    ? "border-simtis-primary text-simtis-primary-dark"
                    : "border-transparent text-simtis-muted hover:text-simtis-primary",
                )}
              >
                <Icon className="h-4 w-4" aria-hidden />
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {periodeLue && !periodError && tab === "propositions" && (
        <ProposalsTab
          companyId={companyId}
          pending={pending}
          logos={logos}
          canValidate={canValidate}
          canManageDiscrepancies={canManageDiscrepancies}
          onChanged={reload}
          onOpen={(item) => {
            setTab("rapprochement");
            setStatut("");
            setOperation(operationOf(item));
          }}
          ambigues={ambigues}
          typeOperation={typePropositions}
          onTypeOperation={(value) => {
            setTypePropositions(value);
            setAmbiguPage({ cle: cleAmbigues, page: 1 });
          }}
          onAmbiguPage={(page) => setAmbiguPage({ cle: cleAmbigues, page })}
          ecrituresAmbigues={ecrituresAmbigues}
          onEcrituresAmbiguesPage={(page) => setEcrAmbiguPage({ cle: cleAmbigues, page })}
          onOpenOperation={(selected) => {
            setTab("rapprochement");
            setStatut("");
            setOperation(selected);
          }}
        />
      )}

      {periodeLue && !periodError && tab === "historique" && (
        <HistoryTab
          key={`hist-${filterKey}`}
          companyId={companyId}
          filter={filter}
          canValidate={canValidate}
          reloadKey={reloadKey}
          onChanged={reload}
        />
      )}

      {periodeLue && !periodError && tab === "rapprochement" && statut === A_COMPTABILISER && (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center justify-end gap-3">
            <Button
              variant="secondary"
              icon={FileSpreadsheet}
              disabled={exporting}
              onClick={exporterPourBanque}
              title="Frais de plus de 200 DH (hors droits de timbre) à justifier"
            >
              Exporter pour la banque
            </Button>
            {canPrepare && (
              <span className="text-sm text-simtis-muted">
                {plural(totalAExporter, "écriture")} de frais à exporter
              </span>
            )}
            {canPrepare && (
              <Button
                icon={Download}
                disabled={exporting || totalAExporter === 0}
                onClick={exporterPourSage}
              >
                Exporter pour Sage ({totalAExporter})
              </Button>
            )}
          </div>
          <FraisCard
            companyId={companyId}
            filter={filter}
            reloadKey={reloadKey}
            canPrepare={canPrepare}
            onChanged={reload}
            onAExporter={setTotalAExporter}
            onLancer={canValidate ? run : undefined}
          />
        </div>
      )}

      {periodeLue && !periodError && tab === "rapprochement" && (
        <div
          ref={zoneRef}
          className="space-y-3"
          style={{ "--hauteur-bandeau": `${hauteurBandeau}px` } as CSSProperties}
        >
          {/* Bandeau de correspondance (28/10/2026) : montants cochés et écart, visible au défilement */}
          <div
            ref={bandeauRef}
            className={cn(
              "sticky z-10",
              pleinEcran ? "top-0" : "top-[var(--simtis-header-height)]",
            )}
          >
            <PanierPanel
              operations={panierOps}
              ecritures={panierEcr}
              canValidate={canValidate}
              onRetirerOperation={(op) => setPanierOps((l) => basculerLigne(l, op))}
              onRetirerEcriture={(e) => setPanierEcr((l) => basculerLigne(l, e))}
              onVider={viderPanier}
              onDone={(message) => {
                viderPanier();
                reload(message);
              }}
              pleinEcran={pleinEcran}
              onPleinEcran={() => setPleinEcran(!pleinEcran)}
            />
          </div>
          <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-3 xl:grid-cols-2">
            <TransactionsPane
              key={`tx-${filterKey}`}
              pleinEcran={pleinEcran}
              companyId={companyId}
              filter={filter}
              reloadKey={reloadKey}
              selectedId={operation?.id ?? null}
              coches={{
                ids: panierOps.map((op) => op.id),
                onToggle: (row) => setPanierOps((l) => basculerLigne(l, row)),
              }}
              onSelect={setOperation}
              onLoaded={handleOperations}
              statut={statut}
              onStatutChange={setStatut}
            />
            <EntriesPane
              key={`ec-${filterKey}`}
              pleinEcran={pleinEcran}
              companyId={companyId}
              filter={filter}
              reloadKey={reloadKey}
              selectedId={entry?.id ?? null}
              coches={{
                ids: panierEcr.map((e) => e.id),
                onToggle: (row) => setPanierEcr((l) => basculerLigne(l, row)),
              }}
              onSelect={setEntry}
              onLoaded={handleEntries}
            />
          </div>
        </div>
      )}

      <Modal open={!!(operation || entry)} onClose={fermerDetail} title="Détail du rapprochement">
        {(operation || entry) && (
          <MatchPanel
            key={operation?.id ?? `e${entry?.id ?? ""}`}
            companyId={companyId}
            operation={operation}
            entry={entry}
            canValidate={canValidate}
            canManageDiscrepancies={canManageDiscrepancies}
            reloadKey={reloadKey}
            onChanged={reload}
          />
        )}
      </Modal>
    </>
  );
}
