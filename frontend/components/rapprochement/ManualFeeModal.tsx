"use client";

import { Check } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { DateInput, Field, NumberInput, Select, TextInput } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { normalizeAmountInput } from "@/lib/accounts";
import { ApiError } from "@/lib/api";
import { formatAmount } from "@/lib/format";
import {
  AUTRE_COMPTE,
  comptesDeLaBanque,
  compteParDefaut,
  compteValide,
  sommeMontants,
  suggestionsLibelles,
  tvaSurPartie,
  ventilerTva,
} from "@/lib/frais";
import { fromCents, toCents } from "@/lib/statementLines";
import { comptabiliserManuellement, listComptesFrais } from "@/services/frais";
import type { AutreFrais, CompteFrais } from "@/types/frais";

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
 * l'ouverture : son état repart de zéro. Le compte de charge suit le libellé (« INTERET CRED SPOT »
 * → 63119400) ou se choisit dans la liste des comptes de frais (05/11/2026), ou se saisit (« Autre », 07/11/2026).
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

  const banque = operations[0]?.bank_code ?? "";
  const [libelle, setLibelle] = useState("");
  const [comptes, setComptes] = useState<CompteFrais[]>([]);
  // null : le compte suit le libellé ; AUTRE_COMPTE : numéro saisi dans `compteLibre` (07/11/2026)
  const [compteChoisi, setCompteChoisi] = useState<string | null>(null);
  const [compteLibre, setCompteLibre] = useState("");
  const [date, setDate] = useState(derniereDate);
  const [avecTva, setAvecTva] = useState(false);
  const [taux, setTaux] = useState(TAUX_PAR_DEFAUT);
  const [ht, setHt] = useState("");
  const [tva, setTva] = useState("");
  // Partie avec TVA (12/11/2026) : vide, la TVA porte sur tout le montant
  const [partie, setPartie] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let actif = true;
    listComptesFrais()
      .then((liste) => {
        if (actif) setComptes(liste);
      })
      // Sans la liste, le serveur choisit le compte d'après le libellé
      .catch(() => undefined);
    return () => {
      actif = false;
    };
  }, []);

  const comptesProposes = comptesDeLaBanque(comptes, banque);
  // Le compte réellement utilisé est toujours affiché (07/11/2026)
  const autre = compteChoisi === AUTRE_COMPTE;
  const selection = compteChoisi ?? compteParDefaut(libelle, banque, comptes);
  const compte = autre ? compteLibre.trim() : selection;

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

  // TVA sur une partie seulement : calculée, Frais HT et TVA ne se saisissent plus
  const partiel = avecTva && partie.trim() !== "" ? tvaSurPartie(total, partie, taux) : null;
  const htExact = partiel ? partiel.ht : montant(ht);
  const tvaExacte = partiel ? partiel.tva : montant(tva);
  const erreurTva = !avecTva
    ? null
    : partiel
      ? partiel.erreur
      : htExact === null || tvaExacte === null
        ? "Saisissez le frais hors taxe et la TVA (2 décimales au plus)."
        : toCents(htExact) <= BigInt(0) || toCents(tvaExacte) <= BigInt(0)
          ? "Le frais hors taxe et la TVA doivent être positifs."
          : toCents(htExact) + toCents(tvaExacte) !== toCents(total)
            ? `Frais HT + TVA doit faire exactement ${formatAmount(total, "DH")}.`
            : null;
  const tauxValide = ventilerTva(total, taux) !== null;
  const pret =
    libelle.trim() !== "" &&
    date !== "" &&
    !erreurTva &&
    (!avecTva || tauxValide) &&
    (!autre || compteValide(compteLibre)) &&
    !busy;

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
        ...(compte ? { compte } : {}),
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
            maxLength={50}
            list="frais-manuel-suggestions"
            autoComplete="off"
            onChange={(event) => setLibelle(event.target.value)}
          />
        </Field>
        <datalist id="frais-manuel-suggestions">
          {suggestionsLibelles(comptesProposes).map((suggestion) => (
            <option key={suggestion} value={suggestion} />
          ))}
        </datalist>

        <Field
          label="Compte de charge"
          htmlFor="frais-manuel-compte"
          hint="Suit le libellé, modifiable ; la TVA va toujours sur 34552142."
        >
          <Select
            id="frais-manuel-compte"
            value={selection}
            placeholder={selection === "" ? "Choisir un compte" : undefined}
            options={[
              ...comptesProposes.map((item) => ({
                value: item.numero,
                label: `${item.numero} · ${item.intitule}`,
              })),
              { value: AUTRE_COMPTE, label: "Autre…" },
            ]}
            onChange={(event) => setCompteChoisi(event.target.value || null)}
          />
        </Field>
        {autre && (
          <Field
            label="N° de compte"
            htmlFor="frais-manuel-compte-libre"
            required
            error={
              compteLibre.trim() !== "" && !compteValide(compteLibre)
                ? "De 4 à 20 chiffres, sans espace."
                : undefined
            }
          >
            <TextInput
              id="frais-manuel-compte-libre"
              inputMode="numeric"
              value={compteLibre}
              placeholder="Ex. 44110000"
              invalid={compteLibre.trim() !== "" && !compteValide(compteLibre)}
              onChange={(event) => setCompteLibre(event.target.value)}
            />
          </Field>
        )}

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
          <div className="grid gap-4 sm:grid-cols-2">
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
            <Field
              label="Partie avec TVA (HT)"
              htmlFor="frais-manuel-partie"
              hint="Si la TVA ne porte que sur une partie ; vide : sur tout le montant."
            >
              <NumberInput
                id="frais-manuel-partie"
                value={partie}
                inputMode="decimal"
                placeholder="Tout le montant"
                invalid={!!partiel?.erreur}
                onChange={(event) => setPartie(event.target.value)}
              />
            </Field>
            <Field label="Frais HT" htmlFor="frais-manuel-ht">
              <NumberInput
                id="frais-manuel-ht"
                value={partiel ? partiel.ht.replace(".", ",") : ht}
                inputMode="decimal"
                disabled={!!partiel}
                invalid={!!erreurTva}
                onChange={(event) => saisirHt(event.target.value)}
              />
            </Field>
            <Field label="TVA" htmlFor="frais-manuel-tva">
              <NumberInput
                id="frais-manuel-tva"
                value={partiel ? partiel.tva.replace(".", ",") : tva}
                inputMode="decimal"
                disabled={!!partiel}
                invalid={!!erreurTva}
                onChange={(event) => saisirTva(event.target.value)}
              />
            </Field>
          </div>
        )}
        {partiel && !partiel.erreur && (
          <p className="text-sm text-simtis-muted tabular-nums">
            Partie avec TVA {formatAmount(normalizeAmountInput(partie) ?? "0", "DH")} · TVA{" "}
            {formatAmount(partiel.tva, "DH")} · Sans TVA {formatAmount(partiel.sansTva, "DH")}
          </p>
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
