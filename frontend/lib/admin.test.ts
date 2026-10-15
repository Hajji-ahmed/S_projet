import { describe, expect, it } from "vitest";

import { basculer, caseVerrouillee, matriceDe, parModule, rolesModifies } from "@/lib/admin";
import type { AdminRole } from "@/types/admin";

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
