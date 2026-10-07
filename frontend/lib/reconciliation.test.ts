import { describe, expect, it } from "vitest";

import {
  absolute,
  defaultPeriod,
  defaultSelection,
  ecartManuel,
  filterProposals,
  formatScore,
  rapprochable,
  reconciliationQuery,
  selectionSummary,
  sensBanque,
  sensSage,
  statutsVolet,
  toggleStatut,
  validable,
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

function proposal(
  id: number,
  score: string,
  forte: boolean,
  montant = "100.00",
  ecriture = "-100.00",
) {
  return {
    id,
    statut: "Proposée",
    score,
    forte,
    operation: { montant },
    ecriture: { montant: ecriture },
  } as unknown as Correspondance;
}

describe("propositions en attente", () => {
  const strong = proposal(1, "95.00", true, "-250.50", "250.50");
  const weak = proposal(2, "60.00", false);
  const unequal = proposal(3, "92.00", true, "100.00", "-90.00");
  const items = [weak, unequal, strong];

  it("ne valide que les propositions équilibrées", () => {
    expect(validable(strong)).toBe(true);
    expect(validable(unequal)).toBe(false);
    expect(validable({ ...weak, statut: "Validée" })).toBe(false);
  });

  it("coche d'office les seules fortes validables", () => {
    expect([...defaultSelection(items)]).toEqual([1]);
  });

  it("filtre fortes / à vérifier, la plus forte d'abord", () => {
    expect(filterProposals(items, "toutes").map((p) => p.id)).toEqual([1, 3, 2]);
    expect(filterProposals(items, "fortes").map((p) => p.id)).toEqual([1, 3]);
    expect(filterProposals(items, "a_verifier").map((p) => p.id)).toEqual([2]);
    // Le filtre « Ambiguës » ne montre que les opérations sans proposition
    expect(filterProposals(items, "ambigues")).toEqual([]);
  });

  it("résume la sélection en centimes exacts", () => {
    expect(selectionSummary(items, new Set([1, 2]))).toEqual({
      nb: 2,
      faibles: 1,
      total: "350.50",
    });
    expect(selectionSummary(items, new Set())).toEqual({ nb: 0, faibles: 0, total: "0.00" });
  });
});

describe("sensSage", () => {
  it("lit le montant Sage : positif = crédit (sortie de banque), négatif = débit", () => {
    // Droit de timbre : 1 DH au débit en banque, 1 DH au crédit du compte banque dans Sage
    expect(sensSage("1.00")).toBe("crédit Sage");
    expect(sensSage("-50000.00")).toBe("débit Sage");
  });
});

describe("reconciliationQuery sans À vérifier", () => {
  it("ajoute sans_a_verifier seulement quand il est demandé", () => {
    expect(reconciliationQuery(1, { sansAVerifier: true, page: 1 })).toBe(
      "?company_id=1&sans_a_verifier=true&page=1",
    );
    expect(reconciliationQuery(1, { page: 1 })).toBe("?company_id=1&page=1");
  });
});

describe("statutsVolet", () => {
  it("ne propose « Écart » que si la fonction Écarts est active", () => {
    expect(statutsVolet(false)).toEqual(["Non rapprochée", "Rapprochée"]);
    expect(statutsVolet(true)).toEqual(["Non rapprochée", "Rapprochée", "Écart"]);
  });
});
