import { describe, expect, it } from "vitest";

import {
  basculer,
  caseVerrouillee,
  changementsPersonne,
  matriceDe,
  parModule,
  rolesModifies,
} from "@/lib/admin";
import type { AdminRole, PermissionPersonne } from "@/types/admin";

function role(id: number, code: string, permissions: string[]): AdminRole {
  return {
    id,
    code,
    nom: code,
    description: null,
    systeme: true,
    permissions,
    nb_utilisateurs: 0,
  };
}

describe("administration", () => {
  it("groupe les permissions par module dans l'ordre reçu", () => {
    const groupes = parModule([
      { code: "banks.manage", description: "", module: "Banques" },
      { code: "audit.view", description: "", module: "Historique" },
      { code: "banks.view", description: "", module: "Banques" },
    ]);

    expect(groupes.map(([module, liste]) => [module, liste.length])).toEqual([
      ["Banques", 2],
      ["Historique", 1],
    ]);
  });

  it("ne garde que les rôles réellement modifiés", () => {
    const roles = [role(1, "ADMIN", ["b", "a"]), role(2, "DIRECTION", ["a"])];
    let matrice = matriceDe(roles);

    expect(rolesModifies(roles, matrice)).toEqual([]);
    matrice = basculer(matrice, 2, "c");
    expect(matrice[2]).toEqual(["a", "c"]);
    expect(rolesModifies(roles, matrice).map((r) => r.code)).toEqual(["DIRECTION"]);
    matrice = basculer(matrice, 2, "c");
    expect(rolesModifies(roles, matrice)).toEqual([]);
  });

  it("verrouille l'administration du rôle Administrateur", () => {
    expect(caseVerrouillee(role(1, "ADMIN", []), "admin.roles")).toBe(true);
    expect(caseVerrouillee(role(1, "ADMIN", []), "dashboard.view")).toBe(false);
    expect(caseVerrouillee(role(2, "DIRECTION", []), "admin.roles")).toBe(false);
  });
});

describe("changementsPersonne (23/10/2026)", () => {
  const permission = (code: string, par_roles: string[]): PermissionPersonne => ({
    code,
    description: code,
    module: "M",
    par_roles,
    personnalisation: null,
    effective: par_roles.length > 0,
    verrouillee: false,
  });
  const permissions = [
    permission("dashboard.view", ["Comptable"]),
    permission("audit.view", []),
    permission("accounting.import", ["Comptable"]),
  ];

  it("ajoute une case cochée hors rôle et retire une case du rôle décochée", () => {
    expect(changementsPersonne(permissions, new Set(["audit.view", "accounting.import"]))).toEqual({
      ajouts: ["audit.view"],
      retraits: ["dashboard.view"],
    });
  });

  it("n'envoie rien quand les cases suivent le rôle", () => {
    expect(
      changementsPersonne(permissions, new Set(["dashboard.view", "accounting.import"])),
    ).toEqual({ ajouts: [], retraits: [] });
  });
});
