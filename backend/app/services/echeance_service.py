"""Reprise de l'échéance Sage d'écritures déjà importées (04/11/2026) : `python -m app.cli
completer-echeances`. Le grand livre AWB titre sa colonne d'échéance par une date (31/12/2025) au
lieu de « ECH » : l'import ne l'a pas reconnue et les écritures n'ont pas d'échéance. La commande
relit le fichier avec les règles de l'import, retrouve chaque écriture par son empreinte (qui ne
contient pas l'échéance) et remplit seulement les échéances vides."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from openpyxl.utils import column_index_from_string, get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AccountingEntry, Company
from app.repositories import auth_repository
from app.services import accounting_import_service, audit_service, import_file
from app.services.accounting_import_service import ACCOUNTING_FIELDS, FIELD_LABELS, EntryLine
from app.services.errors import ConflictError, NotFoundError
from app.services.import_file import HASH_BATCH

EXEMPLES = 20  # lignes non trouvées ou en conflit affichées


@dataclass
class Bilan:
    societe: str
    feuille: str
    colonne: str  # lettre de la colonne d'échéance
    correspondance: list[str] = field(default_factory=list)  # « Date : B », pour vérifier
    lignes: int = 0  # lignes de compte bancaire lues dans le fichier
    ignorees: int = 0  # autres journaux, contreparties, titres : comme à l'import
    sans_echeance: int = 0  # lignes du fichier dont la cellule d'échéance est vide
    a_remplir: list[tuple[int, date]] = field(default_factory=list)  # (écriture, échéance)
    identiques: int = 0  # écriture qui a déjà cette échéance
    differentes: list[str] = field(default_factory=list)  # échéance déjà là, gardée
    non_trouvees: list[str] = field(default_factory=list)


def _decrire(line: EntryLine) -> str:
    jour = f"{line.date_ecriture:%d/%m/%Y}" if line.date_ecriture else "sans date"
    montant = line.debit if line.debit else -(line.credit or Decimal("0"))
    return f"ligne {line.numero} · {jour} · {line.numero_piece or '—'} · {line.libelle} · {montant}"


def _index(lettre: str) -> int:
    try:
        return column_index_from_string(lettre.strip().upper()) - 1
    except ValueError as error:
        raise ConflictError(f"Colonne illisible : « {lettre} ».") from error


def colonne_echeance(entete: tuple, lettre: str | None) -> int:
    """Index de la colonne d'échéance : la lettre donnée, sinon la seule colonne titrée par une date."""
    if lettre:
        return _index(lettre)
    dates = [i for i, cell in enumerate(entete) if isinstance(cell, date | datetime)]
    if len(dates) != 1:
        lettres = ", ".join(get_column_letter(i + 1) for i in dates) or "aucune"
        raise ConflictError(
            f"Colonnes titrées par une date : {lettres}. Indiquez --colonne-echeance."
        )
    return dates[0]


def comparer(lines: list[EntryLine], ecritures: dict[str, AccountingEntry], bilan: Bilan) -> None:
    """Pure : range chaque ligne du fichier (`ecritures` : écritures de la société par empreinte)."""
    for line in lines:
        bilan.lignes += 1
        if line.echeance is None:
            bilan.sans_echeance += 1
            continue
        entry = ecritures.get(line.hash_ligne) if line.hash_ligne else None
        if entry is None:
            bilan.non_trouvees.append(_decrire(line))
        elif entry.echeance is None:
            bilan.a_remplir.append((entry.id, line.echeance))
        elif entry.echeance == line.echeance:
            bilan.identiques += 1
        else:
            bilan.differentes.append(
                f"{_decrire(line)} : {entry.echeance:%d/%m/%Y} gardée "
                f"(fichier {line.echeance:%d/%m/%Y})"
            )


def _ecritures(db: Session, company_id: int, hashes: list[str]) -> dict[str, AccountingEntry]:
    found: dict[str, AccountingEntry] = {}
    for start in range(0, len(hashes), HASH_BATCH):
        query = select(AccountingEntry).where(
            AccountingEntry.company_id == company_id,
            AccountingEntry.hash_ligne.in_(hashes[start : start + HASH_BATCH]),
        )
        found.update((entry.hash_ligne, entry) for entry in db.scalars(query))
    return found


def analyser(
    db: Session,
    *,
    code_societe: str,
    fichier_nom: str,
    content: bytes,
    colonne: str | None = None,
    colonnes: dict[str, str] | None = None,
    feuille: str | None = None,
) -> Bilan:
    """Ne modifie pas la base. `colonnes` : champ de l'import → lettre, quand le modèle de la
    société ne reconnaît pas une colonne du fichier."""
    company = db.scalar(select(Company).filter_by(code=code_societe))
    if company is None:
        raise NotFoundError(f"Société introuvable : {code_societe}.")
    # Même lecture que l'import, puis la colonne d'échéance ajoutée au modèle de la société
    analysis = accounting_import_service.analyse_entries(
        db, company_id=company.id, fichier_nom=fichier_nom, content=content, feuille=feuille
    )
    _, _, rows = import_file.read_sheet(content, analysis.feuille)
    index = colonne_echeance(rows[analysis.ligne_entete - 1], colonne)
    if index >= len(analysis.colonnes):
        raise ConflictError(f"La colonne {get_column_letter(index + 1)} n'existe pas.")
    forcees = {"echeance": index}
    for code, lettre in (colonnes or {}).items():
        if code not in FIELD_LABELS or code == "echeance":
            raise ConflictError(f"Champ inconnu : « {code} » ({', '.join(FIELD_LABELS)}).")
        forcees[code] = _index(lettre)
    mapping = {
        code: i for code, i in analysis.mapping.items() if i not in forcees.values()
    } | forcees
    analysis = accounting_import_service.analyse_entries(
        db,
        company_id=company.id,
        fichier_nom=fichier_nom,
        content=content,
        feuille=analysis.feuille,
        mapping={item.code: mapping.get(item.code) for item in ACCOUNTING_FIELDS},
    )
    if analysis.erreurs_mapping:
        raise ConflictError(" ".join(analysis.erreurs_mapping))

    bilan = Bilan(
        societe=company.nom,
        feuille=analysis.feuille,
        colonne=get_column_letter(index + 1),
        correspondance=[
            f"{FIELD_LABELS[item.code]} : {get_column_letter(analysis.mapping[item.code] + 1)}"
            for item in ACCOUNTING_FIELDS
            if analysis.mapping.get(item.code) is not None
        ],
    )
    bilan.ignorees = analysis.resume.nb_ignorees
    hashes = [line.hash_ligne for line in analysis.lignes if line.hash_ligne]
    comparer(analysis.lignes, _ecritures(db, company.id, hashes), bilan)
    return bilan


def appliquer(
    db: Session,
    *,
    code_societe: str,
    fichier_nom: str,
    content: bytes,
    motif: str,
    email: str,
    colonne: str | None = None,
    colonnes: dict[str, str] | None = None,
    feuille: str | None = None,
) -> Bilan:
    """Remplit les échéances vides en une transaction, un audit par écriture."""
    if not motif.strip():
        raise ConflictError("Indiquez le motif de la reprise.")
    user = auth_repository.get_user_by_email(db, email)
    if user is None or not user.actif:
        raise NotFoundError(f"Utilisateur introuvable ou inactif : {email}.")
    bilan = analyser(
        db,
        code_societe=code_societe,
        fichier_nom=fichier_nom,
        content=content,
        colonne=colonne,
        colonnes=colonnes,
        feuille=feuille,
    )
    for entry_id, echeance in bilan.a_remplir:
        entry = db.get(AccountingEntry, entry_id)
        entry.echeance = echeance
        audit_service.log(
            db,
            user_id=user.id,
            action="completer_echeance",
            entite="accounting_entry",
            entite_id=entry_id,
            avant={"echeance": None},
            apres={"echeance": echeance, "fichier": fichier_nom, "motif": motif.strip()},
        )
    db.commit()
    return bilan
