"use client";

import { useMemo, useState } from "react";

import { Field, TextInput } from "@/components/ui/Field";
import { FormModal } from "@/components/ui/FormModal";
import { parModule } from "@/lib/admin";
import { ApiError } from "@/lib/api";
import { createRole, updateRole } from "@/services/admin";
import type { AdminPermission, AdminRole } from "@/types/admin";

/**
 * Rôle « Personnalisé » : création (nom, description, permissions) ou renommage. Les permissions
 * d'un rôle existant se modifient dans la matrice.
 */
export function RoleFormModal({
  role,
  permissions,
  onClose,
  onSaved,
}: {
  role: AdminRole | null;
  permissions: AdminPermission[];
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [nom, setNom] = useState(role?.nom ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [choisies, setChoisies] = useState<string[]>(role?.permissions ?? []);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const groupes = useMemo(() => parModule(permissions), [permissions]);

  async function enregistrer() {
    if (!nom.trim()) {
      setErreur("Le nom du rôle est obligatoire.");
      return;
    }
    setEnvoi(true);
    setErreur(null);
    const data = { nom, description: description.trim() || null, permissions: choisies };
    try {
      if (role) {
        await updateRole(role.id, data);
        onSaved("Rôle enregistré.");
      } else {
        const cree = await createRole(data);
        onSaved(`Rôle « ${cree.nom} » créé.`);
      }
    } catch (error) {
      setErreur(error instanceof ApiError ? error.message : "Enregistrement impossible.");
      setEnvoi(false);
    }
  }

  return (
    <FormModal
      open
      title={role ? "Renommer le rôle" : "Nouveau rôle personnalisé"}
      onClose={onClose}
      onSubmit={enregistrer}
      submitLabel={role ? "Enregistrer" : "Créer le rôle"}
      submitting={envoi}
      error={erreur}
    >
      <div className="space-y-4">
        <Field label="Nom" htmlFor="admin-role-nom" required>
          <TextInput
            id="admin-role-nom"
            value={nom}
            maxLength={80}
            onChange={(event) => setNom(event.target.value)}
            autoFocus
          />
        </Field>
        <Field label="Description" htmlFor="admin-role-description">
          <TextInput
            id="admin-role-description"
            value={description}
            maxLength={500}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        {!role && (
          <fieldset className="max-h-[320px] space-y-3 overflow-y-auto rounded-[12px] border border-simtis-border p-3">
            <legend className="px-1 text-sm font-medium text-simtis-text">Permissions</legend>
            {groupes.map(([module, liste]) => (
              <div key={module}>
                <p className="mb-1 text-xs font-semibold text-simtis-primary-dark">{module}</p>
                {liste.map((permission) => (
                  <label
                    key={permission.code}
                    className="flex cursor-pointer items-center gap-2.5 rounded-md px-1 py-1 text-sm hover:bg-simtis-surface"
                  >
                    <input
                      type="checkbox"
                      checked={choisies.includes(permission.code)}
                      onChange={() =>
                        setChoisies((codes) =>
                          codes.includes(permission.code)
                            ? codes.filter((c) => c !== permission.code)
                            : [...codes, permission.code],
                        )
                      }
                      className="h-4 w-4 accent-simtis-primary"
                    />
                    {permission.description}
                  </label>
                ))}
              </div>
            ))}
          </fieldset>
        )}
      </div>
    </FormModal>
  );
}
