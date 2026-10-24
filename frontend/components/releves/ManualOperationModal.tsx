"use client";

import { Plus } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { DateInput, Field, Select, TextInput } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { ApiError } from "@/lib/api";
import { businessToday } from "@/lib/balances";
import { montantsSaisis, type Sens } from "@/lib/saisie";
import { ajouterOperation } from "@/services/statements";
import type { PointageType } from "@/types/statement";

/**
 * Opération absente du relevé, saisie à la main (24/10/2026). Elle s'ajoute au relevé du compte
 * comme une ligne importée ; son solde suit l'opération qui la précède.
 */
export function ManualOperationModal({
  accountId,
  compte,
  pointages,
  onClose,
  onSaved,
}: {
  accountId: number;
  compte: string;
  pointages: PointageType[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [dateOperation, setDateOperation] = useState(businessToday());
  const [dateValeur, setDateValeur] = useState("");
  const [libelle, setLibelle] = useState("");
  const [reference, setReference] = useState("");
  const [sens, setSens] = useState<Sens>("debit");
  const [montant, setMontant] = useState("");
  const [pointage, setPointage] = useState("");
  const [commentaire, setCommentaire] = useState("");
  const [motif, setMotif] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  const montants = montantsSaisis(sens, montant);
  const pret =
    !!dateOperation && libelle.trim() !== "" && montants !== null && motif.trim().length >= 3;

  async function enregistrer() {
    if (!montants) return;
    setEnvoi(true);
    setErreur(null);
    try {
      await ajouterOperation(accountId, {
        date_operation: dateOperation,
        date_valeur: dateValeur || null,
        libelle: libelle.trim(),
        reference: reference.trim() || null,
        ...montants,
        pointage_type_id: pointage ? Number(pointage) : null,
        commentaire: commentaire.trim() || null,
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
      title="Ajouter une opération"
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
        Compte <span className="font-medium text-simtis-text">{compte}</span>. L&apos;opération
        s&apos;ajoute au relevé comme une ligne importée, avec le badge « Saisie manuelle ». Si le
        fichier de la banque la contient plus tard avec exactement les mêmes valeurs, elle y sera
        reconnue comme doublon.
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Field label="Date d'opération" htmlFor="op-date" required>
          <DateInput
            id="op-date"
            value={dateOperation}
            max={businessToday()}
            onChange={(e) => setDateOperation(e.target.value)}
          />
        </Field>
        <Field label="Date de valeur" htmlFor="op-valeur">
          <DateInput
            id="op-valeur"
            value={dateValeur}
            onChange={(e) => setDateValeur(e.target.value)}
          />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Libellé" htmlFor="op-libelle" required>
            <TextInput
              id="op-libelle"
              value={libelle}
              maxLength={500}
              onChange={(e) => setLibelle(e.target.value)}
            />
          </Field>
        </div>
        <Field label="Sens" htmlFor="op-sens" required>
          <Select
            id="op-sens"
            value={sens}
            onChange={(e) => setSens(e.target.value as Sens)}
            options={[
              { value: "debit", label: "Débit (sortie d'argent)" },
              { value: "credit", label: "Crédit (entrée d'argent)" },
            ]}
          />
        </Field>
        <Field
          label="Montant"
          htmlFor="op-montant"
          required
          error={montant && !montants ? "Montant positif, au centime." : undefined}
        >
          <TextInput
            id="op-montant"
            value={montant}
            inputMode="decimal"
            placeholder="0,00"
            onChange={(e) => setMontant(e.target.value)}
          />
        </Field>
        <Field label="Référence" htmlFor="op-reference">
          <TextInput
            id="op-reference"
            value={reference}
            maxLength={60}
            onChange={(e) => setReference(e.target.value)}
          />
        </Field>
        <Field label="Pointage" htmlFor="op-pointage">
          <Select
            id="op-pointage"
            value={pointage}
            onChange={(e) => setPointage(e.target.value)}
            placeholder="À choisir"
            options={pointages.map((p) => ({ value: String(p.id), label: p.libelle }))}
          />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Commentaire" htmlFor="op-commentaire">
            <TextInput
              id="op-commentaire"
              value={commentaire}
              maxLength={1000}
              onChange={(e) => setCommentaire(e.target.value)}
            />
          </Field>
        </div>
        <div className="sm:col-span-2">
          <Field label="Motif de la saisie" htmlFor="op-motif" required error={erreur ?? undefined}>
            <TextInput
              id="op-motif"
              value={motif}
              maxLength={500}
              placeholder="Ex. absente du relevé de la banque"
              onChange={(e) => setMotif(e.target.value)}
            />
          </Field>
        </div>
      </div>
    </Modal>
  );
}
