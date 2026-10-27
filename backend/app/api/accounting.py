"""Import et lecture des écritures comptables Sage / SI (P10)."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, TypeVar

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, ValidationError
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
    SoldeComptableOut,
)
from app.services import (
    accounting_import_service,
    import_file,
    saisie_manuelle_service,
    solde_comptable_service,
    suppression_import_service,
)
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
    lignes_choisies: Annotated[
        str | None, Form(description="JSON [numéros des lignes cochées] : seules celles-ci")
    ] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_import),
) -> ConfirmationComptableOut:
    """Enregistre l'export (même fichier, même correspondance que l'aperçu validé)."""
    kept = _json_field(LignesGardeesIn, "garder_doublons", garder_doublons)
    chosen = _json_field(LignesGardeesIn, "lignes_choisies", lignes_choisies)
    if chosen is not None and (kept is not None or ecarter_erreurs):
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "lignes_choisies"),
                    "msg": "lignes_choisies remplace garder_doublons et ecarter_erreurs.",
                    "input": lignes_choisies,
                }
            ]
        )
    result = accounting_import_service.confirm_entries(
        db,
        company_id=company_id,
        fichier_nom=fichier.filename or "",
        content=_content(fichier),
        mapping=_mapping(mapping),
        feuille=feuille or None,
        garder_doublons=None if kept is None else kept.root,
        ecarter_erreurs=ecarter_erreurs,
        lignes_choisies=None if chosen is None else chosen.root,
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
    # Filtre « Type d'opération » (14/10/2026), mêmes règles que le moteur
    type_operation: Annotated[
        Literal["Chèque", "Effet", "Espèces", "Virement", "Impayé", "Autre"] | None,
        Query(description="Chèque, Effet, Espèces, Virement, Impayé ou Autre"),
    ] = None,
    # 19/10/2026 : false = écritures sans opération bancaire possible, true = avec
    operation_possible: bool | None = None,
    sens: Annotated[
        Literal["Débit", "Crédit"] | None,
        Query(description="Débit ou Crédit de l'écriture, comme dans Sage (19/10/2026)"),
    ] = None,
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
        type_operation=type_operation,
        operation_possible=operation_possible,
        sens=sens,
    )
    return EcrituresPageOut.from_page(result)


class EcritureManuelleIn(BaseModel):
    """Écriture saisie à la main (24/10/2026) ; montants en texte exact (« 1250.50 »)."""

    model_config = ConfigDict(extra="forbid")

    bank_account_id: int
    journal: str = Field(max_length=20)
    date_ecriture: date
    libelle: str = Field(max_length=500)
    debit: Decimal | None = None
    credit: Decimal | None = None
    numero_piece: str | None = Field(default=None, max_length=60)
    reference: str | None = Field(default=None, max_length=60)
    echeance: date | None = None
    montant_devise: Decimal | None = None
    # Compte comptable parmi ceux du compte bancaire ; facultatif s'il n'y en a qu'un (27/10/2026)
    compte: str | None = Field(default=None, max_length=20)
    motif: str = Field(max_length=500)


@router.post("/entries", response_model=EcritureDetailOut, status_code=201)
def ajouter_ecriture(
    body: EcritureManuelleIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_import),
) -> EcritureDetailOut:
    """Ajoute à la main une écriture oubliée par Sage (24/10/2026), avec un motif."""
    saisie = saisie_manuelle_service.EcritureSaisie(**body.model_dump(exclude={"motif"}))
    entry = saisie_manuelle_service.ajouter_ecriture(
        db, saisie, motif=body.motif, acteur_id=user.id, ip=client_ip(request)
    )
    return EcritureDetailOut(
        **EcritureOut.fields_of(entry, entry.bank_account.bank.code),
        fichier_nom=None,
        importe_le=None,
        importe_par=None,
    )


class MotifIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motif: str = Field(max_length=500)


@router.post("/entries/{entry_id}/supprimer", status_code=204)
def supprimer_ecriture(
    entry_id: int,
    body: MotifIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_import),
) -> Response:
    """Supprime une écriture (importée ou manuelle) non rapprochée, avec un motif (24/10/2026)."""
    saisie_manuelle_service.supprimer_ecriture(
        db, entry_id, motif=body.motif, acteur_id=user.id, ip=client_ip(request)
    )
    return Response(status_code=204)


@router.get("/soldes", response_model=list[SoldeComptableOut])
def soldes_comptables(
    company_id: Annotated[int, Query(description="Société")],
    date_solde: Annotated[date | None, Query(alias="date")] = None,
    bank_account_id: int | None = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_read),
) -> list[SoldeComptableOut]:
    """Solde comptable (Sage) de chaque compte à la date choisie (26/10/2026)."""
    items = solde_comptable_service.soldes(db, company_id, date_solde, bank_account_id)
    return [SoldeComptableOut.of(item) for item in items]


class OuvertureIn(BaseModel):
    """Solde comptable d'ouverture ; tout à null pour l'effacer."""

    model_config = ConfigDict(extra="forbid")

    date_ouverture: date | None
    solde: Decimal | None
    solde_devise: Decimal | None = None


@router.put("/soldes/{account_id}/ouverture", response_model=SoldeComptableOut | None)
def set_ouverture(
    account_id: int,
    body: OuvertureIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_import),
) -> SoldeComptableOut | None:
    """Saisit le solde comptable d'ouverture d'un compte, avec sa date (26/10/2026)."""
    account = solde_comptable_service.set_ouverture(
        db,
        account_id,
        date_ouverture=body.date_ouverture,
        solde=body.solde,
        solde_devise=body.solde_devise,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    items = solde_comptable_service.soldes(db, account.company_id, None, account.id)
    return SoldeComptableOut.of(items[0]) if items else None


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


class SuppressionImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motif: str = Field(max_length=500)


class SuppressionImportOut(BaseModel):
    nb_lignes: int
    nb_propositions_retirees: int


@router.post("/imports/{batch_id}/supprimer", response_model=SuppressionImportOut)
def supprimer_import(
    batch_id: int,
    body: SuppressionImportIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_import),
) -> SuppressionImportOut:
    """Supprime toutes les écritures d'un export Sage importé (23/10/2026), sans écriture
    rapprochée ; l'import reste au journal, « Annulé »."""
    result = suppression_import_service.supprimer_import_comptable(
        db,
        batch_id,
        motif=body.motif,
        type_import=accounting_import_service.TYPE_IMPORT,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return SuppressionImportOut(
        nb_lignes=result.nb_lignes, nb_propositions_retirees=result.nb_propositions_retirees
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
