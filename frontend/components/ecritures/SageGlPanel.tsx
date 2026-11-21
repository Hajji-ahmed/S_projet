"use client";

import { CheckCheck, CircleAlert, Database, Download } from "lucide-react";
import { useEffect, useState } from "react";

import { SageCompteCard } from "@/components/ecritures/SageCompteCard";
import { Button } from "@/components/ui/Button";
import { DateInput, Field } from "@/components/ui/Field";
import { ApiError } from "@/lib/api";
import { businessToday } from "@/lib/balances";
import { formatNombre } from "@/lib/format";
import { absentesParDefaut, blocageImport, type BlocageImport } from "@/lib/importLines";
import { cochesParDefaut, comptesAValider, formatCopie, periodeParDefaut } from "@/lib/sage";
import { sageAnalyse, sageConfirm, sageEtat } from "@/services/accounting";
import type {
  ConfirmationComptable,
  SageAnalyse,
  SageAnalyseCompte,
  SageEtat,
} from "@/types/accounting";

type SageGlPanelProps = {
  companyId: number;
  logos: Map<string, string | null>;
  /** Un compte vient d'être importé : la page recharge ses écritures et son journal. */
  onImported: (confirmation: ConfirmationComptable) => void;
};

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Une erreur est survenue.";
}

/**
 * « Récupérer le GL » (21/11/2026) : le grand livre des comptes courants MAD est lu dans la base
 * Sage, un tableau par compte ; chaque compte se valide seul (« Valider ce compte ») ou tous
 * ensemble (« Tout valider »). Rien n'est importé sans clic.
 */
export function SageGlPanel({ companyId, logos, onImported }: SageGlPanelProps) {
  const [etat, setEtat] = useState<SageEtat | null>(null);
  const [etatErreur, setEtatErreur] = useState<string | null>(null);
  const [periode, setPeriode] = useState(() => periodeParDefaut(businessToday()));
  const [analyse, setAnalyse] = useState<SageAnalyse | null>(null);
  const [lecture, setLecture] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [coches, setCoches] = useState<Map<number, Set<number>>>(new Map());
  const [supprimees, setSupprimees] = useState<Map<number, Set<number>>>(new Map());
  const [importes, setImportes] = useState<Map<number, ConfirmationComptable>>(new Map());
  const [erreurs, setErreurs] = useState<Map<number, string>>(new Map());
  const [enCours, setEnCours] = useState<Set<number>>(new Set());

  useEffect(() => {
    let cancelled = false;
    sageEtat(companyId)
      .then((result) => {
        if (!cancelled) setEtat(result);
      })
      .catch((caught) => {
        if (!cancelled) setEtatErreur(errorMessage(caught));
      });
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  async function recuperer() {
    setLecture(true);
    setErreur(null);
    try {
      const result = await sageAnalyse(companyId, periode.du, periode.au);
      setAnalyse(result);
      setCoches(
        new Map(
          result.comptes.map((item) => [
            item.compte.bank_account_id,
            cochesParDefaut(item.analyse.lignes),
          ]),
        ),
      );
      setSupprimees(
        new Map(
          result.comptes.map((item) => [
            item.compte.bank_account_id,
            absentesParDefaut(item.analyse.ecritures_absentes ?? []),
          ]),
        ),
      );
      setImportes(new Map());
      setErreurs(new Map());
      setEtat((current) => current && { ...current, derniere_copie: result.derniere_copie });
    } catch (caught) {
      setAnalyse(null);
      setErreur(errorMessage(caught));
    } finally {
      setLecture(false);
    }
  }

  function cochesDe(item: SageAnalyseCompte): Set<number> {
    return coches.get(item.compte.bank_account_id) ?? new Set();
  }

  function supprimeesDe(item: SageAnalyseCompte): Set<number> {
    return supprimees.get(item.compte.bank_account_id) ?? new Set();
  }

  function blocageDe(item: SageAnalyseCompte): BlocageImport | null {
    const choisies = cochesDe(item);
    return blocageImport({
      dejaImporte: false,
      cochees: choisies.size,
      erreursCochees: item.analyse.lignes.filter(
        (line) => line.statut === "Erreur" && choisies.has(line.numero),
      ).length,
      correction: "Sage",
      suppressions: supprimeesDe(item).size,
    });
  }

  async function valider(item: SageAnalyseCompte): Promise<boolean> {
    if (!analyse) return false;
    const id = item.compte.bank_account_id;
    setEnCours((current) => new Set(current).add(id));
    setErreurs((current) => {
      const next = new Map(current);
      next.delete(id);
      return next;
    });
    try {
      const confirmation = await sageConfirm({
        companyId,
        bankAccountId: id,
        du: analyse.du,
        au: analyse.au,
        empreinte: item.empreinte,
        lignesChoisies: [...cochesDe(item)],
        ecrituresSupprimees: [...supprimeesDe(item)],
      });
      setImportes((current) => new Map(current).set(id, confirmation));
      onImported(confirmation);
      return true;
    } catch (caught) {
      setErreurs((current) => new Map(current).set(id, errorMessage(caught)));
      return false;
    } finally {
      setEnCours((current) => {
        const next = new Set(current);
        next.delete(id);
        return next;
      });
    }
  }

  const etats = new Map(
    (analyse?.comptes ?? []).map((item) => [
      item.compte.bank_account_id,
      { importe: importes.has(item.compte.bank_account_id), bloque: blocageDe(item) !== null },
    ]),
  );
  const aValider = analyse
    ? comptesAValider(
        analyse.comptes.map((item) => ({ ...item, bank_account_id: item.compte.bank_account_id })),
        etats,
      )
    : [];
  const lignesAValider = aValider.reduce((total, item) => total + cochesDe(item).size, 0);
  const occupe = lecture || enCours.size > 0;

  async function toutValider() {
    // Un compte après l'autre : chacun devient un import de l'historique, supprimable seul
    for (const item of aValider) {
      await valider(item);
    }
  }

  const copie = formatCopie(etat?.derniere_copie ?? null);
  const periodeInvalide = !periode.du || !periode.au || periode.du > periode.au;

  return (
    <div>
      {etatErreur && (
        <p role="alert" className="mb-3 text-sm text-simtis-danger-fg">
          {etatErreur}
        </p>
      )}
      {etat && (
        <p className="mb-4 flex flex-wrap items-center gap-2 text-sm text-simtis-muted">
          <Database className="h-4 w-4 shrink-0 text-simtis-primary" aria-hidden />
          {etat.configure && etat.base ? (
            <>
              Base Sage {etat.base}
              {copie ? ` · copiée le ${copie}` : ""} · comptes courants en dirhams :{" "}
              {etat.comptes.map((compte) => compte.bank_code).join(", ") || "aucun"}
            </>
          ) : (
            "Récupération depuis Sage indisponible"
          )}
        </p>
      )}
      {etat?.message && (
        <div
          role="alert"
          className="mb-4 flex items-start gap-2 rounded-lg bg-simtis-warning-bg px-3 py-2.5 text-sm text-simtis-warning-fg"
        >
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {etat.message}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-3">
        <div className="w-44">
          <Field label="Du" htmlFor="sage-du">
            <DateInput
              id="sage-du"
              value={periode.du}
              disabled={occupe}
              onChange={(event) => setPeriode((p) => ({ ...p, du: event.target.value }))}
            />
          </Field>
        </div>
        <div className="w-44">
          <Field label="Au" htmlFor="sage-au">
            <DateInput
              id="sage-au"
              value={periode.au}
              disabled={occupe}
              onChange={(event) => setPeriode((p) => ({ ...p, au: event.target.value }))}
            />
          </Field>
        </div>
        <Button
          icon={Download}
          onClick={recuperer}
          disabled={occupe || periodeInvalide || !etat?.configure}
        >
          {lecture ? "Lecture de Sage..." : "Récupérer le GL"}
        </Button>
        {analyse && (
          <Button
            variant="secondary"
            icon={CheckCheck}
            onClick={toutValider}
            disabled={occupe || aValider.length === 0}
            className="ml-auto"
          >
            Tout valider ({aValider.length} compte{aValider.length > 1 ? "s" : ""},{" "}
            {formatNombre(lignesAValider)} ligne{lignesAValider > 1 ? "s" : ""})
          </Button>
        )}
      </div>
      {periodeInvalide && (
        <p className="mt-2 text-sm text-simtis-danger-fg">
          La date de début doit précéder la date de fin.
        </p>
      )}
      {erreur && (
        <div
          role="alert"
          className="mt-4 flex items-start gap-2 rounded-lg bg-simtis-danger-bg px-3 py-2.5 text-sm text-simtis-danger-fg"
        >
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {erreur}
        </div>
      )}

      {analyse && (
        <div className="mt-6 space-y-5">
          {analyse.comptes.map((item) => {
            const id = item.compte.bank_account_id;
            return (
              <SageCompteCard
                key={id}
                item={item}
                logo={logos.get(item.compte.bank_code)}
                coches={cochesDe(item)}
                onCoches={(next) => setCoches((current) => new Map(current).set(id, next))}
                supprimees={supprimeesDe(item)}
                onSupprimees={(next) => setSupprimees((current) => new Map(current).set(id, next))}
                blocage={blocageDe(item)}
                importe={importes.get(id)}
                erreur={erreurs.get(id) ?? null}
                busy={enCours.has(id) || lecture}
                onValider={() => void valider(item)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
