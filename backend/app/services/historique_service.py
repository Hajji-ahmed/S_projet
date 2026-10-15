"""Historique (P16.2, 14/10/2026) : lecture du journal d'audit, en français.

`audit_logs` est en ajout seul : cet écran ne fait que lire. Une ligne affiche qui, quand, quelle
action, sur quoi, et un résumé tiré des valeurs ; le détail montre champ par champ l'avant et
l'après. Une action ou une entité inconnue est affichée telle quelle, lisible (« Suppression
releve awb »), jamais masquée.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog
from app.repositories import audit_repository
from app.services.errors import ConflictError, NotFoundError
from app.services.position_service import BUSINESS_TZ

PAR_PAGE = 50

ACTIONS = {
    "connexion": "Connexion",
    "deconnexion": "Déconnexion",
    "echec_connexion": "Échec de connexion",
    "compte_verrouille": "Compte verrouillé",
    "creation_utilisateur": "Création d'utilisateur",
    "modification_utilisateur": "Modification d'utilisateur",
    "activation_utilisateur": "Réactivation d'utilisateur",
    "desactivation_utilisateur": "Désactivation d'utilisateur",
    "modification_mot_de_passe": "Changement de mot de passe",
    "reinitialisation_mot_de_passe": "Réinitialisation du mot de passe",
    "creation_role": "Création de rôle",
    "modification_permissions": "Modification de rôle ou de permissions",
    "suppression_role": "Suppression de rôle",
    "creation_banque": "Création de banque",
    "modification_banque": "Modification de banque",
    "desactivation_banque": "Désactivation de banque",
    "reactivation_banque": "Réactivation de banque",
    "creation_compte": "Création de compte",
    "modification_compte": "Modification de compte",
    "desactivation_compte": "Désactivation de compte",
    "reactivation_compte": "Réactivation de compte",
    "suppression_compte": "Suppression de compte",
    "saisie_solde": "Saisie de solde",
    "correction_solde": "Correction de solde",
    "recalcul_soldes": "Recalcul des soldes",
    "saisie_devises": "Saisie du tableau Devises",
    "saisie_previsions": "Saisie du tableau Prévisions",
    "import_releve": "Import de relevé",
    "import_ecritures": "Import d'écritures Sage",
    "modification_operation": "Modification d'opération",
    "repointage": "Repointage",
    "correction_sens": "Correction du sens",
    "rapprochement_lance": "Rapprochement lancé",
    "validation_rapprochement": "Validation rapprochement",
    "rejet_rapprochement": "Rejet de rapprochement",
    "annulation_rapprochement": "Annulation de rapprochement",
    "rapprochement_manuel": "Rapprochement manuel",
    "export_lettrage": "Export du lettrage",
    "comptabilisation_timbres": "Comptabilisation des droits de timbre",
    "comptabilisation_commissions": "Comptabilisation des commissions",
    "comptabilisation_frais": "Comptabilisation des frais",
    "comptabilisation_manuelle": "Comptabilisation manuelle de frais",
    "export_ecriture_frais": "Export des frais pour Sage",
    "suppression_ecriture_frais": "Suppression d'écriture de frais",
    "creation_ecart": "Création d'écart",
    "modification_ecart": "Modification d'écart",
    "cloture_ecart": "Clôture d'écart",
    "generation_ecarts": "Génération des écarts",
    "modification_parametre": "Modification de paramètre",
    "suppression_mapping": "Suppression de modèle d'import",
    "export_rapport": "Export de rapport",
}

ENTITES = {
    "user": "Utilisateur",
    "user_session": "Session",
    "role": "Rôle",
    "company": "Société",
    "bank": "Banque",
    "bank_account": "Compte bancaire",
    "bank_account_balance": "Solde",
    "bank_statement": "Relevé",
    "bank_transaction": "Opération bancaire",
    "import_batch": "Import",
    "accounting_entry": "Écriture comptable",
    "reconciliation_match": "Rapprochement",
    "reconciliation_rule": "Paramètre de rapprochement",
    "column_mapping": "Modèle d'import",
    "discrepancy": "Écart",
    "rapport": "Rapport",
}

# Champs repris dans le résumé d'une ligne, dans cet ordre
CHAMPS_RESUME = (
    "code",
    "nom",
    "email",
    "fichier_nom",
    "fichier",
    "libelle",
    "montant",
    "type",
    "motif",
    "commentaire",
)


def _lisible(code: str) -> str:
    texte = code.replace("_", " ").strip()
    return texte[:1].upper() + texte[1:]


def libelle_action(code: str) -> str:
    return ACTIONS.get(code, _lisible(code))


def libelle_entite(code: str) -> str:
    return ENTITES.get(code, _lisible(code))


def _texte(valeur: Any) -> str:
    if valeur is None:
        return "-"
    if isinstance(valeur, bool):
        return "oui" if valeur else "non"
    if isinstance(valeur, list):
        return ", ".join(_texte(v) for v in valeur) or "-"
    return str(valeur)


def resume(avant: dict | None, apres: dict | None) -> str:
    """« BP-26-000123 — 50000.00 — À vérifier → Rapprochée » : les valeurs utiles d'une ligne."""
    avant, apres = avant or {}, apres or {}
    morceaux = []
    for champ in CHAMPS_RESUME:
        valeur = apres.get(champ, avant.get(champ))
        if valeur not in (None, "", []):
            morceaux.append(_texte(valeur))
    statut_avant, statut_apres = avant.get("statut"), apres.get("statut")
    if statut_avant and statut_apres and statut_avant != statut_apres:
        morceaux.append(f"{statut_avant} → {statut_apres}")
    elif statut_apres or statut_avant:
        morceaux.append(_texte(statut_apres or statut_avant))
    return " — ".join(morceaux)


@dataclass(frozen=True)
class Difference:
    champ: str
    avant: Any
    apres: Any
    modifie: bool


def differences(avant: dict | None, apres: dict | None) -> list[Difference]:
    """Chaque champ de l'avant ou de l'après, dans l'ordre d'apparition ; `modifie` quand la
    valeur a changé (un champ absent d'un côté compte comme vide)."""
    avant, apres = avant or {}, apres or {}
    champs = list(dict.fromkeys([*avant.keys(), *apres.keys()]))
    return [
        Difference(champ, avant.get(champ), apres.get(champ), avant.get(champ) != apres.get(champ))
        for champ in champs
    ]


@dataclass(frozen=True)
class Ligne:
    entry: AuditLog
    utilisateur: str | None


@dataclass(frozen=True)
class Page:
    lignes: list[Ligne]
    total: int
    page: int
    pages: int


def _bornes(
    date_from: date | None, date_to: date | None
) -> tuple[datetime | None, datetime | None]:
    """Jours du Maroc → instants : du début de `date_from` à la fin de `date_to`."""
    if date_from and date_to and date_from > date_to:
        raise ConflictError("La date de début doit précéder la date de fin.")
    debut = datetime.combine(date_from, time.min, BUSINESS_TZ) if date_from else None
    fin = datetime.combine(date_to + timedelta(days=1), time.min, BUSINESS_TZ) if date_to else None
    return debut, fin


def journal(
    db: Session,
    *,
    page: int = 1,
    user_id: int | None = None,
    action: str | None = None,
    entite: str | None = None,
    entite_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Page:
    debut, fin = _bornes(date_from, date_to)
    page = max(page, 1)
    entries, total = audit_repository.search(
        db,
        limit=PAR_PAGE,
        offset=(page - 1) * PAR_PAGE,
        user_id=user_id,
        action=action,
        entite=entite,
        entite_id=entite_id,
        debut=debut,
        fin=fin,
    )
    noms = audit_repository.user_names(db, {e.user_id for e in entries if e.user_id is not None})
    return Page(
        lignes=[Ligne(entry, noms.get(entry.user_id)) for entry in entries],
        total=total,
        page=page,
        pages=max((total + PAR_PAGE - 1) // PAR_PAGE, 1),
    )


def detail(db: Session, audit_id: int) -> Ligne:
    entry = audit_repository.get(db, audit_id)
    if entry is None:
        raise NotFoundError("Entrée d'historique introuvable.")
    noms = audit_repository.user_names(db, {entry.user_id} if entry.user_id else set())
    return Ligne(entry, noms.get(entry.user_id))


@dataclass(frozen=True)
class Filtres:
    actions: list[tuple[str, str, int]]
    entites: list[tuple[str, str]]
    utilisateurs: list[tuple[int, str]]


def filtres(db: Session) -> Filtres:
    """Valeurs proposées par les listes de filtres : celles présentes dans le journal."""
    actions = [(code, libelle_action(code), nb) for code, nb in audit_repository.actions(db)]
    return Filtres(
        actions=sorted(actions, key=lambda a: a[1].lower()),
        entites=sorted(
            ((code, libelle_entite(code)) for code in audit_repository.entites(db)),
            key=lambda e: e[1].lower(),
        ),
        utilisateurs=sorted(audit_repository.user_names(db).items(), key=lambda u: u[1].lower()),
    )
