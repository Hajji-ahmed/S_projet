import { describe, expect, it } from "vitest";

import { accountingForm, entriesQuery, pageCount } from "./accounting";

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
