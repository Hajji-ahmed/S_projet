import { describe, expect, it, vi } from "vitest";

import { isCollapsed, setCollapsed, subscribe } from "./sidebar";

describe("barre de navigation réduite", () => {
  it("est agrandie par défaut, même sans stockage disponible", () => {
    expect(isCollapsed()).toBe(false);
  });

  it("retient le choix de la visite et prévient l'écran", () => {
    const listener = vi.fn();
    const unsubscribe = subscribe(listener);

    setCollapsed(true);
    expect(isCollapsed()).toBe(true);
    setCollapsed(false);
    expect(isCollapsed()).toBe(false);

    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
  });
});
