import { describe, expect, it } from "vitest";

import {
  cleJour,
  compteDuLibelle,
  comptesDeLaBanque,
  etatLignes,
  libelleModifie,
  lignesSaisies,
  selectionTimbres,
  sommeMontants,
  suggestionsLibelles,
  ventilerTva,
} from "@/lib/frais";
import type { CompteFrais, PropositionTimbres } from "@/types/frais";

const jour = (bank_account_id: number, date: string, total: string, famille = "timbres") =>
  ({ famille, bank_account_id, date, total }) as PropositionTimbres;

describe("droits de timbre", () => {
  it("additionne exactement les jours cochés", () => {
    const items = [
      jour(3, "2026-04-23", "222.00"),
      jour(3, "2026-04-24", "0.10"),
      jour(4, "2026-04-23", "0.20"),
    ];
    const selection = new Set([cleJour(items[1]), cleJour(items[2])]);

    expect(selectionTimbres(items, selection)).toEqual({ nb: 2, total: "0.30" });
    expect(selectionTimbres(items, new Set())).toEqual({ nb: 0, total: "0.00" });
  });

  it("distingue les timbres et la COM d'un même jour", () => {
    const timbre = jour(3, "2026-04-23", "222.00");
    const com = jour(3, "2026-04-23", "66.00", "commissions");

    expect(cleJour(timbre)).not.toBe(cleJour(com));
    expect(selectionTimbres([timbre, com], new Set([cleJour(com)]))).toEqual({
      nb: 1,
      total: "66.00",
    });
  });
});

describe("comptabilisation manuelle", () => {
  it("sépare la TVA comme le serveur, et HT + TVA = total", () => {
    expect(ventilerTva("165.00", "10")).toEqual({ ht: "150.00", tva: "15.00" });
    expect(ventilerTva("100.00", "10")).toEqual({ ht: "90.91", tva: "9.09" });
    expect(ventilerTva("0.05", "20")).toEqual({ ht: "0.04", tva: "0.01" });
    expect(ventilerTva("110.00", "7,5")).toEqual({ ht: "102.33", tva: "7.67" });
  });

  it("refuse un taux invalide", () => {
    expect(ventilerTva("165.00", "")).toBeNull();
    expect(ventilerTva("165.00", "0")).toBeNull();
    expect(ventilerTva("165.00", "abc")).toBeNull();
    expect(ventilerTva("165.00", "120")).toBeNull();
  });

  it("additionne exactement des montants signés", () => {
    expect(sommeMontants(["-165.00", "-0.10", "0.05"])).toBe("-165.05");
  });
});

describe("propositions modifiées (19/10/2026)", () => {
  const ligne = (compte: string, montant: string, sens: "Crédit" | "Débit" = "Crédit") => ({
    compte,
    libelle: "COM",
    montant,
    sens,
  });

  it("accepte des lignes qui font exactement le total", () => {
    const etat = etatLignes([ligne("61714000", "50.00"), ligne("34552142", "5.00")], "55.00");

    expect(etat).toEqual({ somme: "55.00", ecart: "0.00", erreur: null });
  });

  it("refuse un écart, un montant invalide ou une ligne sans compte", () => {
    expect(etatLignes([ligne("61714000", "50.00")], "55.00")).toMatchObject({
      ecart: "5.00",
      erreur: "Le total des lignes doit être égal à la somme des opérations.",
    });
    expect(etatLignes([ligne("61714000", "0")], "0.00").erreur).toBe(
      "Chaque montant est positif, au centime près.",
    );
    expect(etatLignes([ligne(" ", "55.00")], "55.00").erreur).toBe(
      "Chaque ligne a un N° compte général.",
    );
    expect(etatLignes([], "55.00").erreur).toBe("L'écriture doit garder au moins une ligne.");
  });

  it("déduit un débit d'un crédit", () => {
    const etat = etatLignes(
      [ligne("61714000", "60.00"), ligne("61473000", "5.00", "Débit")],
      "55.00",
    );

    expect(etat.erreur).toBeNull();
  });

  it("reprend les lignes calculées et renomme la TVA avec l'écriture", () => {
    const tva = {
      type: "tva",
      type_libelle: "",
      libelle: "TVA COM",
      compte: "34552142",
      debit: null,
      credit: "5.00",
    };

    expect(lignesSaisies([tva])).toEqual([
      { compte: "34552142", libelle: "TVA COM", montant: "5.00", sens: "Crédit" },
    ]);
    expect(libelleModifie(tva, "COM", "COM RTGS")).toBe("TVA COM RTGS");
    expect(libelleModifie({ ...tva, libelle: "COM" }, "COM", "COM RTGS")).toBe("COM RTGS");
  });
});

describe("comptes de charge des frais (05/11/2026)", () => {
  const comptes: CompteFrais[] = [
    { numero: "63110004", intitule: "INTERET CMT / OXYGENE", banque: null },
    { numero: "63112000", intitule: "AGIOS BP", banque: "BP" },
    { numero: "63113000", intitule: "AGIOS AWB", banque: "AWB" },
    { numero: "63119400", intitule: "INTERET CRED SPOT", banque: null },
    { numero: "63119700", intitule: "INTERET CMT", banque: null },
    { numero: "63119710", intitule: "INTERETS CMT BP 10.728 KMAD", banque: "BP" },
  ];

  it("réserve un compte à sa banque", () => {
    expect(comptesDeLaBanque(comptes, "AWB").map((c) => c.numero)).toEqual([
      "63110004",
      "63113000",
      "63119400",
      "63119700",
    ]);
  });

  it("donne le compte de l'intitulé le plus long qui commence le libellé, comme le serveur", () => {
    expect(compteDuLibelle("Intérêts cred spot mars", "BP", comptes)).toBe("63119400");
    expect(compteDuLibelle("INTERET CMT / OXYGENE", "BP", comptes)).toBe("63110004");
    expect(compteDuLibelle("INTERETS CMT BP 10.728 KMAD", "BP", comptes)).toBe("63119710");
    expect(compteDuLibelle("INTERETS CMT BP 10.728 KMAD", "AWB", comptes)).toBe("63119700");
    expect(compteDuLibelle("AGIOS BANCAIRES", "AWB", comptes)).toBe("63113000");
    expect(compteDuLibelle("INTERETS DEBITEURS", "BP", comptes)).toBeNull();
    expect(compteDuLibelle("INTERET CMTX", "BP", comptes)).toBeNull();
  });

  it("propose les libellés usuels puis les intitulés, sans doublon", () => {
    const suggestions = suggestionsLibelles(comptes);
    expect(suggestions[0]).toBe("AGIOS");
    expect(suggestions).toContain("INTERET CRED SPOT");
    expect(new Set(suggestions).size).toBe(suggestions.length);
  });
});
