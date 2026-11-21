import { describe, expect, it } from "vitest";

import { difference, ecartApresImport, etatEcart, sensEcart, veille } from "./sageEcart";

describe("etatEcart", () => {
  it("distingue aucun écart, un écart et rien à comparer", () => {
    expect(etatEcart("0.00")).toBe("aucun");
    expect(etatEcart("-0.00")).toBe("aucun");
    expect(etatEcart("-30.00")).toBe("ecart");
    expect(etatEcart("0.01")).toBe("ecart");
    expect(etatEcart(null)).toBe("inconnu");
    expect(etatEcart(undefined)).toBe("inconnu");
  });
});

describe("ecartApresImport", () => {
  it("retranche le solde après import du solde Sage, au centime", () => {
    expect(ecartApresImport("-1234567.89", "-1234567.89")).toBe("0.00");
    expect(ecartApresImport("1150.00", "1180.00")).toBe("-30.00");
    expect(ecartApresImport("0.10", "0.20")).toBe("-0.10");
  });

  it("ne compare rien sans les deux soldes", () => {
    expect(ecartApresImport(null, "10.00")).toBeNull();
    expect(ecartApresImport("10.00", null)).toBeNull();
  });
});

describe("sensEcart", () => {
  it("dit de quel côté penche l'écart", () => {
    expect(sensEcart("30.00")).toBe("Sage plus débiteur que SIMTIS");
    expect(sensEcart("-30.00")).toBe("Sage plus créditeur que SIMTIS");
    expect(sensEcart("0.00")).toBeNull();
    expect(sensEcart(null)).toBeNull();
  });
});

describe("difference", () => {
  it("calcule au centime, signe compris", () => {
    expect(difference("1000.00", "1000.00")).toBe("0.00");
    expect(difference("0.00", "-20.00")).toBe("20.00");
    expect(difference("-7654321.11", "-7654321.10")).toBe("-0.01");
  });
});

describe("veille", () => {
  it("donne la veille, même en changeant de mois ou d'année", () => {
    expect(veille("2025-01-01")).toBe("2024-12-31");
    expect(veille("2024-03-01")).toBe("2024-02-29");
    expect(veille(null)).toBeNull();
  });
});
