"use client";

import { KeyRound, Lock, Pencil, Plus, Power, ShieldCheck, UserRound } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { PasswordModal } from "@/components/administration/PasswordModal";
import { UserFormModal } from "@/components/administration/UserFormModal";
import { UserPermissionsModal } from "@/components/administration/UserPermissionsModal";
import { useAuth } from "@/components/auth/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/statements";
import { listRoles, listUsers, resetPassword, setUserStatus } from "@/services/admin";
import type { AdminRole, AdminUser, PasswordResult } from "@/types/admin";

type Ligne = AdminUser & Record<string, unknown>;

/** Utilisateurs : créer, modifier les rôles, activer / désactiver, réinitialiser le mot de passe. */
export function UsersTab() {
  const { user: moi } = useAuth();
  const { toast } = useToast();
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [roles, setRoles] = useState<AdminRole[]>([]);
  const [erreur, setErreur] = useState(false);
  const [formulaire, setFormulaire] = useState<AdminUser | "nouveau" | null>(null);
  const [motDePasse, setMotDePasse] = useState<{ titre: string; result: PasswordResult } | null>(
    null,
  );
  const [confirmation, setConfirmation] = useState<{
    type: "statut" | "mot_de_passe";
    user: AdminUser;
  } | null>(null);
  const [envoi, setEnvoi] = useState(false);
  // Permissions propres à une personne (23/10/2026)
  const [permissionsDe, setPermissionsDe] = useState<AdminUser | null>(null);

  const [version, setVersion] = useState(0);
  const charger = useCallback(() => setVersion((n) => n + 1), []);

  useEffect(() => {
    let annule = false;
    Promise.all([listUsers(), listRoles()]).then(
      ([u, r]) => {
        if (annule) return;
        setUsers(u);
        setRoles(r);
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

  async function confirmer() {
    if (!confirmation) return;
    setEnvoi(true);
    try {
      if (confirmation.type === "statut") {
        const actif = !confirmation.user.actif;
        await setUserStatus(confirmation.user.id, actif);
        toast(actif ? "Compte réactivé." : "Compte désactivé : ses sessions sont fermées.");
      } else {
        const result = await resetPassword(confirmation.user.id);
        setMotDePasse({ titre: "Mot de passe réinitialisé", result });
      }
      setConfirmation(null);
      charger();
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Action impossible.", "error");
    } finally {
      setEnvoi(false);
    }
  }

  const colonnes: Column<Ligne>[] = [
    {
      key: "nom",
      header: "Utilisateur",
      render: (u) => (
        <span className="flex items-center gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-simtis-light text-sm font-semibold text-simtis-primary">
            {u.nom.charAt(0).toUpperCase()}
          </span>
          <span className="min-w-0">
            <span className="block font-medium text-simtis-text">
              {u.nom}
              {u.id === moi?.id && <span className="ml-1.5 text-xs text-simtis-muted">(vous)</span>}
            </span>
            <span className="block text-xs text-simtis-muted">{u.email}</span>
          </span>
        </span>
      ),
    },
    {
      key: "roles",
      header: "Rôles",
      render: (u) => (
        <span className="flex flex-wrap gap-1">
          {u.roles.map((role) => (
            <span
              key={role.id}
              className="rounded-full bg-simtis-light px-2 py-0.5 text-xs font-medium text-simtis-primary-dark"
            >
              {role.nom}
            </span>
          ))}
          {(u.nb_ajouts > 0 || u.nb_retraits > 0) && (
            <span
              className="rounded-full bg-simtis-warning-bg px-2 py-0.5 text-xs font-medium text-simtis-warning-fg tabular-nums"
              title="Permissions ajoutées / retirées pour cette personne, en plus de son rôle"
            >
              +{u.nb_ajouts} / −{u.nb_retraits}
            </span>
          )}
        </span>
      ),
    },
    {
      key: "actif",
      header: "Statut",
      render: (u) => (
        <span className="flex items-center gap-1.5">
          <StatusBadge status={u.actif ? "Actif" : "Inactif"} />
          {u.verrouille && (
            <span title="Verrouillé après plusieurs échecs de connexion">
              <Lock className="h-4 w-4 text-simtis-warning-fg" aria-label="Verrouillé" />
            </span>
          )}
        </span>
      ),
    },
    {
      key: "dernier_login",
      header: "Dernière connexion",
      render: (u) =>
        u.dernier_login ? (
          <span className="tabular-nums">{formatDateTime(u.dernier_login)}</span>
        ) : (
          <span className="text-simtis-muted">Jamais</span>
        ),
    },
    {
      key: "actions",
      header: "Actions",
      align: "right",
      render: (u) => (
        <span className="flex justify-end gap-1">
          <IconAction label="Modifier" icon={Pencil} onClick={() => setFormulaire(u)} />
          <IconAction
            label="Permissions de cette personne"
            icon={ShieldCheck}
            onClick={() => setPermissionsDe(u)}
          />
          <IconAction
            label="Réinitialiser le mot de passe"
            icon={KeyRound}
            onClick={() => setConfirmation({ type: "mot_de_passe", user: u })}
          />
          <IconAction
            label={u.actif ? "Désactiver" : "Réactiver"}
            icon={Power}
            danger={u.actif}
            disabled={u.id === moi?.id}
            onClick={() => setConfirmation({ type: "statut", user: u })}
          />
        </span>
      ),
    },
  ];

  return (
    <Card title="Utilisateurs" icon={UserRound}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-simtis-muted">
          {users ? `${users.filter((u) => u.actif).length} actifs sur ${users.length}` : ""}
        </p>
        <Button icon={Plus} onClick={() => setFormulaire("nouveau")}>
          Nouvel utilisateur
        </Button>
      </div>
      {erreur ? (
        <ErrorState message="Impossible de charger les utilisateurs." onRetry={charger} />
      ) : users === null ? (
        <LoadingState rows={4} />
      ) : (
        <DataTable
          columns={colonnes}
          rows={users as Ligne[]}
          getRowKey={(u) => String(u.id)}
          isRowMuted={(u) => !u.actif}
          emptyMessage="Aucun utilisateur."
        />
      )}

      {formulaire !== null && (
        <UserFormModal
          user={formulaire === "nouveau" ? null : formulaire}
          roles={roles}
          onClose={() => setFormulaire(null)}
          onCreated={(result) => {
            setFormulaire(null);
            setMotDePasse({ titre: "Compte créé", result });
            charger();
          }}
          onSaved={() => {
            setFormulaire(null);
            toast("Utilisateur enregistré.");
            charger();
          }}
        />
      )}

      {permissionsDe && (
        <UserPermissionsModal
          user={permissionsDe}
          onClose={() => setPermissionsDe(null)}
          onSaved={() => {
            setPermissionsDe(null);
            charger();
          }}
        />
      )}

      {motDePasse && (
        <PasswordModal
          titre={motDePasse.titre}
          result={motDePasse.result}
          onClose={() => setMotDePasse(null)}
        />
      )}

      {confirmation && (
        <Modal
          open
          title={
            confirmation.type === "mot_de_passe"
              ? "Réinitialiser le mot de passe ?"
              : confirmation.user.actif
                ? "Désactiver ce compte ?"
                : "Réactiver ce compte ?"
          }
          onClose={() => !envoi && setConfirmation(null)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setConfirmation(null)} disabled={envoi}>
                Annuler
              </Button>
              <Button
                variant={
                  confirmation.type === "statut" && confirmation.user.actif ? "danger" : "primary"
                }
                onClick={confirmer}
                disabled={envoi}
              >
                {envoi ? "En cours..." : "Confirmer"}
              </Button>
            </>
          }
        >
          <p>
            <strong>{confirmation.user.nom}</strong> ({confirmation.user.email})
          </p>
          <p className="mt-2 text-simtis-muted">
            {confirmation.type === "mot_de_passe"
              ? "Un nouveau mot de passe provisoire sera généré et affiché une seule fois. Les sessions ouvertes de ce compte seront fermées."
              : confirmation.user.actif
                ? "L'utilisateur ne pourra plus se connecter et ses sessions ouvertes seront fermées. Son historique est conservé."
                : "L'utilisateur pourra de nouveau se connecter avec son mot de passe."}
          </p>
        </Modal>
      )}
    </Card>
  );
}

function IconAction({
  label,
  icon: Icon,
  onClick,
  danger = false,
  disabled = false,
}: {
  label: string;
  icon: typeof Pencil;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className={
        "rounded-[10px] p-2 transition-colors duration-150 disabled:pointer-events-none disabled:opacity-40 " +
        (danger
          ? "text-simtis-danger-fg hover:bg-simtis-danger-bg"
          : "text-simtis-muted hover:bg-simtis-light hover:text-simtis-primary")
      }
    >
      <Icon className="h-4 w-4" aria-hidden />
    </button>
  );
}
