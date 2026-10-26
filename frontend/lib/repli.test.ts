import { describe, expect, it, vi } from "vitest";

import { repli } from "./repli";

describe("repli (26/10/2026)", () => {
  it("vaut la valeur par défaut, puis le dernier choix, et prévient les abonnés", () => {
    const etat = repli("test.repli", false);
    const abonne = vi.fn();
    etat.subscribe(abonne);

    expect(etat.lire()).toBe(false);
    etat.ecrire(true);

    expect(etat.lire()).toBe(true);
    expect(abonne).toHaveBeenCalledTimes(1);
  });
});
