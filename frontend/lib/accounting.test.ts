import { describe, expect, it } from "vitest";

import {
  OPERATION_POSSIBLE,
  accountingForm,
  champsModifies,
  entriesQuery,
  pageCount,
  statutEcritures,
} from "./accounting";

describe("entriesQuery", () => {
  it("n'envoie que les filtres renseignés, la page toujours", () => {
    expect(entriesQuery(1, { page: 1 })).toBe("?company_id=1&page=1");
    expect(
      entriesQuery(2, {
        bankAccountId: 5,
        from: "2025-09-01",
        to: "",
        statut: "Rapprochée",
        q: " atlas ",
        page: 3,
      }),
    ).toBe("?company_id=2&bank_account_id=5&from=2025-09-01&statut=Rapproch%C3%A9e&q=atlas&page=3");
  });
});

describe("entriesQuery tri", () => {
  it("envoie le tri par montant seulement quand il est choisi", () => {
    expect(entriesQuery(1, { tri: "montant_desc", page: 1 })).toBe(
      "?company_id=1&tri=montant_desc&page=1",
    );
    expect(entriesQuery(1, { tri: "", page: 1 })).toBe("?company_id=1&page=1");
  });
});

describe("pageCount", () => {
  it("compte les pages de 50, au moins une", () => {
    expect(pageCount(0, 50)).toBe(1);
    expect(pageCount(50, 50)).toBe(1);
    expect(pageCount(51, 50)).toBe(2);
  });
});

describe("accountingForm", () => {
  it("joint le fichier, la société et les options de confirmation", () => {
    const file = new File(["x"], "sage.xlsx");

    const form = accountingForm(file, 3, {
      mapping: { date_ecriture: 0, tiers: null },
      garderDoublons: [7, 4],
      ecarterErreurs: true,
    });

    expect((form.get("fichier") as File).name).toBe("sage.xlsx");
    expect(form.get("company_id")).toBe("3");
    expect(form.get("mapping")).toBe('{"date_ecriture":0}');
    expect(form.get("garder_doublons")).toBe("[4,7]");
    expect(form.get("ecarter_erreurs")).toBe("true");
  });

  it("n'envoie rien de plus pour une simple analyse", () => {
    const form = accountingForm(new File(["x"], "sage.xlsx"), 3);

    expect([...form.keys()]).toEqual(["fichier", "company_id"]);
  });
});

describe("accountingForm, lignes cochées", () => {
  it("envoie les numéros des lignes cochées, triés", () => {
    const file = new File(["x"], "sage.xlsx");
    const form = accountingForm(file, 3, { lignesChoisies: [9, 2] });

    expect(form.get("lignes_choisies")).toBe("[2,9]");
    expect(form.get("garder_doublons")).toBeNull();
    expect(form.get("ecarter_erreurs")).toBeNull();
  });
});

describe("statutEcritures (19/10/2026)", () => {
  it("« Non rapprochée » ne garde que les écritures sans opération possible", () => {
    expect(statutEcritures("Non rapprochée")).toEqual({
      statut: "Non rapprochée",
      operationPossible: false,
    });
    expect(statutEcritures(OPERATION_POSSIBLE)).toEqual({
      statut: "Non rapprochée",
      operationPossible: true,
    });
    expect(statutEcritures("Rapprochée")).toEqual({ statut: "Rapprochée" });
    expect(statutEcritures("")).toEqual({ statut: undefined });
  });

  it("envoie operation_possible à l'API", () => {
    expect(entriesQuery(1, { page: 1, operationPossible: false })).toBe(
      "?company_id=1&operation_possible=false&page=1",
    );
  });
});

describe("accountingForm, écritures absentes à supprimer (05/11/2026)", () => {
  it("envoie leurs ids triés, et rien quand la liste est vide", () => {
    const file = new File(["x"], "sage.xlsx");
    expect(
      accountingForm(file, 3, { ecrituresSupprimees: [8, 4] }).get("ecritures_supprimees"),
    ).toBe("[4,8]");
    expect(
      accountingForm(file, 3, { ecrituresSupprimees: [] }).get("ecritures_supprimees"),
    ).toBeNull();
  });
});

describe("champsModifies (19/11/2026)", () => {
  const ecriture = {
    libelle: "CHQ 0163571",
    reference: null,
    numero_piece: "CHQ1",
    date_ecriture: "2026-10-26",
    echeance: null,
    debit: "0.00",
    credit: "163571.80",
    montant_devise: null,
  };
  const saisie = {
    libelle: "CHQ 0163571",
    reference: "",
    numero_piece: "CHQ1",
    date_ecriture: "2026-10-26",
    echeance: "",
    debit: null,
    credit: "163571.80",
    montant_devise: null,
  };

  it("n'envoie rien quand rien ne change", () => {
    expect(champsModifies(ecriture, saisie)).toEqual({});
    expect(champsModifies(ecriture, { ...saisie, credit: "163571.8" })).toEqual({});
  });

  it("envoie débit et crédit ensemble quand le montant ou le sens change", () => {
    expect(champsModifies(ecriture, { ...saisie, credit: "163571.20" })).toEqual({
      debit: null,
      credit: "163571.20",
    });
    expect(champsModifies(ecriture, { ...saisie, debit: "163571.80", credit: null })).toEqual({
      debit: "163571.80",
      credit: null,
    });
  });

  it("envoie les textes nettoyés, et null pour un champ vidé", () => {
    expect(
      champsModifies(ecriture, { ...saisie, libelle: " CHQ 80460892 ", numero_piece: " " }),
    ).toEqual({ libelle: "CHQ 80460892", numero_piece: null });
    expect(champsModifies({ ...ecriture, echeance: "2026-11-30" }, saisie)).toEqual({
      echeance: null,
    });
  });

  it("joint le montant en devise à un changement de montant", () => {
    const usd = { ...ecriture, montant_devise: "16357.18" };
    expect(
      champsModifies(usd, { ...saisie, credit: "163571.20", montant_devise: "16357.18" }),
    ).toEqual({ debit: null, credit: "163571.20", montant_devise: "16357.18" });
    expect(champsModifies(usd, { ...saisie, montant_devise: "16357.18" })).toEqual({});
  });
});
