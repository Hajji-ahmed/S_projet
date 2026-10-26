"use client";

import { ChevronDown, PenLine, Scale } from "lucide-react";
import { useEffect, useState, useSyncExternalStore } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/ErrorState";
import { DateInput, Field, TextInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { finNumero } from "@/lib/accounts";
import { ApiError } from "@/lib/api";
import {
  businessToday,
  currencySuffix,
  formatDate,
  normalizeSignedAmountInput,
} from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/format";
import { repli } from "@/lib/repli";
import { listSoldesComptables, setSoldeOuverture } from "@/services/accounting";
import type { SoldeComptable } from "@/types/accounting";

type Ligne = SoldeComptable & Record<string, unknown>;

// Carte réduite par défaut ; le dernier choix est gardé dans le navigateur (26/10/2026)
const OUVERTURE = repli("simtis.ecritures.solde-comptable", false);

/**
 * Solde comptable (Sage) de chaque compte à une date (26/10/2026) : solde d'ouverture saisi + débits
 * − crédits des écritures après lui ; comparé au solde du relevé à la même date.
 */
export function SoldeComptableCard({
  companyId,
  logos,
  canEdit,
  reloadKey,
}: {
  companyId: number;
  logos: Map<string, string | null>;
  canEdit: boolean;
  reloadKey: number;
}) {
  const { toast } = useToast();
  const [jour, setJour] = useState(businessToday());
  const [lignes, setLignes] = useState<SoldeComptable[] | null>(null);
  const [erreur, setErreur] = useState(false);
  const [version, setVersion] = useState(0);
  const [edition, setEdition] = useState<SoldeComptable | null>(null);
  const ouverte = useSyncExternalStore(OUVERTURE.subscribe, OUVERTURE.lire, () => false);
  const basculer = () => OUVERTURE.ecrire(!ouverte);

  useEffect(() => {
    // Réduite : rien n'est demandé au serveur
    if (!ouverte) return;
    let annule = false;
    listSoldesComptables(companyId, jour).then(
      (items) => {
        if (annule) return;
        setLignes(items);
        setErreur(false);
      },
      () => {
        if (!annule) setErreur(true);
      },
    );
    return () => {
      annule = true;
    };
  }, [companyId, jour, reloadKey, version, ouverte]);

  const unite = (l: SoldeComptable) => currencySuffix(l.devise);
  const colonnes: Column<Ligne>[] = [
    {
      key: "compte",
      header: "Compte",
      render: (l) => (
        <span className="block min-w-[160px]">
          <BankLabel code={l.bank_code} logo={logos.get(l.bank_code) ?? null}>
            {l.bank_code} · {l.devise}
          </BankLabel>
          <span className="block text-xs text-simtis-muted tabular-nums">
            {finNumero(l.numero)}
          </span>
        </span>
      ),
    },
    {
      key: "ouverture",
      header: "Ouverture",
      align: "right",
      render: (l) =>
        l.ouverture === null ? (
          <span className="text-simtis-warning-fg">À saisir</span>
        ) : (
          <span>
            {formatAmount(l.ouverture, "DH")}
            <span className="block text-xs text-simtis-muted">
              au {formatDate(l.date_ouverture)}
            </span>
          </span>
        ),
    },
    { key: "debit", header: "Débits", align: "right", render: (l) => formatAmount(l.debit, "DH") },
    {
      key: "credit",
      header: "Crédits",
      align: "right",
      render: (l) => formatAmount(l.credit, "DH"),
    },
    {
      key: "solde",
      header: "Solde comptable",
      align: "right",
      render: (l) =>
        l.solde === null ? (
          <span className="text-simtis-muted">-</span>
        ) : (
          <span className="font-semibold">
            {formatAmount(l.solde, "DH")}
            {l.devise !== "MAD" && (
              <span className="block text-xs font-normal text-simtis-muted">
                {l.solde_devise === null
                  ? "devise à saisir"
                  : formatAmount(l.solde_devise, l.devise)}
              </span>
            )}
            {l.nb_non_exportees > 0 && (
              <span className="block text-xs font-normal text-simtis-warning-fg">
                dont {l.nb_non_exportees} écriture{l.nb_non_exportees > 1 ? "s" : ""} pas encore
                dans Sage
              </span>
            )}
          </span>
        ),
    },
    {
      key: "solde_bancaire",
      header: "Solde bancaire",
      align: "right",
      render: (l) => (
        <span
          title={
            l.date_solde_bancaire ? `Relevé au ${formatDate(l.date_solde_bancaire)}` : undefined
          }
        >
          {formatAmount(l.solde_bancaire, unite(l))}
        </span>
      ),
    },
    {
      key: "ecart",
      header: "Écart",
      align: "right",
      render: (l) => (
        <span
          className={cn(
            l.ecart !== null && Number(l.ecart) !== 0 && "font-semibold text-simtis-danger-fg",
            l.ecart !== null && Number(l.ecart) === 0 && "text-simtis-success-fg",
          )}
        >
          {formatAmount(l.ecart, unite(l))}
        </span>
      ),
    },
    ...(canEdit
      ? [
          {
            key: "actions",
            header: "",
            align: "right" as const,
            render: (l: Ligne) => (
              <button
                type="button"
                onClick={() => setEdition(l)}
                aria-label={`Solde d'ouverture du compte ${l.bank_code} ${l.devise}`}
                title="Saisir le solde comptable d'ouverture"
                className="rounded-lg p-2 text-simtis-muted transition-colors hover:bg-simtis-light hover:text-simtis-primary"
              >
                <PenLine className="h-4 w-4" aria-hidden />
              </button>
            ),
          },
        ]
      : []),
  ];

  return (
    <Card>
      <button
        type="button"
        onClick={basculer}
        aria-expanded={ouverte}
        className="flex w-full items-center gap-3 rounded-[10px] text-left"
      >
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-[10px] bg-simtis-light text-simtis-primary">
          <Scale className="h-5 w-5" aria-hidden />
        </span>
        <span className="flex-1 text-base font-semibold tracking-tight text-simtis-text">
          Solde comptable
        </span>
        <ChevronDown
          className={cn(
            "h-5 w-5 text-simtis-muted transition-transform duration-200",
            ouverte && "rotate-180",
          )}
          aria-hidden
        />
      </button>
      {ouverte && (
        <div className="mt-4">
          <div className="mb-4 flex flex-wrap items-end gap-3">
            <div className="w-full max-w-[180px]">
              <Field label="À la date du" htmlFor="solde-compta-date">
                <DateInput
                  id="solde-compta-date"
                  value={jour}
                  max={businessToday()}
                  onChange={(e) => e.target.value && setJour(e.target.value)}
                />
              </Field>
            </div>
          </div>
          {erreur ? (
            <ErrorState
              message="Impossible de calculer les soldes comptables."
              onRetry={() => setVersion((v) => v + 1)}
            />
          ) : lignes === null ? (
            <LoadingState rows={2} />
          ) : (
            <DataTable
              columns={colonnes}
              rows={lignes as Ligne[]}
              getRowKey={(l) => String(l.bank_account_id)}
              emptyMessage="Aucun compte avec un journal Sage."
            />
          )}
        </div>
      )}
      {edition && (
        <OuvertureModal
          ligne={edition}
          onClose={() => setEdition(null)}
          onSaved={() => {
            setEdition(null);
            toast("Solde d'ouverture enregistré.");
            setVersion((v) => v + 1);
          }}
        />
      )}
    </Card>
  );
}

function OuvertureModal({
  ligne,
  onClose,
  onSaved,
}: {
  ligne: SoldeComptable;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [date, setDate] = useState(ligne.date_ouverture ?? "");
  const [solde, setSolde] = useState(ligne.ouverture ?? "");
  const [soldeDevise, setSoldeDevise] = useState(ligne.ouverture_devise ?? "");
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const enDevise = ligne.devise !== "MAD";
  const montant = normalizeSignedAmountInput(solde);
  const montantDevise = enDevise ? normalizeSignedAmountInput(soldeDevise) : null;
  const pret = !!date && montant !== null && (!enDevise || montantDevise !== null);

  async function enregistrer(effacer = false) {
    setEnvoi(true);
    setErreur(null);
    try {
      await setSoldeOuverture(ligne.bank_account_id, {
        date_ouverture: effacer ? null : date,
        solde: effacer ? null : montant,
        solde_devise: effacer || !enDevise ? null : montantDevise,
      });
      onSaved();
    } catch (error) {
      setErreur(error instanceof ApiError ? error.message : "Enregistrement impossible.");
      setEnvoi(false);
    }
  }

  return (
    <Modal
      open
      title={`Solde comptable d'ouverture · ${ligne.bank_code} ${ligne.devise}`}
      onClose={() => !envoi && onClose()}
      footer={
        <>
          {ligne.ouverture !== null && (
            <Button variant="ghost" onClick={() => enregistrer(true)} disabled={envoi}>
              Effacer
            </Button>
          )}
          <Button variant="secondary" onClick={onClose} disabled={envoi}>
            Annuler
          </Button>
          <Button onClick={() => enregistrer()} disabled={envoi || !pret}>
            {envoi ? "Enregistrement..." : "Enregistrer"}
          </Button>
        </>
      }
    >
      <p className="text-sm text-simtis-muted">
        Le solde du compte dans le grand livre Sage à une date (ex. 31/12/2025). Débiteur = positif,
        créditeur = négatif. Les écritures datées après cette date s&apos;y ajoutent.
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Field label="Date" htmlFor="ouv-date" required>
          <DateInput
            id="ouv-date"
            value={date}
            max={businessToday()}
            onChange={(e) => setDate(e.target.value)}
          />
        </Field>
        <Field
          label="Solde (DH)"
          htmlFor="ouv-solde"
          required
          error={
            solde && montant === null ? "Montant au centime, « - » pour créditeur." : undefined
          }
        >
          <TextInput
            id="ouv-solde"
            value={solde}
            inputMode="decimal"
            placeholder="0,00"
            onChange={(e) => setSolde(e.target.value)}
          />
        </Field>
        {enDevise && (
          <Field label={`Solde en ${ligne.devise}`} htmlFor="ouv-devise" required>
            <TextInput
              id="ouv-devise"
              value={soldeDevise}
              inputMode="decimal"
              placeholder="0,00"
              onChange={(e) => setSoldeDevise(e.target.value)}
            />
          </Field>
        )}
      </div>
      {erreur && <p className="mt-3 text-sm text-simtis-danger-fg">{erreur}</p>}
    </Modal>
  );
}
