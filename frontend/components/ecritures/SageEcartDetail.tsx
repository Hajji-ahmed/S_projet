"use client";

import { GitCompareArrows, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { Button } from "@/components/ui/Button";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { finNumero } from "@/lib/accounts";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/balances";
import { cn } from "@/lib/cn";
import { formatAmount, formatNombre } from "@/lib/format";
import { difference, etatEcart, sensEcart, veille } from "@/lib/sageEcart";
import { sageComparaison, sageEcart } from "@/services/accounting";
import type {
  EcritureAbsente,
  LigneComptable,
  SageComparaison,
  SageEcartDetail as Detail,
  SageLigne,
} from "@/types/accounting";

type LigneDetail = {
  cle: string;
  libelle: ReactNode;
  sage: string | null;
  simtis: string | null;
  ecart: string | null;
  nb?: string;
};

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : "Impossible de lire la base Sage.";
}

/** Montant d'écart : vert à 0, rouge sinon, tiret sans comparaison possible. */
export function EcartBadge({ ecart }: { ecart: string | null | undefined }) {
  const etat = etatEcart(ecart);
  if (etat === "inconnu") return <span className="text-simtis-muted">-</span>;
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2.5 py-0.5 text-xs leading-5 font-semibold whitespace-nowrap tabular-nums",
        etat === "aucun"
          ? "bg-simtis-success-bg text-simtis-success-fg"
          : "bg-simtis-danger-bg text-simtis-danger-fg",
      )}
    >
      {etat === "aucun" ? "Aucun écart" : formatAmount(ecart ?? null, "DH")}
    </span>
  );
}

/**
 * D'où vient l'écart entre le solde Sage et le solde SIMTIS d'un compte (21/11/2026) : départ,
 * journaux, écritures SIMTIS pas encore dans Sage, lignes Sage hors journaux de banque ; et, sur
 * demande, les écritures présentes d'un seul côté.
 */
export function SageEcartDetail({
  bankAccountId,
  jour,
  logos,
  onClose,
}: {
  bankAccountId: number;
  jour: string;
  logos: Map<string, string | null>;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [comparaison, setComparaison] = useState<SageComparaison | null>(null);
  const [comparaisonErreur, setComparaisonErreur] = useState<string | null>(null);
  const [compare, setCompare] = useState(false);

  useEffect(() => {
    let annule = false;
    sageEcart(bankAccountId, jour).then(
      (result) => {
        if (annule) return;
        setDetail(result);
        setErreur(null);
      },
      (error) => {
        if (!annule) setErreur(message(error));
      },
    );
    return () => {
      annule = true;
    };
  }, [bankAccountId, jour, version]);

  async function comparer() {
    setCompare(true);
    setComparaisonErreur(null);
    try {
      setComparaison(await sageComparaison(bankAccountId, jour));
    } catch (error) {
      setComparaisonErreur(message(error));
    } finally {
      setCompare(false);
    }
  }

  const titre = detail
    ? `${detail.solde.bank_code} · ${finNumero(detail.solde.numero)}`
    : "Écart avec Sage";

  const lignes: LigneDetail[] = detail
    ? [
        {
          cle: "depart",
          libelle: (
            <span>
              Solde de départ
              <span className="block text-xs text-simtis-muted">
                Sage : à-nouveau du {formatDate(detail.solde.debut)} · SIMTIS : solde au{" "}
                {formatDate(veille(detail.debut_simtis))}
              </span>
            </span>
          ),
          sage: detail.depart_sage,
          simtis: detail.depart_simtis,
          ecart:
            detail.depart_simtis === null
              ? null
              : difference(detail.depart_sage, detail.depart_simtis),
        },
        ...detail.journaux.map((j) => ({
          cle: `j-${j.journal}`,
          libelle: (
            <span>
              Journal {j.journal}
              <span className="block text-xs text-simtis-muted">
                {j.banque ? "Journal de banque du compte" : "Hors journaux de banque du compte"}
              </span>
            </span>
          ),
          sage: j.sage,
          simtis: j.simtis,
          ecart: j.ecart,
          nb: `${formatNombre(j.nb_sage)} / ${formatNombre(j.nb_simtis)}`,
        })),
        ...(detail.nb_non_exportees > 0
          ? [
              {
                cle: "non-exportees",
                libelle: (
                  <span>
                    Écritures SIMTIS pas encore exportées vers Sage
                    <span className="block text-xs text-simtis-muted">
                      Frais et saisies SIMTIS : elles arrivent dans Sage à l&apos;export
                    </span>
                  </span>
                ),
                sage: null,
                simtis: detail.non_exportees,
                ecart: difference("0.00", detail.non_exportees),
                nb: `- / ${formatNombre(detail.nb_non_exportees)}`,
              },
            ]
          : []),
        {
          cle: "total",
          libelle: <span className="font-semibold">Solde au {formatDate(detail.solde.jour)}</span>,
          sage: detail.solde.solde_sage,
          simtis: detail.solde.solde_simtis,
          ecart: detail.solde.ecart,
        },
      ]
    : [];

  const colonnes: Column<LigneDetail>[] = [
    { key: "libelle", header: "", render: (l) => l.libelle },
    {
      key: "sage",
      header: "Sage",
      align: "right",
      render: (l) => (l.sage === null ? "-" : formatAmount(l.sage, "DH")),
    },
    {
      key: "simtis",
      header: "SIMTIS",
      align: "right",
      render: (l) => (l.simtis === null ? "-" : formatAmount(l.simtis, "DH")),
    },
    {
      key: "ecart",
      header: "Écart",
      align: "right",
      render: (l) => <EcartBadge ecart={l.ecart} />,
    },
    {
      key: "nb",
      header: "Lignes Sage / SIMTIS",
      align: "right",
      render: (l) => <span className="text-simtis-muted tabular-nums">{l.nb ?? ""}</span>,
    },
  ];

  const colonnesSage: Column<SageLigne & Record<string, unknown>>[] = [
    {
      key: "date_ecriture",
      header: "Date",
      render: (l) => <span className="whitespace-nowrap">{formatDate(l.date_ecriture)}</span>,
    },
    { key: "journal", header: "Journal" },
    { key: "numero_piece", header: "N° pièce", render: (l) => l.numero_piece ?? "-" },
    {
      key: "libelle",
      header: "Libellé",
      render: (l) => <span className="block min-w-[200px]">{l.libelle ?? "-"}</span>,
    },
    {
      key: "debit",
      header: "Débit",
      align: "right",
      render: (l) => formatAmount(l.debit, "DH", { dashForZero: true }),
    },
    {
      key: "credit",
      header: "Crédit",
      align: "right",
      render: (l) => formatAmount(l.credit, "DH", { dashForZero: true }),
    },
  ];

  const colonnesAbsentesSimtis: Column<LigneComptable>[] = [
    {
      key: "date_ecriture",
      header: "Date",
      render: (l) => <span className="whitespace-nowrap">{formatDate(l.date_ecriture)}</span>,
    },
    { key: "journal", header: "Journal", render: (l) => l.journal ?? "-" },
    { key: "numero_piece", header: "N° pièce", render: (l) => l.numero_piece ?? "-" },
    {
      key: "libelle",
      header: "Libellé",
      render: (l) => <span className="block min-w-[200px]">{l.libelle ?? "-"}</span>,
    },
    {
      key: "debit",
      header: "Débit",
      align: "right",
      render: (l) => formatAmount(l.debit, "DH", { dashForZero: true }),
    },
    {
      key: "credit",
      header: "Crédit",
      align: "right",
      render: (l) => formatAmount(l.credit, "DH", { dashForZero: true }),
    },
  ];

  const colonnesAbsentesSage: Column<EcritureAbsente>[] = [
    {
      key: "date_ecriture",
      header: "Date",
      render: (a) => <span className="whitespace-nowrap">{formatDate(a.date_ecriture)}</span>,
    },
    { key: "journal", header: "Journal", render: (a) => a.journal ?? "-" },
    { key: "numero_piece", header: "N° pièce", render: (a) => a.numero_piece ?? "-" },
    {
      key: "libelle",
      header: "Libellé",
      render: (a) => (
        <span className="block min-w-[200px]">
          {a.libelle ?? "-"}
          {a.code_rapprochement && (
            <span className="block text-xs text-simtis-muted">
              Rapprochée {a.code_rapprochement}
            </span>
          )}
        </span>
      ),
    },
    {
      key: "debit",
      header: "Débit",
      align: "right",
      render: (a) => formatAmount(a.debit, "DH", { dashForZero: true }),
    },
    {
      key: "credit",
      header: "Crédit",
      align: "right",
      render: (a) => formatAmount(a.credit, "DH", { dashForZero: true }),
    },
  ];

  return (
    <section
      aria-label={`Écart avec Sage ${titre}`}
      className="mt-5 rounded-[12px] border border-simtis-border bg-simtis-background p-4"
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-[15px] font-semibold text-simtis-text">
            Écart avec Sage
            {detail && (
              <BankLabel code={detail.solde.bank_code} logo={logos.get(detail.solde.bank_code)}>
                {titre}
              </BankLabel>
            )}
          </h3>
          {detail && (
            <p className="mt-1 text-sm text-simtis-muted">
              Du {formatDate(detail.solde.debut)} au {formatDate(detail.solde.jour)}
              {sensEcart(detail.solde.ecart) ? ` · ${sensEcart(detail.solde.ecart)}` : ""}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Fermer le détail de l'écart"
          className="rounded-lg p-1 text-simtis-muted transition-colors hover:bg-simtis-light hover:text-simtis-primary"
        >
          <X className="h-5 w-5" aria-hidden />
        </button>
      </div>

      {erreur ? (
        <ErrorState message={erreur} onRetry={() => setVersion((v) => v + 1)} />
      ) : !detail ? (
        <LoadingState rows={3} />
      ) : (
        <>
          <DataTable columns={colonnes} rows={lignes} getRowKey={(l) => l.cle} />

          <h4 className="mt-5 mb-2 text-sm font-semibold text-simtis-text">
            Lignes Sage hors journaux de banque ({formatNombre(detail.hors_journaux.length)}
            {detail.hors_journaux_tronque ? " les plus récentes" : ""})
          </h4>
          <p className="mb-2 text-xs text-simtis-muted">
            Passées sur ce compte dans Sage par un autre journal (OD, autre banque…) : SIMTIS ne les
            importe pas, elles font un écart.
          </p>
          <DataTable
            columns={colonnesSage}
            rows={detail.hors_journaux as (SageLigne & Record<string, unknown>)[]}
            getRowKey={(l) =>
              `${l.date_ecriture}-${l.journal}-${l.numero_piece}-${l.debit}-${l.credit}`
            }
            emptyMessage="Aucune ligne hors journaux de banque sur la période."
          />

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button
              variant="secondary"
              icon={GitCompareArrows}
              onClick={comparer}
              disabled={compare}
            >
              {compare ? "Comparaison en cours..." : "Comparer ligne à ligne"}
            </Button>
            <span className="text-xs text-simtis-muted">
              Journaux de banque du compte, sur toute la période : peut prendre quelques secondes.
            </span>
          </div>
          {comparaisonErreur && (
            <p role="alert" className="mt-3 text-sm text-simtis-danger-fg">
              {comparaisonErreur}
            </p>
          )}
          {comparaison && (
            <div className="mt-4 space-y-4">
              <div>
                <h4 className="mb-2 text-sm font-semibold text-simtis-text">
                  Dans Sage, pas dans SIMTIS ({formatNombre(comparaison.absentes_de_simtis.length)})
                </h4>
                <DataTable
                  columns={colonnesAbsentesSimtis}
                  rows={comparaison.absentes_de_simtis}
                  getRowKey={(l) => String(l.numero)}
                  emptyMessage="Toutes les lignes Sage des journaux de banque sont dans SIMTIS."
                />
              </div>
              <div>
                <h4 className="mb-2 text-sm font-semibold text-simtis-text">
                  Dans SIMTIS, plus dans Sage ({formatNombre(comparaison.absentes_de_sage.length)})
                </h4>
                <DataTable
                  columns={colonnesAbsentesSage}
                  rows={comparaison.absentes_de_sage}
                  getRowKey={(a) => String(a.id)}
                  emptyMessage="Toutes les écritures Sage de SIMTIS sont encore dans Sage."
                />
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
