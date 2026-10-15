"use client";

import { useState } from "react";

import { Field, TextInput } from "@/components/ui/Field";
import { FormModal } from "@/components/ui/FormModal";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { createUser, updateUser } from "@/services/admin";
import type { AdminRole, AdminUser, PasswordResult } from "@/types/admin";

/** Création ou modification d'un utilisateur : nom, email et rôles. */
export function UserFormModal({
  user,
  roles,
  onClose,
  onCreated,
  onSaved,
}: {
  /** null : nouvel utilisateur. */
  user: AdminUser | null;
  roles: AdminRole[];
  onClose: () => void;
  onCreated: (result: PasswordResult) => void;
  onSaved: () => void;
}) {
  const [nom, setNom] = useState(user?.nom ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [roleIds, setRoleIds] = useState<number[]>(user?.roles.map((role) => role.id) ?? []);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  function basculer(id: number) {
    setRoleIds((ids) => (ids.includes(id) ? ids.filter((i) => i !== id) : [...ids, id]));
  }

  async function enregistrer() {
    if (!nom.trim() || !email.trim()) {
      setErreur("Le nom et l'email sont obligatoires.");
      return;
    }
    if (roleIds.length === 0) {
      setErreur("Choisissez au moins un rôle.");
      return;
    }
    setEnvoi(true);
    setErreur(null);
    const data = { nom, email, role_ids: roleIds };
    try {
      if (user) {
        await updateUser(user.id, data);
        onSaved();
      } else {
        onCreated(await createUser(data));
      }
    } catch (error) {
      setErreur(error instanceof ApiError ? error.message : "Enregistrement impossible.");
      setEnvoi(false);
    }
  }

  return (
    <FormModal
      open
      title={user ? "Modifier l'utilisateur" : "Nouvel utilisateur"}
      onClose={onClose}
      onSubmit={enregistrer}
      submitLabel={user ? "Enregistrer" : "Créer le compte"}
      submitting={envoi}
      error={erreur}
    >
      <div className="space-y-4">
        <Field label="Nom" htmlFor="admin-user-nom" required>
          <TextInput
            id="admin-user-nom"
            value={nom}
            maxLength={120}
            onChange={(event) => setNom(event.target.value)}
            autoFocus
          />
        </Field>
        <Field
          label="Email"
          htmlFor="admin-user-email"
          required
          hint="Sert d'identifiant de connexion."
        >
          <TextInput
            id="admin-user-email"
            type="email"
            value={email}
            maxLength={255}
            onChange={(event) => setEmail(event.target.value)}
          />
        </Field>
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium text-simtis-text">
            Rôles <span className="text-simtis-danger">*</span>
          </legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {roles.map((role) => {
              const coche = roleIds.includes(role.id);
              return (
                <label
                  key={role.id}
                  className={cn(
                    "flex cursor-pointer items-start gap-2.5 rounded-[10px] border px-3 py-2.5 transition-colors duration-150",
                    coche
                      ? "border-simtis-primary bg-simtis-light"
                      : "border-simtis-border hover:bg-simtis-surface",
                  )}
                >
                  <input
                    type="checkbox"
                    checked={coche}
                    onChange={() => basculer(role.id)}
                    className="mt-0.5 h-4 w-4 accent-simtis-primary"
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-simtis-text">{role.nom}</span>
                    <span className="block text-xs text-simtis-muted">
                      {role.permissions.length} permission{role.permissions.length > 1 ? "s" : ""}
                      {!role.systeme && " · personnalisé"}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>
        {!user && (
          <p className="text-xs text-simtis-muted">
            Un mot de passe provisoire sera généré et affiché une seule fois après la création.
          </p>
        )}
      </div>
    </FormModal>
  );
}
