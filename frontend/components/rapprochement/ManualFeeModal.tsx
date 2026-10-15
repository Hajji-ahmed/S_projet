"use client";

import { Check } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { DateInput, Field, NumberInput, TextInput } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { normalizeAmountInput } from "@/lib/accounts";
import { ApiError } from "@/lib/api";
import { formatAmount } from "@/lib/format";
import { LIBELLES_SUGGERES, sommeMontants, ventilerTva } from "@/lib/frais";
import { fromCents, toCents } from "@/lib/statementLines";
import { comptabiliserManuellement } from "@/services/frais";
import type { AutreFrais } from "@/types/frais";

type ManualFeeModalProps = {
  companyId: number;
  /** Opérations cochées, toutes du même compte bancaire. */
  operations: AutreFrais[];
  onClose: () => void;
  onDone: (message: string) => void;
};

const TAUX_PAR_DEFAUT = "10";

/** Montant saisi (« 150,5 ») en texte exact (« 150.50 »), ou null. */
function montant(saisie: string): string | null {
  const valeur = normalizeAmountInput(saisie);
  return valeur === null ? null : fromCents(toCents(valeur));
}

/**
 * Écriture saisie à la main pour des frais d'un même compte (13/10/2026) : libellé, date et, si le
 * montant contient de la TVA, le frais hors taxe et la TVA séparés. À monter seulement à
 * l'ouverture : son état repart de zéro.
 */
export function ManualFeeModal({ companyId, operations, onClose, onDone }: ManualFeeModalProps) {
  const somme = sommeMontants(operations.map((tx) => tx.montant));
  // Un frais (débit en banque) va au crédit du compte bancaire ; un remboursement au débit
  const remboursement = !somme.startsWith("-");
  const total = remboursement ? somme : somme.slice(1);
  const derniereDate =
    operations
      .map((tx) => tx.date_operation)
      .sort()
      .at(-1) ?? "";

  const [libelle, setLibelle] = useState("");
  const [date, setDate] = useState(derniereDate);
  const [avecTva, setAvecTva] = useState(false);
  const [taux, setTaux] = useState(TAUX_PAR_DEFAUT);
  const [ht, setHt] = useState("");
  const [tva, setTva] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function appliquerTaux(valeur: string) {
    setTaux(valeur);
    const ventilation = ventilerTva(total, valeur);
    if (ventilation) {
      setHt(ventilation.ht.replace(".", ","));
      setTva(ventilation.tva.replace(".", ","));
    }
  }

  function basculerTva(coche: boolean) {
    setAvecTva(coche);
    if (coche) appliquerTaux(taux);
  }

  // Modifier l'un des deux montants recalcule l'autre : HT + TVA = total
  function saisirHt(valeur: string) {
    setHt(valeur);
    const exact = montant(valeur);
    if (exact !== null) setTva(fromCents(toCents(total) - toCents(exact)).replace(".", ","));
  }

  function saisirTva(valeur: string) {
    setTva(valeur);
    const exact = montant(valeur);
    if (exact !== null) setHt(fromCents(toCents(total) - toCents(exact)).replace(".", ","));
  }

  const htExact = montant(ht);
  const tvaExacte = montant(tva);
  const erreurTva = !avecTva
    ? null
    : htExact === null || tvaExacte === null
      ? "Saisissez le frais hors taxe et la TVA (2 décimales au plus)."
      : toCents(htExact) <= BigInt(0) || toCents(tvaExacte) <= BigInt(0)
        ? "Le frais hors taxe et la TVA doivent être positifs."
        : toCents(htExact) + toCents(tvaExacte) !== toCents(total)
          ? `Frais HT + TVA doit faire exactement ${formatAmount(total, "DH")}.`
          : null;
  const tauxValide = ventilerTva(total, taux) !== null;
  const pret =
    libelle.trim() !== "" && date !== "" && !erreurTva && (!avecTva || tauxValide) && !busy;

  const lignes = avecTva
    ? [
        { type: "Frais", montant: htExact ?? "0" },
        { type: "TVA", montant: tvaExacte ?? "0" },
      ]
    : [{ type: "", montant: total }];

  async function valider() {
    setBusy(true);
    setError(null);
    try {
      const result = await comptabiliserManuellement({
        company_id: companyId,
        transaction_ids: operations.map((tx) => tx.id),
        libelle: libelle.trim(),
        date,
        taux_tva: avecTva ? taux.trim().replace(",", ".") : null,
        montant_tva: avecTva ? tvaExacte : null,
      });
      onDone(`Écriture ${result.codes[0]} comptabilisée et rapprochée.`);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "La comptabilisation a échoué.");
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Comptabiliser à la main"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Annuler
          </Button>
          <Button icon={Check} disabled={!pret} onClick={valider}>
            Valider l&apos;écriture
          </Button>
        </>
      }
    >
      {error && (
        <p
          role="alert"
          className="mb-3 rounded-[10px] bg-simtis-danger-bg px-3 py-2 text-simtis-danger-fg"
        >
          {error}
        </p>
      )}
      <p className="mb-4 text-sm text-simtis-muted">
        {operations.length} opération{operations.length > 1 ? "s" : ""} · total{" "}
        <span className="font-medium text-simtis-text tabular-nums">
          {formatAmount(total, "DH")}
        </span>{" "}
        {remboursement ? "(remboursement : au débit)" : "(au crédit du compte bancaire)"}
      </p>

      <div className="space-y-4">
        <Field label="Libellé de l'écriture" htmlFor="frais-manuel-libelle" required>
          <TextInput
            id="frais-manuel-libelle"
            value={libelle}
            maxLength={60}
            list="frais-manuel-suggestions"
            autoComplete="off"
            onChange={(event) => setLibelle(event.target.value)}
          />
        </Field>
        <datalist id="frais-manuel-suggestions">
          {LIBELLES_SUGGERES.map((suggestion) => (
            <option key={suggestion} value={suggestion} />
          ))}
        </datalist>

        <Field label="Date" htmlFor="frais-manuel-date" required>
          <DateInput
            id="frais-manuel-date"
            value={date}
            onChange={(event) => setDate(event.target.value)}
          />
        </Field>

        <label className="flex items-center gap-2 text-sm text-simtis-text">
          <input
            type="checkbox"
            className="h-4 w-4 accent-simtis-primary"
            checked={avecTva}
            onChange={(event) => basculerTva(event.target.checked)}
          />
          Le montant contient de la TVA
        </label>

        {avecTva && (
          <div className="grid gap-4 sm:grid-cols-3">
            <Field
              label="Taux de TVA (%)"
              htmlFor="frais-manuel-taux"
              error={tauxValide ? undefined : "Un taux entre 0 et 100."}
            >
              <NumberInput
                id="frais-manuel-taux"
                value={taux}
                inputMode="decimal"
                invalid={!tauxValide}
                onChange={(event) => appliquerTaux(event.target.value)}
              />
            </Field>
            <Field label="Frais HT" htmlFor="frais-manuel-ht">
              <NumberInput
                id="frais-manuel-ht"
                value={ht}
                inputMode="decimal"
                invalid={!!erreurTva}
                onChange={(event) => saisirHt(event.target.value)}
              />
            </Field>
            <Field label="TVA" htmlFor="frais-manuel-tva">
              <NumberInput
                id="frais-manuel-tva"
                value={tva}
                inputMode="decimal"
                invalid={!!erreurTva}
                onChange={(event) => saisirTva(event.target.value)}
              />
            </Field>
          </div>
        )}
        {erreurTva && <p className="text-sm text-simtis-danger-fg">{erreurTva}</p>}

        <div className="overflow-x-auto rounded-[12px] border border-simtis-border">
          <table className="w-full text-sm">
            <caption className="sr-only">Aperçu de l&apos;écriture</caption>
            <thead className="bg-simtis-light text-left text-xs text-simtis-primary-dark">
              <tr>
                <th className="px-3 py-2 font-semibold">Libellé</th>
                <th className="px-3 py-2 text-right font-semibold">Débit</th>
                <th className="px-3 py-2 text-right font-semibold">Crédit</th>
              </tr>
            </thead>
            <tbody>
              {lignes.map((ligne) => (
                <tr key={ligne.type || "frais"} className="border-t border-simtis-border">
                  <td className="px-3 py-1.5">
                    {/* Comme dans le fichier Sage : « TVA AGIOS » pour la ligne de TVA */}
                    {ligne.type === "TVA" && "TVA "}
                    {libelle.trim().toUpperCase() || "—"}
                    {ligne.type && <span className="text-simtis-muted"> · {ligne.type}</span>}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {remboursement ? formatAmount(ligne.montant, "DH") : ""}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {remboursement ? "" : formatAmount(ligne.montant, "DH")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Modal>
  );
}
