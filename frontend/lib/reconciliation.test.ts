import { describe, expect, it } from "vitest";

import {
  absolute,
  defaultPeriod,
  ecartManuel,
  formatScore,
  fortes,
  rapprochable,
  reconciliationQuery,
  sensBanque,
  toggleStatut,
} from "./reconciliation";
import type { Correspondance } from "@/types/reconciliation";

describe("defaultPeriod", () => {
  it("part du 1er du mois précédent", () => {
    expect(defaultPeriod("2026-10-06")).toEqual({ from: "2026-09-01", to: "2026-10-06" });
    expect(defaultPeriod("2026-01-15")).toEqual({ from: "2025-12-01", to: "2026-01-15" });
  });
});

describe("reconciliationQuery", () => {
  it("n'envoie que les filtres renseignés", () => {
    expect(reconciliationQuery(1, { from: "2026-09-01", to: "" })).toBe(
      "?company_id=1&from=2026-09-01",
    );
    expect(
      reconciliationQuery(2, {
        bankAccountId: 5,
        from: "2026-09-01",
        to: "2026-09-30",
        statut: "À vérifier",
        q: " abc ",
        page: 2,
      }),
    ).toBe(
      "?company_id=2&bank_account_id=5&from=2026-09-01&to=2026-09-30&statut=%C3%80+v%C3%A9rifier&q=abc&page=2",
    );
  });
});

describe("ecartManuel et rapprochable", () => {
  it("un crédit en banque se compense avec un débit Sage du même montant", () => {
    expect(ecartManuel("50000.00", "-50000.00")).toBe("0.00");
    expect(rapprochable("50000.00", "-50000.00")).toBe(true);
  });

  it("refuse un montant différent ou un même sens", () => {
    expect(ecartManuel("12500.00", "-12450.00")).toBe("50.00");
    expect(rapprochable("12500.00", "-12450.00")).toBe(false);
    expect(rapprochable("100.00", "100.00")).toBe(false);
    expect(rapprochable("0.00", "0.00")).toBe(false);
  });

  it("reste exact au centime", () => {
    expect(ecartManuel("0.10", "-0.30")).toBe("-0.20");
  });
});

describe("fortes", () => {
  it("ne garde que les propositions fortes en attente", () => {
    const rows = [
      { id: 1, statut: "Proposée", forte: true },
      { id: 2, statut: "Proposée", forte: false },
      { id: 3, statut: "Validée", forte: true },
    ] as Correspondance[];

    expect(fortes(rows)).toEqual([1]);
  });
});

describe("formats", () => {
  it("affiche le score sans zéros inutiles", () => {
    expect(formatScore("92.50")).toBe("92,5");
    expect(formatScore("100.00")).toBe("100");
    expect(formatScore(null)).toBe("-");
  });

  it("donne le montant absolu et le sens bancaire", () => {
    expect(absolute("-80.00")).toBe("80.00");
    expect(sensBanque("-80.00")).toBe("Débit");
    expect(sensBanque("80.00")).toBe("Crédit");
  });
});

describe("toggleStatut", () => {
  it("filtre sur le compteur cliqué, et retire le filtre au second clic", () => {
    expect(toggleStatut("", "À vérifier")).toBe("À vérifier");
    expect(toggleStatut("Rapprochée", "À vérifier")).toBe("À vérifier");
    expect(toggleStatut("À vérifier", "À vérifier")).toBe("");
  });
});
