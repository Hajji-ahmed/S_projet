import { describe, expect, it } from "vitest";

import { currencyCell, evolutionPoints, formatJour, formatTaux, signTone } from "./position";

describe("currencyCell", () => {
  it("affiche le solde dans sa devise, sans conversion", () => {
    expect(
      currencyCell(
        { bank_id: 1, valeur: "1500.50", date_solde: "2026-10-05", reprise: false },
        "EUR",
      ),
    ).toEqual({ text: "1 500,50 EUR", note: null });
  });

  it("signale un solde repris d'un jour précédent", () => {
    expect(
      currencyCell({ bank_id: 1, valeur: "75.00", date_solde: "2026-10-01", reprise: true }, "USD"),
    ).toEqual({ text: "75 USD", note: "dernier solde connu : 01/10/2026" });
  });

  it("« - » sans compte ni solde, jamais 0", () => {
    expect(
      currencyCell({ bank_id: 1, valeur: null, date_solde: null, reprise: false }, "EUR"),
    ).toEqual({ text: "-", note: null });
  });
});

function jour(date: string, total: string | null) {
  return { date, cellules: [], total, depassement: null };
}

describe("evolutionPoints", () => {
  it("garde les 30 derniers jours, du plus ancien au plus récent", () => {
    const jours = Array.from({ length: 40 }, (_, i) =>
      jour(`2026-09-${String(i + 1).padStart(2, "0")}`, String(i)),
    );

    const points = evolutionPoints(jours, 30);

    expect(points).toHaveLength(30);
    expect(points[0].date).toBe("2026-09-11");
    expect(points.at(-1)?.date).toBe("2026-09-40");
  });

  it("prépare le libellé jj/mm, la valeur à tracer et le texte exact", () => {
    expect(evolutionPoints([jour("2026-10-03", "4465000.50")], 30)).toEqual([
      { date: "2026-10-03", label: "03/10", total: 4465000.5, totalText: "4465000.50" },
    ]);
  });

  it("un jour sans TOTAL reste un vide, jamais 0", () => {
    const [point] = evolutionPoints([jour("2026-09-14", null)], 30);

    expect(point.total).toBeNull();
    expect(point.totalText).toBeNull();
  });

  it("par banque : la facilité de caisse de la banque, au lieu du TOTAL", () => {
    const jours = [
      {
        date: "2026-10-02",
        cellules: [
          { bank_id: 1, valeur: "1200000.00", date_solde: "2026-10-02", reprise: false },
          { bank_id: 3, valeur: null, date_solde: null, reprise: false },
        ],
        total: "1200000.00",
        depassement: null,
      },
    ];

    expect(evolutionPoints(jours, 30, 1)[0]).toMatchObject({
      total: 1200000,
      totalText: "1200000.00",
    });
    // Banque sans valeur ce jour-là : un vide, jamais 0
    expect(evolutionPoints(jours, 30, 3)[0]).toMatchObject({ total: null, totalText: null });
    // Banque absente des cellules : un vide aussi
    expect(evolutionPoints(jours, 30, 99)[0].total).toBeNull();
  });

  it("moins de 30 jours : tous, et aucun jour : liste vide", () => {
    expect(evolutionPoints([jour("2026-09-14", "1")], 30)).toHaveLength(1);
    expect(evolutionPoints([], 30)).toEqual([]);
  });
});

describe("formatTaux", () => {
  it("affiche au moins deux décimales, sans rien tronquer", () => {
    expect(formatTaux("5.5")).toBe("5,50 %");
    expect(formatTaux("5")).toBe("5,00 %");
    expect(formatTaux("4.125")).toBe("4,125 %");
  });

  it("affiche « - » sans taux, jamais 0", () => {
    expect(formatTaux(null)).toBe("-");
  });
});

describe("formatJour", () => {
  it("écrit la date comme le classeur, jj/mm/aa", () => {
    expect(formatJour("2026-09-30")).toBe("30/09/26");
  });
});

describe("signTone", () => {
  it("lit le signe sur le texte exact, sans conversion en nombre", () => {
    expect(signTone("300000.00")).toBe("positive");
    expect(signTone("0.01")).toBe("positive");
    expect(signTone("-100000.00")).toBe("negative");
  });

  it("zéro ou valeur inconnue : neutre", () => {
    expect(signTone("0.00")).toBe("neutral");
    expect(signTone("-0.00")).toBe("neutral");
    expect(signTone("0")).toBe("neutral");
    expect(signTone(null)).toBe("neutral");
  });
});
