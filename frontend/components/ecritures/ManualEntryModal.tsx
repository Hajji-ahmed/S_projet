"use client";

import { Plus } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { DateInput, Field, Select, TextInput } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { normalizeAmountInput } from "@/lib/accounts";
import { ApiError } from "@/lib/api";
import { businessToday } from "@/lib/balances";
import { journauxDuCompte, montantsSaisis, type Sens } from "@/lib/saisie";
import { ajouterEcriture } from "@/services/accounting";
import type { Account } from "@/types/account";

/**
 * Écriture oubliée par Sage, saisie à la main (24/10/2026). Elle se traite comme une écriture
 * importée ; un export Sage qui la contient avec les mêmes valeurs la reconnaît comme doublon.
 */
export function ManualEntryModal({
  accounts,
  compteInitial,
  onClose,
  onSaved,
}: {
  /** Comptes qui ont un journal Sage. */
  accounts: Account[];
  compteInitial?: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [accountId, setAccountId] = useState(String(compteInitial ?? accounts[0]?.id ?? ""));
  const compte = accounts.find((a) => String(a.id) === accountId);
  const journaux = journauxDuCompte(compte?.journal_sage);
  const [journal, setJournal] = useState(journaux[0] ?? "");
  const [dateEcriture, setDateEcriture] = useState(businessToday());
  const [libelle, setLibelle] = useState("");
  const [piece, setPiece] = useState("");
  const [reference, setReference] = useState("");
  const [echeance, setEcheance] = useState("");
  const [sens, setSens] = useState<Sens>("debit");
  const [montant, setMontant] = useState("");
  const [montantDevise, setMontantDevise] = useState("");
  const [motif, setMotif] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  const enDevise = !!compte && compte.devise !== "MAD";
  const montants = montantsSaisis(sens, montant);
  const devise = enDevise ? normalizeAmountInput(montantDevise) : null;
  const pret =
    !!compte &&
    journaux.includes(journal) &&
    !!dateEcriture &&
    libelle.trim() !== "" &&
    montants !== null &&
    (!enDevise || devise !== null) &&
    motif.trim().length >= 3;

  function choisirCompte(id: string) {
    setAccountId(id);
    const suivant = accounts.find((a) => String(a.id) === id);
    setJournal(journauxDuCompte(suivant?.journal_sage)[0] ?? "");
  }

  async function enregistrer() {
    if (!montants || !compte) return;
    setEnvoi(true);
    setErreur(null);
    try {
      await ajouterEcriture({
        bank_account_id: compte.id,
        journal,
        date_ecriture: dateEcriture,
        libelle: libelle.trim(),
        numero_piece: piece.trim() || null,
        reference: reference.trim() || null,
        echeance: echeance || null,
        ...montants,
        montant_devise: enDevise ? devise : null,
        motif: motif.trim(),
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
      title="Ajouter une écriture"
      onClose={() => !envoi && onClose()}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={envoi}>
            Annuler
          </Button>
          <Button icon={Plus} onClick={enregistrer} disabled={envoi || !pret}>
            {envoi ? "Enregistrement..." : "Ajouter"}
          </Button>
        </>
      }
    >
      <p className="text-sm text-simtis-muted">
        À utiliser pour une écriture oubliée par Sage : elle porte le badge « Saisie manuelle ».
        Débit et crédit au sens de Sage (ligne banque), en DH.
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Field label="Compte bancaire" htmlFor="ec-compte" required>
          <Select
            id="ec-compte"
            value={accountId}
            onChange={(e) => choisirCompte(e.target.value)}
            options={accounts.map((a) => ({
              value: String(a.id),
              label: `${a.bank_code} · ${a.devise} · ${a.libelle}`,
            }))}
          />
        </Field>
        <Field label="Journal Sage" htmlFor="ec-journal" required>
          <Select
            id="ec-journal"
            value={journal}
            onChange={(e) => setJournal(e.target.value)}
            options={journaux.map((j) => ({ value: j, label: j }))}
          />
        </Field>
        <Field label="Date" htmlFor="ec-date" required>
          <DateInput
            id="ec-date"
            value={dateEcriture}
            max={businessToday()}
            onChange={(e) => setDateEcriture(e.target.value)}
          />
        </Field>
        <Field label="N° pièce" htmlFor="ec-piece">
          <TextInput
            id="ec-piece"
            value={piece}
            maxLength={60}
            onChange={(e) => setPiece(e.target.value)}
          />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Libellé" htmlFor="ec-libelle" required>
            <TextInput
              id="ec-libelle"
              value={libelle}
              maxLength={500}
              onChange={(e) => setLibelle(e.target.value)}
            />
          </Field>
        </div>
        <Field label="Sens (Sage)" htmlFor="ec-sens" required>
          <Select
            id="ec-sens"
            value={sens}
            onChange={(e) => setSens(e.target.value as Sens)}
            options={[
              { value: "debit", label: "Débit" },
              { value: "credit", label: "Crédit" },
            ]}
          />
        </Field>
        <Field
          label="Montant (DH)"
          htmlFor="ec-montant"
          required
          error={montant && !montants ? "Montant positif, au centime." : undefined}
        >
          <TextInput
            id="ec-montant"
            value={montant}
            inputMode="decimal"
            placeholder="0,00"
            onChange={(e) => setMontant(e.target.value)}
          />
        </Field>
        {enDevise && (
          <Field label={`Montant en ${compte?.devise}`} htmlFor="ec-devise" required>
            <TextInput
              id="ec-devise"
              value={montantDevise}
              inputMode="decimal"
              placeholder="0,00"
              onChange={(e) => setMontantDevise(e.target.value)}
            />
          </Field>
        )}
        <Field label="Référence" htmlFor="ec-reference">
          <TextInput
            id="ec-reference"
            value={reference}
            maxLength={60}
            onChange={(e) => setReference(e.target.value)}
          />
        </Field>
        <Field label="Échéance" htmlFor="ec-echeance">
          <DateInput
            id="ec-echeance"
            value={echeance}
            onChange={(e) => setEcheance(e.target.value)}
          />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Motif de la saisie" htmlFor="ec-motif" required error={erreur ?? undefined}>
            <TextInput
              id="ec-motif"
              value={motif}
              maxLength={500}
              placeholder="Ex. oubliée dans l'export Sage"
              onChange={(e) => setMotif(e.target.value)}
            />
          </Field>
        </div>
      </div>
    </Modal>
  );
}
