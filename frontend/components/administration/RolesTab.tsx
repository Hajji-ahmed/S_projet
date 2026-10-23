"use client";

import { Lock, Pencil, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";

import { RoleFormModal } from "@/components/administration/RoleFormModal";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import {
  basculer,
  caseVerrouillee,
  matriceDe,
  parModule,
  permissionsVisibles,
  rolesModifies,
  type Matrice,
} from "@/lib/admin";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { deleteRole, listPermissions, listRoles, updateRole } from "@/services/admin";
import type { AdminPermission, AdminRole } from "@/types/admin";

/**
 * Matrice rôles × permissions. Les cases cochées sont un brouillon ; « Enregistrer » envoie les
 * rôles modifiés. Un changement s'applique dès la requête suivante des utilisateurs concernés.
 */
export function RolesTab() {
  const { toast } = useToast();
  const [roles, setRoles] = useState<AdminRole[] | null>(null);
  const [permissions, setPermissions] = useState<AdminPermission[]>([]);
  const [matrice, setMatrice] = useState<Matrice>({});
  const [erreur, setErreur] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [formulaire, setFormulaire] = useState<AdminRole | "nouveau" | null>(null);
  const [suppression, setSuppression] = useState<AdminRole | null>(null);

  const [version, setVersion] = useState(0);
  const charger = useCallback(() => setVersion((n) => n + 1), []);

  useEffect(() => {
    let annule = false;
    Promise.all([listRoles(), listPermissions()]).then(
      ([r, p]) => {
        if (annule) return;
        setRoles(r);
        setPermissions(p);
        setMatrice(matriceDe(r));
        setErreur(false);
      },
      () => {
        if (!annule) setErreur(true);
      },
    );
    return () => {
      annule = true;
    };
  }, [version]);

  const modifies = useMemo(() => (roles ? rolesModifies(roles, matrice) : []), [roles, matrice]);
  // Module Écarts masqué tant que la fonction est mise de côté ; la matrice garde ses cases
  const visibles = useMemo(() => permissionsVisibles(permissions), [permissions]);
  const groupes = useMemo(() => parModule(visibles), [visibles]);

  async function enregistrer() {
    setEnvoi(true);
    try {
      for (const role of modifies) {
        await updateRole(role.id, {
          nom: role.nom,
          description: role.description,
          permissions: matrice[role.id] ?? [],
        });
      }
      toast(
        `Permissions enregistrées pour ${modifies.length} rôle${modifies.length > 1 ? "s" : ""}.`,
      );
      charger();
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Enregistrement impossible.", "error");
      charger();
    } finally {
      setEnvoi(false);
    }
  }

  async function supprimer() {
    if (!suppression) return;
    setEnvoi(true);
    try {
      await deleteRole(suppression.id);
      toast(`Rôle « ${suppression.nom} » supprimé.`);
      setSuppression(null);
      charger();
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Suppression impossible.", "error");
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <Card title="Rôles et permissions" icon={ShieldCheck}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-simtis-muted">
          Cochez les permissions de chaque rôle. Un changement s&apos;applique dès la requête
          suivante des utilisateurs concernés, sans redéploiement.
        </p>
        <Button
          variant="secondary"
          icon={Plus}
          onClick={() => setFormulaire("nouveau")}
          disabled={modifies.length > 0}
          title={modifies.length > 0 ? "Enregistrez d'abord la matrice" : undefined}
        >
          Nouveau rôle
        </Button>
      </div>

      {erreur ? (
        <ErrorState message="Impossible de charger les rôles." onRetry={charger} />
      ) : roles === null ? (
        <LoadingState rows={6} />
      ) : (
        <div className="overflow-x-auto rounded-[14px] border border-simtis-border">
          <table className="w-full border-collapse text-[13.5px]">
            <thead>
              <tr className="border-b border-simtis-border bg-simtis-light">
                <th
                  scope="col"
                  className="sticky left-0 z-10 min-w-[260px] bg-simtis-light px-4 py-3 text-left text-[13px] font-semibold text-simtis-primary-dark"
                >
                  Permission
                </th>
                {roles.map((role) => (
                  <th key={role.id} scope="col" className="min-w-[128px] px-2 py-3 align-top">
                    <span className="block text-[13px] font-semibold text-simtis-text">
                      {role.nom}
                    </span>
                    <span className="mt-0.5 block text-[11px] font-normal text-simtis-muted">
                      {role.systeme ? "système" : "personnalisé"} · {role.nb_utilisateurs}{" "}
                      utilisateur{role.nb_utilisateurs > 1 ? "s" : ""}
                    </span>
                    {!role.systeme && (
                      <span className="mt-1 flex justify-center gap-0.5">
                        <button
                          type="button"
                          title="Renommer"
                          aria-label={`Renommer ${role.nom}`}
                          onClick={() => setFormulaire(role)}
                          disabled={modifies.length > 0}
                          className="rounded-md p-1 text-simtis-muted hover:bg-simtis-light hover:text-simtis-primary disabled:opacity-40"
                        >
                          <Pencil className="h-3.5 w-3.5" aria-hidden />
                        </button>
                        <button
                          type="button"
                          title="Supprimer"
                          aria-label={`Supprimer ${role.nom}`}
                          onClick={() => setSuppression(role)}
                          disabled={modifies.length > 0}
                          className="rounded-md p-1 text-simtis-muted hover:bg-simtis-danger-bg hover:text-simtis-danger-fg disabled:opacity-40"
                        >
                          <Trash2 className="h-3.5 w-3.5" aria-hidden />
                        </button>
                      </span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {groupes.map(([module, liste]) => (
                <Fragment key={module}>
                  <tr className="bg-simtis-background">
                    <th
                      colSpan={roles.length + 1}
                      scope="colgroup"
                      className="sticky left-0 px-4 py-2 text-left text-xs font-semibold tracking-wide text-simtis-primary-dark"
                    >
                      {module}
                    </th>
                  </tr>
                  {liste.map((permission) => (
                    <tr
                      key={permission.code}
                      className="border-b border-simtis-border/70 transition-colors duration-150 hover:bg-simtis-light/40"
                    >
                      <th
                        scope="row"
                        className="sticky left-0 z-10 bg-simtis-card px-4 py-2.5 text-left font-normal"
                      >
                        <span className="block text-simtis-text">{permission.description}</span>
                        <span className="block font-mono text-[11px] text-simtis-muted">
                          {permission.code}
                        </span>
                      </th>
                      {roles.map((role) => {
                        const coche = (matrice[role.id] ?? []).includes(permission.code);
                        const verrou = caseVerrouillee(role, permission.code);
                        return (
                          <td key={role.id} className="px-2 py-2.5 text-center">
                            {verrou ? (
                              <span
                                title="Le rôle Administrateur garde l'administration"
                                className="inline-grid h-5 w-5 place-items-center text-simtis-primary"
                              >
                                <Lock className="h-4 w-4" aria-label="Toujours accordée" />
                              </span>
                            ) : (
                              <input
                                type="checkbox"
                                checked={coche}
                                aria-label={`${permission.description} pour ${role.nom}`}
                                onChange={() =>
                                  setMatrice((m) => basculer(m, role.id, permission.code))
                                }
                                className="h-4 w-4 cursor-pointer accent-simtis-primary"
                              />
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modifies.length > 0 && (
        <div
          className={cn(
            "sticky bottom-4 z-20 mt-4 flex flex-wrap items-center justify-between gap-3 rounded-[14px] border border-simtis-border bg-simtis-card px-4 py-3 shadow-simtis-hover",
          )}
        >
          <p className="text-sm text-simtis-text">
            {modifies.length} rôle{modifies.length > 1 ? "s" : ""} modifié
            {modifies.length > 1 ? "s" : ""} : {modifies.map((role) => role.nom).join(", ")}
          </p>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => roles && setMatrice(matriceDe(roles))}
              disabled={envoi}
            >
              Annuler
            </Button>
            <Button onClick={enregistrer} disabled={envoi}>
              {envoi ? "Enregistrement..." : "Enregistrer"}
            </Button>
          </div>
        </div>
      )}

      {formulaire !== null && (
        <RoleFormModal
          role={formulaire === "nouveau" ? null : formulaire}
          permissions={visibles}
          onClose={() => setFormulaire(null)}
          onSaved={(message) => {
            setFormulaire(null);
            toast(message);
            charger();
          }}
        />
      )}

      {suppression && (
        <Modal
          open
          title="Supprimer ce rôle ?"
          onClose={() => !envoi && setSuppression(null)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setSuppression(null)} disabled={envoi}>
                Annuler
              </Button>
              <Button variant="danger" onClick={supprimer} disabled={envoi}>
                {envoi ? "Suppression..." : "Supprimer"}
              </Button>
            </>
          }
        >
          <p>
            Le rôle <strong>{suppression.nom}</strong> sera supprimé. Un rôle encore attribué à un
            utilisateur ne peut pas l&apos;être.
          </p>
        </Modal>
      )}
    </Card>
  );
}
