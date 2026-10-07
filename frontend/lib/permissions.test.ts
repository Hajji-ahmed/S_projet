import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { NAV_ITEMS, navItems } from "./navigation";
import {
  PERMISSIONS,
  ROUTE_PERMISSIONS,
  canAccess,
  hasAnyPermission,
  requiredPermissionsFor,
} from "./permissions";

// Matrice des rôles chargée par les seeds (backend/app/seeds/reference.py)
const CONSULTATION = ["position.view", "reconciliation.view", "dashboard.view"];
const ROLES = {
  tresorerie: [...CONSULTATION, "banks.manage", "statements.import", "forecasts.manage"],
  comptable: [
    ...CONSULTATION,
    "accounting.import",
    "reconciliation.validate",
    "discrepancies.manage",
  ],
  responsable: [...CONSULTATION, "reconciliation.validate", "discrepancies.manage", "audit.view"],
  direction: CONSULTATION,
  admin: Object.values(PERMISSIONS) as string[],
};

const visibleMenu = (granted: string[]) =>
  NAV_ITEMS.filter((item) => canAccess(granted, item.href)).map((item) => item.label);

describe("codes de permission", () => {
  it("sont identiques à ceux du backend", () => {
    const backendFile = fileURLToPath(
      new URL("../../backend/app/core/permissions.py", import.meta.url),
    );
    const enumBody = readFileSync(backendFile, "utf8").split("PERMISSION_DESCRIPTIONS")[0];
    const backendCodes = [...enumBody.matchAll(/=\s*"([a-z_]+\.[a-z_]+)"/g)].map((m) => m[1]);

    expect(backendCodes.length).toBeGreaterThan(0);
    expect([...backendCodes].sort()).toEqual(Object.values(PERMISSIONS).sort());
  });

  it("chaque page du menu a une règle d'accès", () => {
    for (const item of NAV_ITEMS) {
      expect(ROUTE_PERMISSIONS[item.href], item.href).toBeDefined();
    }
  });

  it("pas de pages Prévisions ni Devises (décision du 05/10/2026)", () => {
    // Les tableaux Prévisions et Devises restent sur la page Position bancaire
    const hrefs = NAV_ITEMS.map((item) => item.href);
    expect(hrefs).not.toContain("/previsions");
    expect(hrefs).not.toContain("/devises");
    expect(ROUTE_PERMISSIONS["/previsions"]).toBeUndefined();
    expect(ROUTE_PERMISSIONS["/devises"]).toBeUndefined();
  });
});

describe("fonction Écarts mise de côté (07/10/2026)", () => {
  it("le menu n'a pas « Écarts » tant que la fonction est coupée", () => {
    expect(NAV_ITEMS.map((item) => item.href)).not.toContain("/ecarts");
    expect(navItems(true).map((item) => item.href)).toContain("/ecarts");
  });
});

describe("hasAnyPermission", () => {
  it("accepte si l'une des permissions est présente", () => {
    expect(hasAnyPermission(["a.b", "audit.view"], ["admin.users", "audit.view"])).toBe(true);
  });

  it("refuse si aucune n'est présente", () => {
    expect(hasAnyPermission(["dashboard.view"], ["admin.users", "admin.roles"])).toBe(false);
  });

  it("accepte tout utilisateur connecté quand rien n'est exigé", () => {
    expect(hasAnyPermission([], [])).toBe(true);
  });
});

describe("requiredPermissionsFor", () => {
  it("s'applique aussi aux sous-pages", () => {
    expect(requiredPermissionsFor("/banques/3")).toEqual(["position.view"]);
  });

  it("ne confond pas deux routes au début identique", () => {
    expect(requiredPermissionsFor("/banquesX")).toEqual([]);
  });

  it("n'exige rien pour une page sans règle", () => {
    expect(requiredPermissionsFor("/design-system")).toEqual([]);
  });
});

describe("menu visible selon le rôle", () => {
  it("l'administrateur voit tout", () => {
    expect(visibleMenu(ROLES.admin)).toEqual(NAV_ITEMS.map((item) => item.label));
  });

  it("la trésorerie voit tout sauf l'administration", () => {
    expect(visibleMenu(ROLES.tresorerie)).not.toContain("Administration");
    expect(visibleMenu(ROLES.tresorerie)).toContain("Relevés");
    expect(visibleMenu(ROLES.tresorerie)).toContain("Position bancaire");
  });

  it("la direction consulte sans administration", () => {
    expect(visibleMenu(ROLES.direction)).toEqual(
      NAV_ITEMS.map((item) => item.label).filter((label) => label !== "Administration"),
    );
  });

  it("seuls l'administrateur et le responsable ouvrent l'historique", () => {
    expect(canAccess(ROLES.admin, "/historique")).toBe(true);
    expect(canAccess(ROLES.responsable, "/historique")).toBe(true);
    expect(canAccess(ROLES.tresorerie, "/historique")).toBe(false);
    expect(canAccess(ROLES.comptable, "/historique")).toBe(false);
    expect(canAccess(ROLES.direction, "/historique")).toBe(false);
  });

  it("un utilisateur sans permission ne voit aucun menu", () => {
    expect(visibleMenu([])).toEqual([]);
  });
});
