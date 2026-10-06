import { describe, expect, it } from "vitest";

import {
  changedFields,
  discrepanciesQuery,
  eventLabel,
  nextStatuses,
  openTotals,
  suggestedType,
  typeProblem,
} from "./discrepancies";

const op = (montant: string) => ({ montant });

describe("discrepanciesQuery", () => {
  it("n'envoie que les filtres renseignés, la page toujours", () => {
    expect(discrepanciesQuery(1, { page: 1 })).toBe("?company_id=1&page=1");
    expect(
      discrepanciesQuery(2, {
        statut: "En cours",
        type: "Montant différent",
        responsableId: 4,
        bankAccountId: 5,
        from: "2025-09-01",
        q: " onee ",
        page: 2,
      }),
    ).toBe(
      "?company_id=2&statut=En+cours&type=Montant+diff%C3%A9rent&responsable_id=4" +
        "&bank_account_id=5&from=2025-09-01&q=onee&page=2",
    );
  });
});

describe("typeProblem", () => {
  it("exige les lignes de chaque type", () => {
    expect(typeProblem("Banque sans écriture", op("10"), null)).toBeNull();
    expect(typeProblem("Banque sans écriture", null, null)).not.toBeNull();
    expect(typeProblem("Banque sans écriture", op("10"), op("-10"))).not.toBeNull();
    expect(typeProblem("Écriture sans banque", null, op("10"))).toBeNull();
    expect(typeProblem("Date différente", op("10"), null)).not.toBeNull();
    expect(typeProblem("Libellé ambigu", op("10"), null)).toBeNull();
    expect(typeProblem("Libellé ambigu", op("10"), op("-10"))).toBeNull();
    expect(typeProblem("Doublon potentiel", op("10"), op("-10"))).not.toBeNull();
    expect(typeProblem("Doublon potentiel", null, op("10"))).toBeNull();
  });

  it("refuse un écart de montant quand les montants s'équilibrent", () => {
    expect(typeProblem("Montant différent", op("12500"), op("-12500"))).not.toBeNull();
    expect(typeProblem("Montant différent", op("12500"), op("-12450"))).toBeNull();
  });
});

describe("suggestedType", () => {
  it("propose le type selon les lignes sélectionnées", () => {
    expect(suggestedType(op("10"), null)).toBe("Banque sans écriture");
    expect(suggestedType(null, op("10"))).toBe("Écriture sans banque");
    expect(suggestedType(op("100"), op("-90"))).toBe("Montant différent");
    expect(suggestedType(op("100"), op("-100"))).toBe("Date différente");
  });
});

describe("nextStatuses", () => {
  it("suit le cycle À traiter → En cours → Traité, Traité peut revenir à En cours", () => {
    expect(nextStatuses("À traiter")).toEqual(["En cours"]);
    expect(nextStatuses("En cours")).toEqual(["Traité"]);
    expect(nextStatuses("Traité")).toEqual(["En cours"]);
    expect(nextStatuses("Clôturé")).toEqual([]);
  });
});

describe("openTotals", () => {
  it("met le dirham en premier, sans additionner les devises", () => {
    expect(openTotals({ USD: "5.00", EUR: "50.00", MAD: "500.00" })).toEqual([
      ["MAD", "500.00"],
      ["EUR", "50.00"],
      ["USD", "5.00"],
    ]);
  });
});

describe("historique", () => {
  it("nomme les événements et les champs changés", () => {
    expect(eventLabel("creation_ecart", { origine: "Automatique" })).toBe(
      "Écart créé automatiquement",
    );
    expect(eventLabel("cloture_ecart", null)).toBe("Écart clôturé");
    expect(
      changedFields(
        { statut: "À traiter", responsable_id: null, commentaire: "a" },
        { statut: "En cours", responsable_id: 3, commentaire: "a" },
      ),
    ).toEqual(["Statut", "Responsable"]);
  });
});
