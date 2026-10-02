import { describe, expect, it } from "vitest";

import type { AnalysedLine } from "@/types/statement";

import {
  amountToInput,
  checkDraft,
  draftToLigne,
  lineMotifs,
  sameDraft,
  summariseDrafts,
  type LineDraft,
} from "./statementLines";

const TODAY = "2026-10-02";
const base: LineDraft = {
  numero: 2,
  date_operation: "2026-09-24",
  date_valeur: "",
  libelle: "VIR CLIENT",
  reference: "",
  debit: "",
  credit: "45 000",
  solde: "165 000",
  pointage_type_id: null,
  lettrage_escompte: "",
  commentaire: "",
};

describe("amountToInput", () => {
  it("écrit le montant à la française sans calcul flottant", () => {
    expect(amountToInput("12500.50")).toBe("12 500,50");
    expect(amountToInput("-1037349.50")).toBe("-1 037 349,50");
    expect(amountToInput("10.00")).toBe("10");
    expect(amountToInput("0.05")).toBe("0,05");
    expect(amountToInput(null)).toBe("");
  });
});

describe("checkDraft", () => {
  it("accepte une ligne complète", () => {
    expect(checkDraft(base, TODAY)).toEqual([]);
  });

  it("applique les règles du serveur", () => {
    expect(checkDraft({ ...base, date_operation: "" }, TODAY)).toContain(
      "Date d'opération manquante.",
    );
    expect(checkDraft({ ...base, date_operation: "2026-10-03" }, TODAY)).toContain(
      "Date d'opération dans le futur.",
    );
    expect(checkDraft({ ...base, libelle: "  " }, TODAY)).toContain("Libellé manquant.");
    expect(checkDraft({ ...base, credit: "" }, TODAY)).toContain("Ni débit ni crédit.");
    expect(checkDraft({ ...base, debit: "5" }, TODAY)).toContain(
      "Débit et crédit renseignés sur la même ligne.",
    );
    expect(checkDraft({ ...base, credit: "dix" }, TODAY)).toContain(
      "Crédit : montant illisible (ex. 12 500,50).",
    );
    expect(checkDraft({ ...base, lettrage_escompte: "x".repeat(121) }, TODAY)).toContain(
      "Lettrage / Escompte : 120 caractères au plus.",
    );
  });

  it("lit un débit négatif comme un débit, comme le serveur", () => {
    expect(checkDraft({ ...base, credit: "", debit: "-150" }, TODAY)).toEqual([]);
    expect(draftToLigne({ ...base, credit: "", debit: "-150" }).debit).toBe("150");
  });

  it("signale un format que le navigateur ne sait pas lire, au lieu de l'envoyer", () => {
    // « 1.250,50 » (point des milliers) : signalé, jamais envoyé sous une autre valeur
    expect(checkDraft({ ...base, credit: "1.250,50" }, TODAY)).toContain(
      "Crédit : montant illisible (ex. 12 500,50).",
    );
  });
});

describe("draftToLigne", () => {
  it("normalise les montants et vide les textes blancs", () => {
    expect(draftToLigne(base)).toEqual({
      numero: 2,
      date_operation: "2026-09-24",
      date_valeur: null,
      libelle: "VIR CLIENT",
      reference: null,
      debit: null,
      credit: "45000",
      solde: "165000",
      pointage_type_id: null,
      lettrage_escompte: null,
      commentaire: null,
    });
  });
});

describe("sameDraft", () => {
  it("compare toutes les valeurs", () => {
    expect(sameDraft(base, { ...base })).toBe(true);
    expect(sameDraft(base, { ...base, commentaire: "x" })).toBe(false);
  });
});

describe("lineMotifs", () => {
  const fileLine = (statut: "Valide" | "Erreur", motifs: string[]): AnalysedLine => ({
    numero: 2,
    statut,
    motifs,
    date_operation: "2026-09-24",
    date_valeur: null,
    libelle: "VIR CLIENT",
    reference: null,
    debit: "0.00",
    credit: "45000.00",
    montant: "45000.00",
    solde: null,
    pointage: null,
    pointage_type_id: null,
    pointage_libelle: null,
    pointage_auto: false,
    lettrage_escompte: null,
    commentaire: null,
    hash_ligne: null,
    doublon_de: null,
  });

  it("garde les motifs du serveur tant qu'une ligne en erreur n'est pas corrigée", () => {
    const line = fileLine("Erreur", ["Solde : Montant illisible : « abc »."]);

    expect(lineMotifs(line, base, base, TODAY)).toEqual(["Solde : Montant illisible : « abc »."]);
    expect(lineMotifs(line, { ...base, solde: "1 010" }, base, TODAY)).toEqual([]);
  });

  it("refuse toujours une ligne d'une autre banque, même corrigée", () => {
    const motif = "Banque « BMCE » différente de celle du compte (CIH).";
    const line = fileLine("Erreur", [motif]);

    expect(lineMotifs(line, { ...base, libelle: "AUTRE" }, base, TODAY)).toEqual([motif]);
  });

  it("ne garde rien pour une ligne valide", () => {
    expect(lineMotifs(fileLine("Valide", []), base, base, TODAY)).toEqual([]);
  });
});

describe("summariseDrafts", () => {
  const lines: LineDraft[] = [
    base,
    {
      ...base,
      numero: 3,
      date_operation: "2026-09-25",
      credit: "",
      debit: "250,50",
      solde: "164 749,50",
    },
  ];

  it("totalise en centimes exacts et vérifie la cohérence avec le solde initial du fichier", () => {
    expect(summariseDrafts(lines, "120000.00", null)).toEqual({
      count: 2,
      totalDebit: "250.50",
      totalCredit: "45000.00",
      periodeDebut: "2026-09-24",
      periodeFin: "2026-09-25",
      ouverture: "120000.00",
      cloture: "164749.50",
      coherent: true,
    });
  });

  it("déduit l'ouverture de la première ligne sans solde initial", () => {
    expect(summariseDrafts(lines, null, null).ouverture).toBe("120000.00");
  });

  it("signale un solde initial incohérent", () => {
    expect(summariseDrafts(lines, "100000.00", null).coherent).toBe(false);
  });

  it("ne conclut rien sans soldes", () => {
    const sansSolde = lines.map((line) => ({ ...line, solde: "" }));
    expect(summariseDrafts(sansSolde, null, null).coherent).toBeNull();
  });
});
