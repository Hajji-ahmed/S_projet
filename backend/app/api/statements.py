from datetime import date
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_any_permission, require_permission
from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.schemas.statement import (
    AccountStatementOut,
    AnalyseOut,
    ConfirmationOut,
    LignesGardeesIn,
    LignesSoumisesIn,
    MappingIn,
    StatementOut,
    TransactionOut,
    TransactionUpdateIn,
)
from app.services import import_file, import_service
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/statements", tags=["statements"])

can_import = require_permission(PermissionCode.STATEMENTS_IMPORT)
# Mêmes droits que la page Relevés : la Trésorerie qui importe, la Comptabilité qui rapproche
can_view = require_any_permission(
    PermissionCode.STATEMENTS_IMPORT, PermissionCode.RECONCILIATION_VIEW
)

Fichier = Annotated[UploadFile, File(description="Relevé Excel .xlsx, 5 Mo au plus")]
CompteId = Annotated[int, Form(description="Compte du relevé")]
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
    parsed = _json_field(MappingIn, "mapping", raw)
    return None if parsed is None else parsed.root


@router.get("", response_model=list[StatementOut])
def list_statements(
    # Obligatoire : une réponse ne mélange jamais les relevés de deux sociétés
    company_id: Annotated[int, Query(description="Société dont on veut les relevés")],
    bank_account_id: int | None = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> list[StatementOut]:
    """Relevés importés, du plus récent au plus ancien."""
    rows = import_service.list_statements(db, company_id, bank_account_id)
    return [StatementOut.from_row(row) for row in rows]


@router.get("/{statement_id}/transactions", response_model=list[TransactionOut])
def list_transactions(
    statement_id: int,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> list[TransactionOut]:
    """Opérations d'un relevé, au format standard, dans l'ordre chronologique."""
    statement, rows = import_service.statement_transactions(db, statement_id)
    account = statement.bank_account
    return [TransactionOut.from_row(account, row, pointage) for row, pointage in rows]


@router.patch("/transactions/{transaction_id}", response_model=TransactionOut)
def update_transaction(
    transaction_id: int,
    body: TransactionUpdateIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_import),
) -> TransactionOut:
    """Modifie Pointage, Lettrage / Escompte et Commentaire d'une opération importée.

    Dates, libellé et montants restent ceux de la banque : tout autre champ est refusé (422).
    """
    transaction, pointage = import_service.update_transaction(
        db, transaction_id, **body.model_dump(), acteur_id=user.id, ip=client_ip(request)
    )
    return TransactionOut.from_row(transaction.statement.bank_account, transaction, pointage)


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "/{statement_id}/export",
    response_class=Response,
    responses={200: {"content": {XLSX: {}}, "description": "Relevé au format standard"}},
)
def export_statement(
    statement_id: int,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> Response:
    """Un fichier importé, au format standard (11 colonnes du CDC), en classeur Excel."""
    return _xlsx(*import_service.export_statement(db, statement_id))


def _xlsx(filename: str, content: bytes) -> Response:
    return Response(
        content=content,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Relevé continu d'un compte : tous ses imports à la suite ----------------------------------------

DateFrom = Annotated[date | None, Query(alias="from", description="Première date d'opération")]
DateTo = Annotated[date | None, Query(alias="to", description="Dernière date d'opération")]


@router.get("/accounts/{account_id}", response_model=AccountStatementOut)
def account_statement(
    account_id: int,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> AccountStatementOut:
    """Relevé continu du compte : chaque import s'ajoute à la suite (tout l'historique par défaut)."""
    result = import_service.account_statement(db, account_id, date_from, date_to)
    return AccountStatementOut.from_result(result)


@router.get(
    "/accounts/{account_id}/export",
    response_class=Response,
    responses={200: {"content": {XLSX: {}}, "description": "Relevé continu au format standard"}},
)
def export_account_statement(
    account_id: int,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> Response:
    """Relevé continu du compte au format standard, en classeur Excel."""
    return _xlsx(*import_service.export_account_statement(db, account_id, date_from, date_to))


# 5 000 lignes au plus, chacune de quelques centaines d'octets : 20 Mo laissent une large marge
MAX_LINES_BYTES = 20 * 1024 * 1024


def _lines_text(lignes: UploadFile | None) -> str | None:
    """Contenu du fichier JSON des lignes de l'aperçu (lecture bornée)."""
    if lignes is None:
        return None
    raw = lignes.file.read(MAX_LINES_BYTES + 1)
    if len(raw) > MAX_LINES_BYTES:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "lignes"),
                    "msg": "Lignes trop volumineuses.",
                    "input": None,
                }
            ]
        )
    return raw.decode("utf-8", errors="replace")


def _content(fichier: UploadFile) -> bytes:
    # Lecture bornée : un fichier plus gros que la limite est refusé sans être lu en entier
    return fichier.file.read(import_file.MAX_FILE_BYTES + 1)


@router.post("/import/analyse", response_model=AnalyseOut)
def analyse_statement(
    fichier: Fichier,
    bank_account_id: CompteId,
    mapping: MappingForm = None,
    feuille: FeuilleForm = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_import),
) -> AnalyseOut:
    """Analyse un relevé et renvoie son aperçu (colonnes, correspondance, lignes contrôlées).

    Rien n'est enregistré : l'import se confirme ensuite avec `/import/confirm`.
    """
    analysis = import_service.analyse_statement(
        db,
        account_id=bank_account_id,
        fichier_nom=fichier.filename or "",
        content=_content(fichier),
        mapping=_mapping(mapping),
        feuille=feuille or None,
    )
    return AnalyseOut.from_analysis(analysis)


@router.post("/import/confirm", response_model=ConfirmationOut, status_code=201)
def confirm_statement(
    request: Request,
    fichier: Fichier,
    bank_account_id: CompteId,
    mapping: MappingForm = None,
    feuille: FeuilleForm = None,
    garder_doublons: Annotated[
        str | None, Form(description="JSON [numéros de ligne] des doublons internes à garder")
    ] = None,
    ecarter_erreurs: Annotated[
        bool, Form(description="Importer malgré des lignes en erreur, en les écartant")
    ] = False,
    lignes: Annotated[
        UploadFile | None,
        File(
            description="Fichier JSON : lignes du fichier à importer, avec leurs corrections "
            "(aperçu). Envoyé comme fichier : un champ de formulaire est limité à 1 Mo."
        ),
    ] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_import),
) -> ConfirmationOut:
    """Enregistre le relevé (même fichier, même correspondance que l'aperçu validé).

    Le fichier est analysé à nouveau. Avec `lignes`, ce sont les lignes de l'aperçu, corrigées et
    revérifiées, qui sont enregistrées ; sinon, le fichier tel qu'il est analysé.
    """
    kept = _json_field(LignesGardeesIn, "garder_doublons", garder_doublons)
    submitted = _json_field(LignesSoumisesIn, "lignes", _lines_text(lignes))
    if submitted is not None and (kept is not None or ecarter_erreurs):
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "lignes"),
                    "msg": "« lignes » remplace « garder_doublons » et « ecarter_erreurs ».",
                    "input": None,
                }
            ]
        )
    result = import_service.confirm_statement(
        db,
        account_id=bank_account_id,
        fichier_nom=fichier.filename or "",
        content=_content(fichier),
        mapping=_mapping(mapping),
        feuille=feuille or None,
        garder_doublons=None if kept is None else kept.root,
        ecarter_erreurs=ecarter_erreurs,
        lignes=None if submitted is None else [line.model_dump() for line in submitted.root],
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return ConfirmationOut.from_import(result)
