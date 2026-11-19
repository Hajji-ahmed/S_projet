"use client";

import { Save } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { DateInput, Field, Select, TextInput } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { champsModifies } from "@/lib/accounting";
import { normalizeAmountInput } from "@/lib/accounts";
import { ApiError } from "@/lib/api";
import { businessToday, formatDate } from "@/lib/balances";
import { montantsSaisis, type Sens } from "@/lib/saisie";
import { modifierEcriture } from "@/services/accounting";
import type { Ecriture } from "@/types/accounting";

/** « 163571.80 » → « 163571,80 » pour le champ de saisie. */
function enSaisie(montant: string | null | undefined): string {
  return (montant ?? "").replace("-", "").replace(".", ",");
}

/**
 * Correction d'une écriture du grand livre avec un motif (19/11/2026). Une écriture rapprochée ou
 * en proposition ne change que de libellé, de référence ou de N° pièce. L'empreinte ne change
 * pas : la ligne Sage d'origine reste un doublon au prochain import.
 */
export function EditEntryModal({
  ecriture,
  onClose,
  onSaved,
}: {
  ecriture: Ecriture;
  onClose: () => void;
  onSaved: () => void;
}) {
  const auDebit = Number(ecriture.debit) !== 0;
  const [libelle, setLibelle] = useState(ecriture.libelle);
  const [piece, setPiece] = useState(ecriture.numero_piece ?? "");
  const [reference, setReference] = useState(ecriture.reference ?? "");
  const [dateEcriture, setDateEcriture] = useState(ecriture.date_ecriture);
  const [echeance, setEcheance] = useState(ecriture.echeance ?? "");
  const [sens, setSens] = useState<Sens>(auDebit ? "debit" : "credit");
  const [montant, setMontant] = useState(enSaisie(auDebit ? ecriture.debit : ecriture.credit));
  const [montantDevise, setMontantDevise] = useState(enSaisie(ecriture.montant_devise));
  const [motif, setMotif] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  const verrouillee = ecriture.statut !== "Non rapprochée";
  const enDevise = !!ecriture.devise && ecriture.devise !== "MAD";
  const montants = montantsSaisis(sens, montant);
  const devise = enDevise ? normalizeAmountInput(montantDevise) : null;
  const champs = montants
    ? champsModifies(ecriture, {
        libelle,
        reference,
        numero_piece: piece,
        date_ecriture: dateEcriture,
        echeance,
        ...montants,
        montant_devise: devise,
      })
    : {};
  const pret =
    libelle.trim() !== "" &&
    !!dateEcriture &&
    montants !== null &&
    (!enDevise || devise !== null) &&
    Object.keys(champs).length > 0 &&
    motif.trim().length >= 3;

  async function enregistrer() {
    setEnvoi(true);
    setErreur(null);
    try {
      await modifierEcriture(ecriture.id, champs, motif.trim());
      onSaved();
    } catch (error) {
      setErreur(error instanceof ApiError ? error.message : "Enregistrement impossible.");
      setEnvoi(false);
    }
  }

  return (
    <Modal
      open
      title={`Modifier l'écriture du ${formatDate(ecriture.date_ecriture)}`}
      onClose={() => !envoi && onClose()}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={envoi}>
            Annuler
          </Button>
          <Button icon={Save} onClick={enregistrer} disabled={envoi || !pret}>
            {envoi ? "Enregistrement..." : "Enregistrer"}
          </Button>
        </>
      }
    >
      <p className="text-sm text-simtis-muted">
        Journal {ecriture.journal ?? "-"} · compte {ecriture.compte ?? "-"}. Débit et crédit au sens
        de Sage (ligne banque), en DH. La correction est tracée dans l&apos;Historique ; la ligne
        Sage d&apos;origine reste reconnue comme doublon au prochain import.
      </p>
      {verrouillee && (
        <p className="mt-3 rounded-[10px] bg-simtis-warning-bg px-3 py-2 text-sm text-simtis-warning-fg">
          Écriture « {ecriture.statut} » : seuls le libellé, la référence et le N° pièce se
          modifient. Pour changer le montant, le sens ou la date, annulez d&apos;abord son
          rapprochement (ou rejetez sa proposition).
        </p>
      )}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field label="Libellé" htmlFor="me-libelle" required>
            <TextInput
              id="me-libelle"
              value={libelle}
              maxLength={500}
              onChange={(e) => setLibelle(e.target.value)}
            />
          </Field>
        </div>
        <Field label="N° pièce" htmlFor="me-piece">
          <TextInput
            id="me-piece"
            value={piece}
            maxLength={60}
            onChange={(e) => setPiece(e.target.value)}
          />
        </Field>
        <Field label="Référence" htmlFor="me-reference">
          <TextInput
            id="me-reference"
            value={reference}
            maxLength={60}
            onChange={(e) => setReference(e.target.value)}
          />
        </Field>
        <Field label="Date" htmlFor="me-date" required>
          <DateInput
            id="me-date"
            value={dateEcriture}
            max={businessToday()}
            disabled={verrouillee}
            onChange={(e) => setDateEcriture(e.target.value)}
          />
        </Field>
        <Field label="Échéance" htmlFor="me-echeance">
          <DateInput
            id="me-echeance"
            value={echeance}
            disabled={verrouillee}
            onChange={(e) => setEcheance(e.target.value)}
          />
        </Field>
        <Field label="Sens (Sage)" htmlFor="me-sens" required>
          <Select
            id="me-sens"
            value={sens}
            disabled={verrouillee}
            onChange={(e) => setSens(e.target.value as Sens)}
            options={[
              { value: "debit", label: "Débit" },
              { value: "credit", label: "Crédit" },
            ]}
          />
        </Field>
        <Field
          label="Montant (DH)"
          htmlFor="me-montant"
          required
          error={montant && !montants ? "Montant positif, au centime." : undefined}
        >
          <TextInput
            id="me-montant"
            value={montant}
            inputMode="decimal"
            placeholder="0,00"
            disabled={verrouillee}
            onChange={(e) => setMontant(e.target.value)}
          />
        </Field>
        {enDevise && (
          <Field label={`Montant en ${ecriture.devise}`} htmlFor="me-devise" required>
            <TextInput
              id="me-devise"
              value={montantDevise}
              inputMode="decimal"
              placeholder="0,00"
              disabled={verrouillee}
              onChange={(e) => setMontantDevise(e.target.value)}
            />
          </Field>
        )}
        <div className="sm:col-span-2">
          <Field
            label="Motif de la correction"
            htmlFor="me-motif"
            required
            error={erreur ?? undefined}
          >
            <TextInput
              id="me-motif"
              value={motif}
              maxLength={500}
              placeholder="Ex. montant du chèque corrigé dans Sage"
              onChange={(e) => setMotif(e.target.value)}
            />
          </Field>
        </div>
      </div>
    </Modal>
  );
}
