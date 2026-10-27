import { afterEach, describe, expect, it, vi } from "vitest";

import { estPleinEcran, setPleinEcran, subscribe } from "./pleinEcran";

describe("mode plein écran", () => {
  afterEach(() => setPleinEcran(false));

  it("est désactivé au départ et prévient les abonnés d'un changement", () => {
    const listener = vi.fn();
    const desabonner = subscribe(listener);

    expect(estPleinEcran()).toBe(false);
    setPleinEcran(true);
    expect(estPleinEcran()).toBe(true);
    expect(listener).toHaveBeenCalledTimes(1);

    desabonner();
    setPleinEcran(false);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("ne prévient personne quand la valeur ne change pas", () => {
    const listener = vi.fn();
    const desabonner = subscribe(listener);

    setPleinEcran(false);

    expect(listener).not.toHaveBeenCalled();
    desabonner();
  });
});
