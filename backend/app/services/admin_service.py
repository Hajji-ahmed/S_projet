"""Administration (P16.1, 14/10/2026) : utilisateurs, rôles et permissions.

Les permissions sont relues en base à chaque requête (P5) : un changement de rôle ou de matrice
s'applique dès la requête suivante, sans redéploiement. Garde-fous :
- il reste toujours au moins un administrateur actif ;
- un administrateur ne se désactive pas lui-même et ne se retire pas le rôle Administrateur ;
- le rôle Administrateur garde l'administration des utilisateurs et des rôles ;
- un rôle système (seed) garde son code et ne se supprime pas ; un rôle personnalisé ne se
  supprime que sans utilisateur.
Chaque action est auditée avec l'avant et l'après, dans la transaction du changement.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core import security
from app.core.permissions import PERMISSION_DESCRIPTIONS, PermissionCode
from app.models import Permission, Role, User, UserPermission
from app.repositories import admin_repository, auth_repository
from app.repositories.admin_repository import ROLE_ADMIN
from app.services import audit_service
from app.services.auth_service import generate_password, normalize_email
from app.services.errors import ConflictError, NotFoundError

# Le rôle Administrateur ne peut pas perdre ces permissions : sinon plus personne n'administre
PERMISSIONS_ADMIN_OBLIGATOIRES = (PermissionCode.ADMIN_USERS, PermissionCode.ADMIN_ROLES)

# Libellé de chaque module pour regrouper la matrice des permissions à l'écran
MODULES = {
    "banks": "Banques et comptes",
    "statements": "Relevés",
    "position": "Position bancaire",
    "accounting": "Écritures comptables",
    "reconciliation": "Rapprochement",
    "discrepancies": "Écarts",
    "forecasts": "Prévisions",
    "dashboard": "Dashboard",
    "admin": "Administration",
    "audit": "Historique",
}


@dataclass(frozen=True)
class MotDePasse:
    """Mot de passe provisoire : montré une seule fois à l'administrateur, jamais stocké en clair."""

    user: User
    mot_de_passe: str


def _now() -> datetime:
    return datetime.now(UTC)


def _user_state(user: User) -> dict:
    return {
        "nom": user.nom,
        "email": user.email,
        "actif": user.actif,
        "roles": sorted(role.code for role in user.roles),
    }


def _role_state(role: Role) -> dict:
    return {
        "code": role.code,
        "nom": role.nom,
        "description": role.description,
        "permissions": sorted(permission.code for permission in role.permissions),
    }


def _user(db: Session, user_id: int) -> User:
    user = admin_repository.get_user(db, user_id)
    if user is None:
        raise NotFoundError("Utilisateur introuvable.")
    return user


def _roles(db: Session, role_ids: list[int]) -> list[Role]:
    if not role_ids:
        raise ConflictError("Choisissez au moins un rôle.")
    roles = admin_repository.get_roles(db, sorted(set(role_ids)))
    if len(roles) != len(set(role_ids)):
        raise NotFoundError("Rôle introuvable.")
    return roles


def _email(email: str) -> str:
    email = normalize_email(email)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ConflictError("Adresse email invalide.")
    return email


def _nom(nom: str, quoi: str = "Le nom") -> str:
    nom = " ".join(nom.split())
    if not nom:
        raise ConflictError(f"{quoi} est obligatoire.")
    return nom


def _est_admin_actif(user: User) -> bool:
    return user.actif and any(role.code == ROLE_ADMIN for role in user.roles)


def _check_admins_left(db: Session, user: User) -> None:
    """Appelée AVANT de retirer à `user` son statut d'administrateur actif (rôle ou activation) :
    refuse s'il est le dernier. Le rôle ADMIN est verrouillé par l'appelant."""
    if _est_admin_actif(user) and admin_repository.count_active_admins(db) <= 1:
        raise ConflictError("Il doit rester au moins un administrateur actif.")


# --- Permissions par personne (23/10/2026) --------------------------------------------------------


@dataclass(frozen=True)
class PermissionPersonne:
    code: str
    description: str
    module: str
    # Rôles de la personne qui donnent cette permission (noms)
    par_roles: tuple[str, ...]
    # None : comme ses rôles ; True : ajoutée pour la personne ; False : retirée
    personnalisation: bool | None
    effective: bool
    # Case verrouillée : un administrateur garde l'administration des utilisateurs et des rôles
    verrouillee: bool


def _est_admin(user: User) -> bool:
    return any(role.code == ROLE_ADMIN for role in user.roles)


def user_permissions(db: Session, user_id: int) -> list[PermissionPersonne]:
    """Chaque permission connue pour cette personne : d'où elle vient et son état final."""
    user = _user(db, user_id)
    perso = auth_repository.get_personal_permissions(db, user.id)
    roles_par_code: dict[str, list[str]] = {}
    for role in sorted(user.roles, key=lambda r: r.nom):
        for permission in role.permissions:
            roles_par_code.setdefault(permission.code, []).append(role.nom)
    admin = _est_admin(user)
    resultat = []
    for info in list_permissions(db):
        par_roles = tuple(roles_par_code.get(info.code, ()))
        personnalisation = perso.get(info.code)
        effective = personnalisation if personnalisation is not None else bool(par_roles)
        resultat.append(
            PermissionPersonne(
                code=info.code,
                description=info.description,
                module=info.module,
                par_roles=par_roles,
                personnalisation=personnalisation,
                effective=effective,
                verrouillee=admin and info.code in PERMISSIONS_ADMIN_OBLIGATOIRES,
            )
        )
    return resultat


def set_user_permissions(
    db: Session,
    user_id: int,
    *,
    ajouts: list[str],
    retraits: list[str],
    acteur_id: int,
    ip: str | None,
) -> list[PermissionPersonne]:
    """Remplace les ajouts et retraits de la personne, tout ou rien. Un ajout déjà donné par ses
    rôles, ou un retrait d'une permission qu'ils ne donnent pas, est ignoré (rien d'inutile n'est
    enregistré). Un administrateur garde l'administration des utilisateurs et des rôles."""
    user = _user(db, user_id)
    if set(ajouts) & set(retraits):
        raise ConflictError("Une permission ne peut pas être à la fois ajoutée et retirée.")
    permissions = {p.code: p for p in _permissions(db, [*ajouts, *retraits])}
    par_roles = auth_repository.get_role_permission_codes(db, user.id)
    if _est_admin(user):
        bloquees = sorted(set(retraits) & set(PERMISSIONS_ADMIN_OBLIGATOIRES))
        if bloquees:
            raise ConflictError(
                "Un administrateur garde l'administration des utilisateurs et des rôles."
            )
    voulu = {code: True for code in ajouts if code not in par_roles}
    voulu |= {code: False for code in retraits if code in par_roles}

    avant = auth_repository.get_personal_permissions(db, user.id)
    if voulu != avant:
        user.permissions_perso = [
            UserPermission(user_id=user.id, permission_id=permissions[code].id, accordee=accordee)
            for code, accordee in sorted(voulu.items())
        ]
        audit_service.log(
            db,
            user_id=acteur_id,
            action="modification_permissions_utilisateur",
            entite="user",
            entite_id=user.id,
            avant=_etat_perso(avant),
            apres=_etat_perso(voulu),
            ip=ip,
        )
    db.commit()
    db.refresh(user)
    return user_permissions(db, user.id)


def _etat_perso(perso: dict[str, bool]) -> dict:
    return {
        "ajouts": sorted(code for code, accordee in perso.items() if accordee),
        "retraits": sorted(code for code, accordee in perso.items() if not accordee),
    }


# --- Utilisateurs ---------------------------------------------------------------------------------


def list_users(db: Session) -> list[User]:
    return admin_repository.list_users(db)


def create_user(
    db: Session,
    *,
    nom: str,
    email: str,
    role_ids: list[int],
    acteur_id: int,
    ip: str | None,
) -> MotDePasse:
    email = _email(email)
    nom = _nom(nom)
    if admin_repository.get_user_by_email(db, email) is not None:
        raise ConflictError(f"Un compte existe déjà pour {email}.")
    roles = _roles(db, role_ids)
    mot_de_passe = generate_password()
    user = admin_repository.add(
        db,
        User(
            nom=nom,
            email=email,
            mot_de_passe_hash=security.hash_password(mot_de_passe),
            roles=roles,
        ),
    )
    audit_service.log(
        db,
        user_id=acteur_id,
        action="creation_utilisateur",
        entite="user",
        entite_id=user.id,
        apres=_user_state(user),
        ip=ip,
    )
    db.commit()
    return MotDePasse(user, mot_de_passe)


def update_user(
    db: Session,
    user_id: int,
    *,
    nom: str,
    email: str,
    role_ids: list[int],
    acteur_id: int,
    ip: str | None,
) -> User:
    admin_repository.lock_admin_role(db)
    user = _user(db, user_id)
    avant = _user_state(user)
    email = _email(email)
    autre = admin_repository.get_user_by_email(db, email)
    if autre is not None and autre.id != user.id:
        raise ConflictError(f"Un compte existe déjà pour {email}.")
    roles = _roles(db, role_ids)
    if user.id == acteur_id and ROLE_ADMIN in avant["roles"]:
        if ROLE_ADMIN not in {role.code for role in roles}:
            raise ConflictError("Vous ne pouvez pas retirer votre propre rôle Administrateur.")
    if ROLE_ADMIN not in {role.code for role in roles}:
        _check_admins_left(db, user)

    user.nom = _nom(nom)
    user.email = email
    user.roles = roles
    apres = _user_state(user)
    if apres != avant:
        audit_service.log(
            db,
            user_id=acteur_id,
            action="modification_utilisateur",
            entite="user",
            entite_id=user.id,
            avant=avant,
            apres=apres,
            ip=ip,
        )
    db.commit()
    return user


def set_active(db: Session, user_id: int, *, actif: bool, acteur_id: int, ip: str | None) -> User:
    """Désactiver ferme aussitôt toutes les sessions du compte ; l'historique reste intact."""
    admin_repository.lock_admin_role(db)
    user = _user(db, user_id)
    if user.actif == actif:
        return user
    if not actif and user.id == acteur_id:
        raise ConflictError("Vous ne pouvez pas désactiver votre propre compte.")
    if not actif:
        _check_admins_left(db, user)
    user.actif = actif
    sessions = 0
    if not actif:
        sessions = auth_repository.revoke_user_sessions(db, user.id, _now())
    audit_service.log(
        db,
        user_id=acteur_id,
        action="activation_utilisateur" if actif else "desactivation_utilisateur",
        entite="user",
        entite_id=user.id,
        avant={"actif": not actif},
        apres={"actif": actif, "sessions_fermees": sessions},
        ip=ip,
    )
    db.commit()
    return user


def reset_password(db: Session, user_id: int, *, acteur_id: int, ip: str | None) -> MotDePasse:
    """Nouveau mot de passe provisoire ; lève le verrouillage et ferme les sessions ouvertes."""
    user = _user(db, user_id)
    mot_de_passe = generate_password()
    user.mot_de_passe_hash = security.hash_password(mot_de_passe)
    user.echecs_connexion = 0
    user.verrouille_jusqu_a = None
    sessions = auth_repository.revoke_user_sessions(db, user.id, _now())
    audit_service.log(
        db,
        user_id=acteur_id,
        action="reinitialisation_mot_de_passe",
        entite="user",
        entite_id=user.id,
        apres={"email": user.email, "sessions_fermees": sessions},
        ip=ip,
    )
    db.commit()
    return MotDePasse(user, mot_de_passe)


# --- Rôles et permissions -------------------------------------------------------------------------


def list_roles(db: Session) -> list[Role]:
    return admin_repository.list_roles(db)


@dataclass(frozen=True)
class PermissionInfo:
    code: str
    description: str
    module: str


def list_permissions(db: Session) -> list[PermissionInfo]:
    """Permissions connues, groupées par module dans l'ordre de `PermissionCode`."""
    ordre = {code.value: index for index, code in enumerate(PermissionCode)}
    infos = []
    for permission in admin_repository.list_permissions(db):
        module = permission.code.split(".", 1)[0]
        try:
            description = PERMISSION_DESCRIPTIONS[PermissionCode(permission.code)]
        except ValueError:
            description = permission.description or permission.code
        infos.append(PermissionInfo(permission.code, description, MODULES.get(module, module)))
    return sorted(infos, key=lambda info: ordre.get(info.code, len(ordre)))


def _permissions(db: Session, codes: list[str]) -> list[Permission]:
    permissions = admin_repository.get_permissions_by_codes(db, sorted(set(codes)))
    inconnues = sorted(set(codes) - {permission.code for permission in permissions})
    if inconnues:
        raise ConflictError(f"Permission inconnue : {', '.join(inconnues)}.")
    return permissions


def code_role(nom: str) -> str:
    """« Contrôle de gestion » → « PERSO_CONTROLE_DE_GESTION » (40 caractères au plus)."""
    sans_accent = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Z0-9]+", "_", sans_accent.upper()).strip("_")
    return f"PERSO_{slug}"[:40].rstrip("_")


def create_role(
    db: Session,
    *,
    nom: str,
    description: str | None,
    permission_codes: list[str],
    acteur_id: int,
    ip: str | None,
) -> Role:
    """Rôle « Personnalisé » : un nom libre et la liste de permissions choisie."""
    nom = _nom(nom, "Le nom du rôle")
    if admin_repository.get_role_by_nom(db, nom) is not None:
        raise ConflictError(f"Un rôle « {nom} » existe déjà.")
    code = code_role(nom)
    if code == "PERSO" or admin_repository.get_role_by_code(db, code) is not None:
        raise ConflictError("Choisissez un autre nom de rôle.")
    role = admin_repository.add(
        db,
        Role(
            code=code,
            nom=nom,
            description=(description or "").strip() or None,
            systeme=False,
            permissions=_permissions(db, permission_codes),
        ),
    )
    audit_service.log(
        db,
        user_id=acteur_id,
        action="creation_role",
        entite="role",
        entite_id=role.id,
        apres=_role_state(role),
        ip=ip,
    )
    db.commit()
    return role


def update_role(
    db: Session,
    role_id: int,
    *,
    nom: str,
    description: str | None,
    permission_codes: list[str],
    acteur_id: int,
    ip: str | None,
) -> Role:
    """Nom et description (rôle personnalisé seulement) et matrice des permissions."""
    role = admin_repository.get_role(db, role_id, lock=True)
    if role is None:
        raise NotFoundError("Rôle introuvable.")
    avant = _role_state(role)
    # Tout est vérifié avant la première modification
    permissions = _permissions(db, permission_codes)
    if role.code == ROLE_ADMIN:
        manquantes = set(PERMISSIONS_ADMIN_OBLIGATOIRES) - {p.code for p in permissions}
        if manquantes:
            raise ConflictError(
                "Le rôle Administrateur doit garder l'administration des utilisateurs et des rôles."
            )
    if not role.systeme:
        nom = _nom(nom, "Le nom du rôle")
        autre = admin_repository.get_role_by_nom(db, nom)
        if autre is not None and autre.id != role.id:
            raise ConflictError(f"Un rôle « {nom} » existe déjà.")
        role.nom = nom
        role.description = (description or "").strip() or None
    role.permissions = permissions
    apres = _role_state(role)
    if apres != avant:
        audit_service.log(
            db,
            user_id=acteur_id,
            action="modification_permissions",
            entite="role",
            entite_id=role.id,
            avant=avant,
            apres=apres,
            ip=ip,
        )
    db.commit()
    return role


def delete_role(db: Session, role_id: int, *, acteur_id: int, ip: str | None) -> None:
    role = admin_repository.get_role(db, role_id, lock=True)
    if role is None:
        raise NotFoundError("Rôle introuvable.")
    if role.systeme:
        raise ConflictError("Un rôle système ne peut pas être supprimé.")
    if role.users:
        raise ConflictError(
            f"Le rôle « {role.nom} » est attribué à {len(role.users)} utilisateur"
            f"{'s' if len(role.users) > 1 else ''} : retirez-le d'abord."
        )
    avant = _role_state(role)
    admin_repository.delete(db, role)
    audit_service.log(
        db,
        user_id=acteur_id,
        action="suppression_role",
        entite="role",
        entite_id=role_id,
        avant=avant,
        ip=ip,
    )
    db.commit()
