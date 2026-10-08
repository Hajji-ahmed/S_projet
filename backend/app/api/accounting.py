"""Import et lecture des écritures comptables Sage / SI (P10)."""

from datetime import date
from typing import Annotated, Literal, TypeVar

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_any_permission, require_permission
from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.schemas.accounting import (
    AnalyseComptableOut,
    ConfirmationComptableOut,
    EcritureDetailOut,
    EcritureOut,
    EcrituresPageOut,
    ImportComptableOut,
    LignesGardeesIn,
    MappingComptableIn,
)
from app.services import accounting_import_service, import_file
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/accounting", tags=["accounting"])

can_import = require_permission(PermissionCode.ACCOUNTING_IMPORT)
# Lecture : le métier qui importe (Comptable) et ceux qui consultent le rapprochement
can_read = require_any_permission(
    PermissionCode.ACCOUNTING_IMPORT, PermissionCode.RECONCILIATION_VIEW
)

Fichier = Annotated[UploadFile, File(description="Export Sage / SI .xlsx ou .xls, 20 Mo au plus")]
SocieteId = Annotated[int, Form(description="Société de l'export")]
MappingForm = Annotated[
    str | None, Form(description="JSON {champ: index de colonne} ; absent = détection")
]
FeuilleForm = Annotated[str | None, Form(description="Feuille à lire, la première par défaut")]
ModelT = TypeVar("ModelT", bound=BaseModel)


def _json_field(model: type[ModelT], name: str, raw: str | None) -> ModelT | None:
    """Champ de formulaire contenant du JSON ; une valeur invalide donne une erreur 422."""
    if raw is None or not raw.strip():
        return None
    try:
        return model.model_validate_json(raw)
    except ValidationError as error:
        raise RequestValidationError(
            [{**item, "loc": ("body", name, *item["loc"])} for item in error.errors()]
        ) from error


def _mapping(raw: str | None) -> dict[str, int | None] | None:
    parsed = _json_field(MappingComptableIn, "mapping", raw)
    return None if parsed is None else parsed.root


def _content(fichier: UploadFile) -> bytes:
    # Lecture bornée : un fichier plus gros que la limite est refusé sans être lu en entier
    return fichier.file.read(import_file.MAX_FILE_BYTES + 1)


@router.post("/import/analyse", response_model=AnalyseComptableOut)
def analyse_entries(
    fichier: Fichier,
    company_id: SocieteId,
    mapping: MappingForm = None,
    feuille: FeuilleForm = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_import),
) -> AnalyseComptableOut:
    """Analyse un export Sage et renvoie son aperçu. Rien n'est enregistré."""
    analysis = accounting_import_service.analyse_entries(
        db,
        company_id=company_id,
        fichier_nom=fichier.filename or "",
        content=_content(fichier),
        mapping=_mapping(mapping),
        feuille=feuille or None,
    )
    return AnalyseComptableOut.from_analysis(analysis)


@router.post("/import/confirm", response_model=ConfirmationComptableOut, status_code=201)
def confirm_entries(
    request: Request,
    fichier: Fichier,
    company_id: SocieteId,
    mapping: MappingForm = None,
    feuille: FeuilleForm = None,
    garder_doublons: Annotated[
        str | None, Form(description="JSON [numéros de ligne] des doublons internes à garder")
    ] = None,
    ecarter_erreurs: Annotated[
        bool, Form(description="Importer malgré des lignes en erreur, en les écartant")
    ] = False,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_import),
) -> ConfirmationComptableOut:
    """Enregistre l'export (même fichier, même correspondance que l'aperçu validé)."""
    kept = _json_field(LignesGardeesIn, "garder_doublons", garder_doublons)
    result = accounting_import_service.confirm_entries(
        db,
        company_id=company_id,
        fichier_nom=fichier.filename or "",
        content=_content(fichier),
        mapping=_mapping(mapping),
        feuille=feuille or None,
        garder_doublons=None if kept is None else kept.root,
        ecarter_erreurs=ecarter_erreurs,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return ConfirmationComptableOut.from_import(result)


# --- Lecture ---------------------------------------------------------------------------------------


@router.get("/entries", response_model=EcrituresPageOut)
def list_entries(
    # Obligatoire : une réponse ne mélange jamais les écritures de deux sociétés
    company_id: Annotated[int, Query(description="Société dont on veut les écritures")],
    bank_account_id: int | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    statut: Literal["Non rapprochée", "À vérifier", "Rapprochée", "Écart"] | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Libellé, pièce, tiers")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_read),
) -> EcrituresPageOut:
    """Écritures importées, de la plus récente à la plus ancienne, 50 par page."""
    result = accounting_import_service.list_entries(
        db,
        company_id,
        bank_account_id=bank_account_id,
        date_from=date_from,
        date_to=date_to,
        statut=statut,
        q=q,
        page=page,
    )
    return EcrituresPageOut.from_page(result)


@router.get("/entries/{entry_id}", response_model=EcritureDetailOut)
def get_entry(
    entry_id: int, db: Session = Depends(get_db), _user: CurrentUser = Depends(can_read)
) -> EcritureDetailOut:
    """Une écriture, avec le fichier dont elle vient."""
    entry, code, batch, author = accounting_import_service.get_entry(db, entry_id)
    return EcritureDetailOut(
        **EcritureOut.fields_of(entry, code),
        fichier_nom=batch.fichier_nom if batch else None,
        importe_le=batch.created_at if batch else None,
        importe_par=author,
    )


@router.get("/imports", response_model=list[ImportComptableOut])
def list_imports(
    company_id: Annotated[int, Query(description="Société dont on veut les imports")],
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_read),
) -> list[ImportComptableOut]:
    """Journal des exports Sage importés, du plus récent au plus ancien."""
    return [
        ImportComptableOut.from_row(row)
        for row in accounting_import_service.list_imports(db, company_id)
    ]
