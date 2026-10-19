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
    AutreFraisOut,
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
    "/export",
    response_class=Response,
    responses={200: {"content": {CSV: {}}, "description": "Écritures à intégrer dans Sage"}},
)
def exporter(
    request: Request,
    company_id: int,
    bank_account_id: int | None = None,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    inclure_exportees: bool = False,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_prepare),
) -> Response:
    """UN fichier CSV pour Sage (16/10/2026), toutes familles de frais ; les écritures exportées
    ne se suppriment plus dans SIMTIS."""
    nom, content, _ = frais_service.exporter(
        db,
        company_id,
        bank_account_id=bank_account_id,
        date_from=date_from,
        date_to=date_to,
        inclure_exportees=inclure_exportees,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return Response(
        content=content,
        media_type=CSV,
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )


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
            (frais_service.famille(jour.famille), jour.bank_account_id, jour.date)
            for jour in body.jours
        ],
        acteur_id=user.id,
        ip=client_ip(request),
        modifications={
            (jour.famille, jour.bank_account_id, jour.date): frais_service.Modification(
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
        nb_ecritures=len(entries), codes=[entry.numero_piece for entry in entries]
    )


@router.post("/ecarter", response_model=NombreOut)
def ecarter(
    body: EcarterIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_prepare),
) -> NombreOut:
    """Écarte des journées proposées (toutes ou aucune) : leurs frais passent à la main."""
    nb = frais_service.ecarter(
        db,
        body.company_id,
        [(frais_service.famille(j.famille), j.bank_account_id, j.date) for j in body.jours],
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
        [(frais_service.famille(j.famille), j.bank_account_id, j.date) for j in body.jours],
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
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return ValidationTimbresOut(nb_ecritures=1, codes=[entry.numero_piece])
