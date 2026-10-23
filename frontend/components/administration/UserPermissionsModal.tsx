"use client";

import { RotateCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { changementsPersonne, parModule, permissionsVisibles } from "@/lib/admin";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { getUserPermissions, setUserPermissions } from "@/services/admin";
import type { AdminUser, PermissionPersonne } from "@/types/admin";

/**
 * Permissions d'une personne (23/10/2026) : celles de ses rôles + ses ajouts − ses retraits. Une case
 * par permission, cochée selon l'état final ; l'API recalcule et refuse ce qui n'est pas permis.
 */
export function UserPermissionsModal({
  user,
  onClose,
  onSaved,
}: {
  user: AdminUser;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { toast } = useToast();
  const [permissions, setPermissions] = useState<PermissionPersonne[] | null>(null);
  const [cochees, setCochees] = useState<Set<string>>(new Set());
  const [erreur, setErreur] = useState(false);
  const [essai, setEssai] = useState(0);
  const [envoi, setEnvoi] = useState(false);

  useEffect(() => {
    let annule = false;
    getUserPermissions(user.id).then(
      (items) => {
        if (annule) return;
        setPermissions(items);
        setCochees(new Set(items.filter((p) => p.effective).map((p) => p.code)));
        setErreur(false);
      },
      () => {
        if (!annule) setErreur(true);
      },
    );
    return () => {
      annule = true;
    };
  }, [user.id, essai]);

  const changements = useMemo(
    () => (permissions ? changementsPersonne(permissions, cochees) : { ajouts: [], retraits: [] }),
    [permissions, cochees],
  );
  // Module Écarts masqué : ses cases gardent leur état et sont renvoyées telles quelles
  const visibles = useMemo(
    () => (permissions ? permissionsVisibles(permissions) : []),
    [permissions],
  );
  const groupes = useMemo(() => parModule(visibles), [visibles]);
  const avantAjouts = permissions?.filter((p) => p.personnalisation === true).length ?? 0;
  const avantRetraits = permissions?.filter((p) => p.personnalisation === false).length ?? 0;
  const modifie =
    permissions !== null &&
    (changements.ajouts.length !== avantAjouts ||
      changements.retraits.length !== avantRetraits ||
      permissions.some((p) => p.effective !== cochees.has(p.code)));

  function basculer(code: string) {
    setCochees((actuelles) => {
      const suivantes = new Set(actuelles);
      if (suivantes.has(code)) suivantes.delete(code);
      else suivantes.add(code);
      return suivantes;
    });
  }

  function revenirAuRole() {
    if (!permissions) return;
    const montrees = new Set(visibles.map((p) => p.code));
    setCochees(
      (actuelles) =>
        new Set(
          permissions
            .filter((p) => (montrees.has(p.code) ? p.par_roles.length > 0 : actuelles.has(p.code)))
            .map((p) => p.code),
        ),
    );
  }

  async function enregistrer() {
    setEnvoi(true);
    try {
      await setUserPermissions(user.id, changements);
      toast(`Permissions de ${user.nom} enregistrées : elles s'appliquent tout de suite.`);
      onSaved();
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Enregistrement impossible.", "error");
    } finally {
      setEnvoi(false);
    }
  }

  const roles = user.roles.map((role) => role.nom).join(", ") || "aucun rôle";

  return (
    <Modal
      open
      title={`Permissions de ${user.nom}`}
      onClose={() => !envoi && onClose()}
      footer={
        <>
          <Button
            variant="ghost"
            icon={RotateCcw}
            onClick={revenirAuRole}
            disabled={envoi || !permissions}
          >
            Revenir aux permissions du rôle
          </Button>
          <Button variant="secondary" onClick={onClose} disabled={envoi}>
            Annuler
          </Button>
          <Button onClick={enregistrer} disabled={envoi || !modifie}>
            {envoi ? "Enregistrement..." : "Enregistrer"}
          </Button>
        </>
      }
    >
      <p className="text-sm text-simtis-muted">
        Rôle : <span className="font-medium text-simtis-text">{roles}</span>. Cochez ou décochez une
        permission pour l&apos;ajouter ou la retirer à cette personne seulement ; les autres
        personnes du même rôle ne changent pas.
      </p>
      {erreur ? (
        <div className="mt-4">
          <ErrorState
            message="Impossible de charger les permissions."
            onRetry={() => setEssai((n) => n + 1)}
          />
        </div>
      ) : permissions === null ? (
        <div className="mt-4">
          <LoadingState rows={4} />
        </div>
      ) : (
        <div className="mt-4 max-h-[60vh] space-y-4 overflow-y-auto pr-1">
          {groupes.map(([module, items]) => (
            <fieldset key={module}>
              <legend className="mb-1.5 text-xs font-semibold tracking-wide text-simtis-primary-dark uppercase">
                {module}
              </legend>
              <ul className="space-y-1.5">
                {items.map((permission) => (
                  <LignePermission
                    key={permission.code}
                    permission={permission}
                    cochee={cochees.has(permission.code)}
                    onToggle={() => basculer(permission.code)}
                  />
                ))}
              </ul>
            </fieldset>
          ))}
        </div>
      )}
    </Modal>
  );
}

function LignePermission({
  permission,
  cochee,
  onToggle,
}: {
  permission: PermissionPersonne;
  cochee: boolean;
  onToggle: () => void;
}) {
  const parRole = permission.par_roles.length > 0;
  const ajoutee = cochee && !parRole;
  const retiree = !cochee && parRole;
  const id = `perm-${permission.code}`;
  return (
    <li className="flex items-start gap-2.5 rounded-[10px] px-2 py-1.5 hover:bg-simtis-surface">
      <input
        id={id}
        type="checkbox"
        className="mt-0.5 h-4 w-4 accent-simtis-primary disabled:opacity-50"
        checked={cochee}
        disabled={permission.verrouillee}
        onChange={onToggle}
      />
      <label htmlFor={id} className="min-w-0 flex-1 text-sm">
        <span className="block text-simtis-text">{permission.description}</span>
        <span
          className={cn(
            "block text-xs",
            ajoutee
              ? "font-medium text-simtis-success-fg"
              : retiree
                ? "font-medium text-simtis-warning-fg"
                : "text-simtis-muted",
          )}
        >
          {permission.verrouillee
            ? "Toujours accordée à un administrateur"
            : ajoutee
              ? "Ajoutée pour cette personne"
              : retiree
                ? `Retirée pour cette personne (donnée par le rôle ${permission.par_roles.join(", ")})`
                : parRole
                  ? `Par le rôle ${permission.par_roles.join(", ")}`
                  : "Non accordée"}
        </span>
      </label>
    </li>
  );
}
