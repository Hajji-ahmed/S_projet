"use client";

import {
  ArrowRight,
  Download,
  FileSpreadsheet,
  GitCompareArrows,
  Landmark,
  Link2,
  Receipt,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { useCompany } from "@/components/company/CompanyProvider";
import { Button } from "@/components/ui/Button";
import { DateInput, Field } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api";
import { businessToday } from "@/lib/balances";
import { moisEnCours } from "@/lib/dashboard";
import { PERMISSIONS, hasAnyPermission } from "@/lib/permissions";
import { saveFile } from "@/lib/statements";
import { exportLettrage } from "@/services/reconciliation";
import { exportEtatRapprochement, exportPosition } from "@/services/rapports";

/** Rapports (P16.4) : exports Excel de la société active. Chaque export est audité. */
export function RapportsView() {
  const { company } = useCompany();
  const { user } = useAuth();
  const granted = user?.permissions ?? [];
  const peutPosition = hasAnyPermission(granted, [PERMISSIONS.POSITION_VIEW]);
  const peutRapprochement = hasAnyPermission(granted, [PERMISSIONS.RECONCILIATION_VIEW]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Rapports"
        description={`Exports Excel${company ? ` de ${company.nom}` : ""} : position, rapprochement, lettrage`}
      />
      {company && (
        <div className="grid gap-5 lg:grid-cols-2">
          <PositionRapport companyId={company.id} actif={peutPosition} />
          <EtatRapport companyId={company.id} actif={peutRapprochement} />
          <LettrageRapport companyId={company.id} actif={peutRapprochement} />
          <Rapport
            titre="Écritures de frais pour Sage"
            icon={Receipt}
            description="Les frais bancaires comptabilisés par SIMTIS, au format du grand livre Sage. L'export les marque comme exportés : il se fait depuis la carte « Frais bancaires » du rapprochement."
          >
            <Link
              href="/rapprochement"
              className="group inline-flex items-center gap-1 text-sm font-medium text-simtis-primary hover:text-simtis-primary-dark"
            >
              Ouvrir le rapprochement
              <ArrowRight
                className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5"
                aria-hidden
              />
            </Link>
          </Rapport>
        </div>
      )}
    </div>
  );
}

function Rapport({
  titre,
  icon: Icon,
  description,
  children,
}: {
  titre: string;
  icon: LucideIcon;
  description: string;
  children?: ReactNode;
}) {
  return (
    <section className="flex flex-col rounded-card border border-simtis-border bg-simtis-card p-5 shadow-simtis lg:p-6">
      <header className="flex items-start gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-[12px] bg-simtis-light text-simtis-primary">
          <Icon className="h-5 w-5" strokeWidth={1.75} aria-hidden />
        </span>
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-base font-semibold tracking-tight text-simtis-text">
            {titre}
          </h2>
          <p className="mt-1 text-sm text-simtis-muted">{description}</p>
        </div>
      </header>
      {children && <div className="mt-4 flex flex-1 flex-col justify-end">{children}</div>}
    </section>
  );
}

/** Bouton « Télécharger » commun : appelle l'export, enregistre le fichier, signale l'erreur. */
function useTelechargement() {
  const { toast } = useToast();
  const [envoi, setEnvoi] = useState(false);
  async function telecharger(appel: () => Promise<Blob>, nom: string) {
    setEnvoi(true);
    try {
      saveFile(await appel(), nom);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Export impossible.", "error");
    } finally {
      setEnvoi(false);
    }
  }
  return { envoi, telecharger };
}

function SansDroit() {
  return <p className="text-sm text-simtis-muted">Vous n&apos;avez pas la permission requise.</p>;
}

function PositionRapport({ companyId, actif }: { companyId: number; actif: boolean }) {
  const [jour, setJour] = useState(businessToday);
  const { envoi, telecharger } = useTelechargement();
  return (
    <Rapport
      titre="Position du jour"
      icon={Landmark}
      description="Le tableau Banques à une date : LIGNE, facilité de caisse jour par jour, TOTAL, DEPASSEMENT et Disponible Fc reel."
    >
      {actif ? (
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-[170px]">
            <Field label="Date" htmlFor="rapport-position-date">
              <DateInput
                id="rapport-position-date"
                value={jour}
                max={businessToday()}
                onChange={(e) => setJour(e.target.value)}
              />
            </Field>
          </div>
          <Button
            icon={Download}
            disabled={envoi || !jour}
            onClick={() =>
              telecharger(
                () => exportPosition(companyId, jour),
                `position-${jour.replaceAll("-", "")}.xlsx`,
              )
            }
          >
            {envoi ? "Préparation..." : "Télécharger"}
          </Button>
        </div>
      ) : (
        <SansDroit />
      )}
    </Rapport>
  );
}

function Periode({
  id,
  periode,
  onChange,
}: {
  id: string;
  periode: { from: string; to: string };
  onChange: (periode: { from: string; to: string }) => void;
}) {
  return (
    <>
      <div className="w-[160px]">
        <Field label="Du" htmlFor={`${id}-from`}>
          <DateInput
            id={`${id}-from`}
            value={periode.from}
            onChange={(e) => onChange({ ...periode, from: e.target.value })}
          />
        </Field>
      </div>
      <div className="w-[160px]">
        <Field label="Au" htmlFor={`${id}-to`}>
          <DateInput
            id={`${id}-to`}
            value={periode.to}
            onChange={(e) => onChange({ ...periode, to: e.target.value })}
          />
        </Field>
      </div>
    </>
  );
}

function periodeValide(periode: { from: string; to: string }): boolean {
  return periode.from !== "" && periode.to !== "" && periode.from <= periode.to;
}

function EtatRapport({ companyId, actif }: { companyId: number; actif: boolean }) {
  const [periode, setPeriode] = useState(() => moisEnCours(businessToday()));
  const { envoi, telecharger } = useTelechargement();
  return (
    <Rapport
      titre="État de rapprochement"
      icon={GitCompareArrows}
      description="Par compte : opérations rapprochées, à vérifier, non rapprochées et taux ; puis la liste des opérations qui restent à rapprocher."
    >
      {actif ? (
        <div className="flex flex-wrap items-end gap-3">
          <Periode id="rapport-etat" periode={periode} onChange={setPeriode} />
          <Button
            icon={Download}
            disabled={envoi || !periodeValide(periode)}
            onClick={() =>
              telecharger(
                () => exportEtatRapprochement(companyId, periode.from, periode.to),
                `etat-rapprochement-${periode.from}-${periode.to}.xlsx`,
              )
            }
          >
            {envoi ? "Préparation..." : "Télécharger"}
          </Button>
        </div>
      ) : (
        <SansDroit />
      )}
    </Rapport>
  );
}

function LettrageRapport({ companyId, actif }: { companyId: number; actif: boolean }) {
  const [periode, setPeriode] = useState(() => moisEnCours(businessToday()));
  const { envoi, telecharger } = useTelechargement();
  return (
    <Rapport
      titre="Lettrage"
      icon={Link2}
      description="Chaque rapprochement validé de la période, par code : opérations du relevé puis écritures Sage."
    >
      {actif ? (
        <div className="flex flex-wrap items-end gap-3">
          <Periode id="rapport-lettrage" periode={periode} onChange={setPeriode} />
          <Button
            icon={FileSpreadsheet}
            disabled={envoi || !periodeValide(periode)}
            onClick={() =>
              telecharger(
                () => exportLettrage(companyId, { from: periode.from, to: periode.to }),
                `lettrage-${periode.from}-${periode.to}.xlsx`,
              )
            }
          >
            {envoi ? "Préparation..." : "Télécharger"}
          </Button>
        </div>
      ) : (
        <SansDroit />
      )}
    </Rapport>
  );
}
