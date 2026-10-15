import { describe, expect, it } from "vitest";

import { basculerLigne, etatPanier } from "@/lib/reconciliation";

const op = (id: number, montant: string, over = {}) => ({
  id,
  montant,
  bank_account_id: 1,
  statut: "Non rapprochée",
  devise: "MAD",
  ...over,
});
const ec = (id: number, montant: string, over = {}) => ({
  id,
  montant,
  bank_account_id: 1,
  statut: "Non rapprochée",
  devise: "MAD",
  ...over,
});

describe("panier de rapprochement manuel", () => {
  it("additionne en centimes et accepte un panier équilibré", () => {
    const etat = etatPanier([op(1, "12000.00")], [ec(1, "-4000.10"), ec(2, "-7999.90")]);
    expect(etat).toMatchObject({
      totalBanque: "12000.00",
      totalSage: "-12000.00",
      ecart: "0.00",
      type: "1-N",
      blocage: null,
    });
  });

  it("dit pourquoi le rapprochement n'est pas possible", () => {
    expect(etatPanier([], [ec(1, "-1")]).blocage).toBe("vide");
    expect(etatPanier([op(1, "1000")], [ec(1, "-900")]).blocage).toBe("ecart");
    expect(etatPanier([op(1, "900")], [ec(1, "-900", { bank_account_id: 2 })]).blocage).toBe(
      "comptes",
    );
    expect(etatPanier([op(1, "900", { statut: "Rapprochée" })], [ec(1, "-900")]).blocage).toBe(
      "rapprochee",
    );
    const beaucoup = Array.from({ length: 51 }, (_, i) => op(i, "1"));
    expect(etatPanier(beaucoup, [ec(1, "-51")]).blocage).toBe("limite");
  });

  it("compare le montant en devise d'une écriture d'un compte EUR", () => {
    const etat = etatPanier(
      [op(1, "100.00", { devise: "EUR" }), op(2, "50.00", { devise: "EUR" })],
      [ec(1, "-1650.00", { montant_devise: "-150.00", devise: "EUR" })],
    );
    expect(etat).toMatchObject({ ecart: "0.00", type: "N-1", devise: "EUR", blocage: null });
  });

  it("ajoute ou retire une ligne", () => {
    const lignes = basculerLigne([op(1, "1")], op(2, "2"));
    expect(lignes.map((l) => l.id)).toEqual([1, 2]);
    expect(basculerLigne(lignes, op(1, "1")).map((l) => l.id)).toEqual([2]);
  });
});
