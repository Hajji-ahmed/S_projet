"""Comptabilisation des frais bancaires par SIMTIS (13/10/2026) : droits de timbre et commissions.

Préparer (calculé), valider (écriture créée et rapprochée d'emblée), exporter pour Sage.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission
from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.schemas.frais import (
    AExporterOut,
    AutreFraisOut,
    CompteFraisOut,
    EcarterIn,
    EcritureFraisOut,
    FraisInclusOut,
    JourEcarteOut,
    ManuelleIn,
    NombreOut,
    PropositionTimbresOut,
    ReproposerIn,
    SuppressionIn,
    TimbresOut,
    ValidationTimbresIn,
    ValidationTimbresOut,
)
from app.services import frais_service
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/frais", tags=["frais"])

can_view = require_permission(PermissionCode.RECONCILIATION_VIEW)
can_prepare = require_permission(PermissionCode.ACCOUNTING_PREPARE)
CSV = "text/csv; charset=windows-1252"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

DateFrom = Annotated[date | None, Query(alias="from")]
DateTo = Annotated[date | None, Query(alias="to")]


@router.delete("/ecritures/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def supprimer(
    entry_id: int,
    body: SuppressionIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_prepare),
) -> None:
    """Supprime une écriture SIMTIS pas encore exportée ; ses opérations redeviennent à
    comptabiliser."""
    frais_service.supprimer(
        db, entry_id, motif=body.motif, acteur_id=user.id, ip=client_ip(request)
    )


@router.get(
    "/justificatif",
    response_class=Response,
    responses={
        200: {"content": {XLSX: {}}, "description": "Frais à justifier auprès de la banque"}
    },
)
def justificatif(
    request: Request,
    company_id: int,
    bank_account_id: int | None = None,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_view),
) -> Response:
    """Excel des frais de plus de 200 DH (hors droits de timbre) à envoyer à la banque
    (19/10/2026)."""
    nom, content, _ = frais_service.justificatif(
        db,
        company_id,
        bank_account_id=bank_account_id,
        date_from=date_from,
        date_to=date_to,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return Response(
        content=content,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )


@router.get("/a-exporter", response_model=list[AExporterOut])
def a_exporter(
    company_id: int,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> list[AExporterOut]:
    """Écritures de frais pas encore exportées, par banque et par mois (09/11/2026)."""
    return [AExporterOut.of(item) for item in frais_service.a_exporter(db, company_id)]


@router.get(
    "/export",
    response_class=Response,
    responses={200: {"content": {CSV: {}}, "description": "Écritures à intégrer dans Sage"}},
)
def exporter(
    request: Request,
    company_id: int,
    bank_id: int,
    mois: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")],
    premiere_piece: Annotated[str, Query(max_length=20)],
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_prepare),
) -> Response:
    """UN fichier CSV pour Sage par banque et par mois (09/11/2026) : les écritures pas encore
    exportées, numérotées à partir de `premiere_piece` (« BP2610001 ») ; chacune ne s'exporte
    qu'une fois."""
    annee, numero_mois = (int(part) for part in mois.split("-"))
    nom, content, _ = frais_service.exporter(
        db,
        company_id,
        bank_id=bank_id,
        annee=annee,
        mois=numero_mois,
        premiere=premiere_piece,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return Response(
        content=content,
        media_type=CSV,
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )


@router.get("/comptes", response_model=list[CompteFraisOut])
def comptes(_user: CurrentUser = Depends(can_view)) -> list[CompteFraisOut]:
    """Comptes de charge des frais bancaires (05/11/2026), à choisir pour une écriture manuelle ;
    `banque` : compte réservé à cette banque."""
    return [
        CompteFraisOut(numero=numero, intitule=intitule, banque=banque)
        for numero, intitule, banque in frais_service.COMPTES_FRAIS
    ]


@router.get("", response_model=TimbresOut)
def lire(
    company_id: int,
    bank_account_id: int | None = None,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> TimbresOut:
    """Un seul tableau (13/10/2026) : écritures à passer, droits de timbre et commissions
    (calculées, une par jour, par compte et par famille), et écritures déjà comptabilisées par
    SIMTIS."""
    vue = frais_service.tableau(
        db, company_id, bank_account_id=bank_account_id, date_from=date_from, date_to=date_to
    )
    return TimbresOut(
        propositions=[PropositionTimbresOut.of(item) for item in vue.propositions],
        total_propositions=sum((item.jour.total for item in vue.propositions), Decimal("0.00")),
        ecritures=[EcritureFraisOut.of(item) for item in vue.ecritures],
        autres_frais=[AutreFraisOut.of(item) for item in vue.autres],
        frais_inclus=[FraisInclusOut.of(item) for item in vue.inclus],
        ecartes=[JourEcarteOut.of(item) for item in vue.ecartes],
    )


@router.post("/valider", response_model=ValidationTimbresOut)
def valider(
    body: ValidationTimbresIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_prepare),
) -> ValidationTimbresOut:
    """Comptabilise les jours choisis, toutes familles (tous ou aucun) : écritures créées et
    rapprochées d'emblée."""
    entries = frais_service.valider(
        db,
        body.company_id,
        [
            (
                frais_service.famille(jour.famille),
                jour.bank_account_id,
                jour.date,
                jour.transaction_id,
            )
            for jour in body.jours
        ],
        acteur_id=user.id,
        ip=client_ip(request),
        modifications={
            (
                jour.famille,
                jour.bank_account_id,
                jour.date,
                jour.transaction_id,
            ): frais_service.Modification(
                libelle=jour.libelle,
                date_ecriture=jour.date_ecriture,
                lignes=None
                if jour.lignes is None
                else tuple(
                    frais_service.LigneSaisie(
                        ligne.compte, ligne.libelle, ligne.montant, ligne.sens
                    )
                    for ligne in jour.lignes
                ),
            )
            for jour in body.jours
            if jour.libelle or jour.date_ecriture or jour.lignes is not None
        },
    )
    return ValidationTimbresOut(
        nb_ecritures=len(entries), codes=frais_service.codes_rapprochement(db, entries)
    )


@router.post("/ecarter", response_model=NombreOut)
def ecarter(
    body: EcarterIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_prepare),
) -> NombreOut:
    """Écarte des frais proposés (13/11/2026) ou des journées, tous ou aucun : ils passent à
    la main."""
    nb = frais_service.ecarter(
        db,
        body.company_id,
        [
            (frais_service.famille(j.famille), j.bank_account_id, j.date, j.transaction_id)
            for j in body.jours
        ],
        motif=body.motif,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return NombreOut(nb=nb)


@router.post("/reproposer", response_model=NombreOut)
def reproposer(
    body: ReproposerIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_prepare),
) -> NombreOut:
    """Annule l'écartement de journées : SIMTIS les propose de nouveau."""
    nb = frais_service.reproposer(
        db,
        body.company_id,
        [
            (frais_service.famille(j.famille), j.bank_account_id, j.date, j.transaction_id)
            for j in body.jours
        ],
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return NombreOut(nb=nb)


@router.post("/manuelle", response_model=ValidationTimbresOut)
def comptabiliser_manuellement(
    body: ManuelleIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_prepare),
) -> ValidationTimbresOut:
    """Écriture saisie à la main pour des frais d'un même compte, TVA séparée ou non : créée et
    rapprochée d'emblée."""
    entry = frais_service.comptabiliser_manuellement(
        db,
        body.company_id,
        transaction_ids=body.transaction_ids,
        libelle=body.libelle,
        date_ecriture=body.date_ecriture,
        taux_tva=body.taux_tva,
        montant_tva=body.montant_tva,
        compte=body.compte,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return ValidationTimbresOut(
        nb_ecritures=1, codes=frais_service.codes_rapprochement(db, [entry])
    )
