"use client";

import { Check, Plus, RotateCcw, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { DateInput, Field, NumberInput, Select, TextInput } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { normalizeAmountInput } from "@/lib/accounts";
import { businessToday, formatDate } from "@/lib/balances";
import { formatAmount } from "@/lib/format";
import { etatLignes, lignesSaisies } from "@/lib/frais";
import { fromCents, toCents } from "@/lib/statementLines";
import type { LigneSaisie, ModificationFrais, PropositionTimbres } from "@/types/frais";

type Saisie = { compte: string; libelle: string; montant: string; sens: LigneSaisie["sens"] };

/** « 150,5 » → « 150.50 » ; un texte invalide est gardé tel quel (refusé par `etatLignes`). */
function exact(saisie: string): string {
  const valeur = normalizeAmountInput(saisie);
  return valeur === null ? saisie : fromCents(toCents(valeur));
}

const SENS = [
  { value: "Crédit", label: "Crédit" },
  { value: "Débit", label: "Débit" },
];

/**
 * Modifier une proposition de frais avant sa validation (19/10/2026) : libellé, date et, au
 * besoin, ses lignes (compte, libellé, montant, sens ; une ligne s'ajoute ou se retire). Le total
 * des lignes reste la somme des opérations. Rien n'est enregistré ici : la modification part avec
 * « Valider la sélection », et le serveur la contrôle de nouveau.
 */
export function EditFraisModal({
  item,
  modification,
  onClose,
  onSave,
}: {
  item: PropositionTimbres;
  modification: ModificationFrais | undefined;
  onClose: () => void;
  onSave: (modification: ModificationFrais | undefined) => void;
}) {
  const [libelle, setLibelle] = useState(modification?.libelle ?? item.libelle);
  const [date, setDate] = useState(modification?.date_ecriture ?? item.date);
  const [lignes, setLignes] = useState<Saisie[]>(() =>
    (modification?.lignes ?? lignesSaisies(item.lignes)).map((ligne) => ({
      ...ligne,
      montant: ligne.montant.replace(".", ","),
    })),
  );
  const [lignesModifiees, setLignesModifiees] = useState(modification?.lignes !== undefined);

  const propres: LigneSaisie[] = lignes.map((ligne) => ({
    ...ligne,
    montant: exact(ligne.montant),
  }));
  const etat = etatLignes(propres, item.total);
  const aujourdhui = businessToday();
  const erreurDate =
    date < item.date || date > aujourdhui
      ? `La date doit être comprise entre le ${formatDate(item.date)} et aujourd'hui.`
      : null;
  const erreurLibelle =
    libelle.trim() === ""
      ? "Indiquez le libellé de l'écriture."
      : libelle.trim().length > 60
        ? "60 caractères au plus."
        : null;
  const erreur = erreurLibelle ?? erreurDate ?? (lignesModifiees ? etat.erreur : null);

  function changerLigne(index: number, champ: keyof Saisie, valeur: string) {
    setLignesModifiees(true);
    setLignes((liste) =>
      liste.map((ligne, i) => (i === index ? { ...ligne, [champ]: valeur } : ligne)),
    );
  }

  function enregistrer() {
    const texte = libelle.trim().toUpperCase().replace(/\s+/g, " ");
    const modif: ModificationFrais = {
      ...(texte !== item.libelle ? { libelle: texte } : {}),
      ...(date !== item.date ? { date_ecriture: date } : {}),
      ...(lignesModifiees ? { lignes: propres } : {}),
    };
    onSave(Object.keys(modif).length > 0 ? modif : undefined);
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Modifier l'écriture proposée"
      footer={
        <>
          <Button
            variant="ghost"
            icon={RotateCcw}
            onClick={() => onSave(undefined)}
            disabled={!modification}
          >
            Revenir au calcul de SIMTIS
          </Button>
          <Button variant="secondary" onClick={onClose}>
            Annuler
          </Button>
          <Button icon={Check} disabled={erreur !== null} onClick={enregistrer}>
            Enregistrer
          </Button>
        </>
      }
    >
      <p className="mb-4 text-sm text-simtis-muted">
        {item.bank_code} · {formatDate(item.date)} · {item.nb_operations} opération
        {item.nb_operations > 1 ? "s" : ""} ·{" "}
        <span className="font-medium text-simtis-text tabular-nums">
          {formatAmount(item.total, "DH")}
        </span>
        . La modification sera appliquée à la validation.
      </p>

      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Libellé de l'écriture"
            htmlFor="frais-edit-libelle"
            required
            error={erreurLibelle ?? undefined}
          >
            <TextInput
              id="frais-edit-libelle"
              value={libelle}
              maxLength={60}
              invalid={!!erreurLibelle}
              onChange={(event) => setLibelle(event.target.value)}
            />
          </Field>
          <Field label="Date" htmlFor="frais-edit-date" required error={erreurDate ?? undefined}>
            <DateInput
              id="frais-edit-date"
              value={date}
              invalid={!!erreurDate}
              onChange={(event) => setDate(event.target.value)}
            />
          </Field>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-simtis-text">Lignes de l&apos;écriture</h3>
          <Button
            variant="secondary"
            icon={Plus}
            onClick={() => {
              setLignesModifiees(true);
              setLignes((liste) => [
                ...liste,
                { compte: "", libelle: "", montant: "", sens: "Crédit" },
              ]);
            }}
          >
            Ajouter une ligne
          </Button>
        </div>
        {!lignesModifiees && (
          <p className="text-xs text-simtis-muted">
            Lignes calculées par SIMTIS. Modifiez-en une, ou ajoutez-en, pour les saisir vous-même.
          </p>
        )}
        <div className="overflow-x-auto rounded-[12px] border border-simtis-border">
          <table className="w-full text-sm">
            <thead className="bg-simtis-light text-left text-xs text-simtis-primary-dark">
              <tr>
                <th className="px-2 py-2 font-semibold">N° compte général</th>
                <th className="px-2 py-2 font-semibold">Libellé</th>
                <th className="px-2 py-2 text-right font-semibold">Montant</th>
                <th className="px-2 py-2 font-semibold">Sens</th>
                <th className="px-2 py-2">
                  <span className="sr-only">Retirer</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {lignes.map((ligne, index) => (
                <tr key={index} className="border-t border-simtis-border">
                  <td className="px-2 py-1.5">
                    <TextInput
                      aria-label={`Compte de la ligne ${index + 1}`}
                      value={ligne.compte}
                      maxLength={20}
                      className="min-w-[110px]"
                      onChange={(event) => changerLigne(index, "compte", event.target.value)}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <TextInput
                      aria-label={`Libellé de la ligne ${index + 1}`}
                      value={ligne.libelle}
                      maxLength={60}
                      className="min-w-[160px]"
                      onChange={(event) => changerLigne(index, "libelle", event.target.value)}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <NumberInput
                      aria-label={`Montant de la ligne ${index + 1}`}
                      value={ligne.montant}
                      inputMode="decimal"
                      className="min-w-[110px] text-right"
                      onChange={(event) => changerLigne(index, "montant", event.target.value)}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <Select
                      aria-label={`Sens de la ligne ${index + 1}`}
                      options={SENS}
                      value={ligne.sens}
                      onChange={(event) => changerLigne(index, "sens", event.target.value)}
                    />
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <Button
                      variant="ghost"
                      icon={Trash2}
                      aria-label={`Retirer la ligne ${index + 1}`}
                      disabled={lignes.length <= 1}
                      onClick={() => {
                        setLignesModifiees(true);
                        setLignes((liste) => liste.filter((_, i) => i !== index));
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-sm tabular-nums">
          Lignes {formatAmount(etat.somme, "DH")} · opérations {formatAmount(item.total, "DH")} ·
          écart{" "}
          <strong
            className={etat.ecart === "0.00" ? "text-simtis-success-fg" : "text-simtis-danger-fg"}
          >
            {formatAmount(etat.ecart, "DH")}
          </strong>
        </p>
        {erreur && (
          <p role="alert" className="text-sm text-simtis-danger-fg">
            {erreur}
          </p>
        )}
      </div>
    </Modal>
  );
}
