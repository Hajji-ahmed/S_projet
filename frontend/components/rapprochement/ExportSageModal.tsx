"use client";

import { Inbox } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";

import { BankLabel } from "@/components/banks/BankLabel";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { FormModal } from "@/components/ui/FormModal";
import { LoadingState } from "@/components/ui/LoadingState";
import { ApiError } from "@/lib/api";
import { erreurPiece, libelleMois, normaliserPiece, prefixePiece, seriePieces } from "@/lib/piece";
import { saveFile } from "@/lib/statements";
import { exporterFrais, listerAExporter } from "@/services/frais";
import type { AExporter } from "@/types/frais";

function plural(n: number, word: string): string {
  return `${n} ${word}${n > 1 ? "s" : ""}`;
}

type Props = {
  companyId: number;
  onClose: () => void;
  /** Export fait : message à afficher, la liste des frais se recharge. */
  onExported: (message: string) => void;
};

/** « Exporter pour Sage » (09/11/2026) : une banque, un mois, et le N° de la première pièce donné
 * par le comptable ; les écritures se numérotent à la suite et ne s'exportent qu'une fois.
 * À monter seulement quand la fenêtre s'ouvre (état neuf à chaque ouverture). */
export function ExportSageModal({ companyId, onClose, onExported }: Props) {
  const id = useId();
  const [groupes, setGroupes] = useState<AExporter[] | null>(null);
  const [chargement, setChargement] = useState<string | null>(null);
  const [bankId, setBankId] = useState<number | null>(null);
  const [mois, setMois] = useState<string | null>(null);
  const [premiere, setPremiere] = useState("");
  const [touche, setTouche] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let actif = true;
    listerAExporter(companyId)
      .then((result) => actif && setGroupes(result))
      .catch(
        (err) =>
          actif && setChargement(err instanceof ApiError ? err.message : "Chargement impossible."),
      );
    return () => {
      actif = false;
    };
  }, [companyId]);

  const banques = useMemo(() => {
    const vues = new Map<number, AExporter>();
    for (const groupe of groupes ?? [])
      if (!vues.has(groupe.bank_id)) vues.set(groupe.bank_id, groupe);
    return [...vues.values()];
  }, [groupes]);
  const banque = banques.find((item) => item.bank_id === bankId) ?? banques[0];
  const moisDeLaBanque = (groupes ?? []).filter((item) => item.bank_id === banque?.bank_id);
  const groupe = moisDeLaBanque.find((item) => item.mois === mois) ?? moisDeLaBanque[0];

  const erreur = groupe ? erreurPiece(premiere, groupe.bank_code, groupe.mois, groupe.nb) : null;
  const serie =
    groupe && !erreur ? seriePieces(premiere, groupe.bank_code, groupe.mois, groupe.nb) : null;

  async function exporter() {
    setTouche(true);
    if (!groupe || erreur) return;
    setSubmitting(true);
    setError(null);
    try {
      const blob = await exporterFrais(
        companyId,
        groupe.bank_id,
        groupe.mois,
        normaliserPiece(premiere),
      );
      saveFile(blob, `ecritures-frais-${groupe.bank_code}-${groupe.mois}.csv`);
      onExported(
        `${plural(groupe.nb, "écriture")} ${groupe.bank_code} de ${libelleMois(groupe.mois)} ` +
          `exportée${groupe.nb > 1 ? "s" : ""} pour Sage` +
          (serie ? ` (${serie.premiere} à ${serie.derniere}).` : "."),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "L'export a échoué.");
      setSubmitting(false);
    }
  }

  return (
    <FormModal
      open
      title="Exporter pour Sage"
      onClose={onClose}
      onSubmit={exporter}
      submitLabel="Exporter"
      submitting={submitting}
      error={error ?? chargement}
    >
      {groupes === null && !chargement && <LoadingState rows={3} />}
      {groupes !== null && groupes.length === 0 && (
        <EmptyState icon={Inbox} message="Aucune écriture de frais à exporter." />
      )}
      {groupe && banque && (
        <>
          <p className="text-sm text-simtis-muted">
            Un fichier par banque et par mois. Chaque écriture ne s&apos;exporte qu&apos;une fois.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Banque" htmlFor={`${id}-banque`} required>
              <Select
                id={`${id}-banque`}
                value={String(banque.bank_id)}
                onChange={(event) => {
                  setBankId(Number(event.target.value));
                  setMois(null);
                }}
                options={banques.map((item) => ({
                  value: String(item.bank_id),
                  label: item.bank_code,
                }))}
              />
            </Field>
            <Field label="Mois" htmlFor={`${id}-mois`} required>
              <Select
                id={`${id}-mois`}
                value={groupe.mois}
                onChange={(event) => setMois(event.target.value)}
                options={moisDeLaBanque.map((item) => ({
                  value: item.mois,
                  label: `${libelleMois(item.mois)} (${item.nb})`,
                }))}
              />
            </Field>
          </div>
          <Field
            label="N° de la première pièce"
            htmlFor={`${id}-piece`}
            required
            error={touche && erreur ? erreur : undefined}
            hint={`Par exemple ${prefixePiece(groupe.bank_code, groupe.mois)}001 ; les suivantes se numérotent à la suite.`}
          >
            <TextInput
              id={`${id}-piece`}
              value={premiere}
              invalid={touche && Boolean(erreur)}
              placeholder={`${prefixePiece(groupe.bank_code, groupe.mois)}001`}
              autoComplete="off"
              maxLength={20}
              onChange={(event) => setPremiere(event.target.value)}
              onBlur={() => setTouche(true)}
            />
          </Field>
          <div className="flex flex-wrap items-center gap-2 rounded-[10px] bg-simtis-surface px-3 py-2.5 text-sm text-simtis-text">
            <BankLabel code={groupe.bank_code} logo={groupe.bank_logo} />
            <span>
              {plural(groupe.nb, "écriture")}
              {serie ? (
                <>
                  {" "}
                  : <span className="font-medium tabular-nums">{serie.premiere}</span>
                  {groupe.nb > 1 && (
                    <>
                      {" "}
                      à <span className="font-medium tabular-nums">{serie.derniere}</span>
                    </>
                  )}
                </>
              ) : (
                " à numéroter"
              )}
            </span>
          </div>
        </>
      )}
    </FormModal>
  );
}
