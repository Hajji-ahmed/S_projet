"""Rapprochement bancaire 1→1 (P11) : le moteur propose, un utilisateur autorisé décide."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission
from app.core.db import get_db
from app.core.permissions import PermissionCode
from app.schemas.reconciliation import (
    AmbigueOut,
    AmbiguesOut,
    AnnulationIn,
    CandidatOut,
    CandidatsOut,
    CorrespondanceOut,
    CorrespondancesOut,
    HistoriqueOut,
    ManuelIn,
    OperationOut,
    OperationsPageOut,
    RejetIn,
    RunIn,
    RunOut,
    StatutCorrespondance,
    StatutDecision,
    StatutRapprochement,
    ValidationLotIn,
    ValidationLotOut,
)
from app.services import reconciliation_service
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])

can_view = require_permission(PermissionCode.RECONCILIATION_VIEW)
# Lancer le moteur écrit des propositions : réservé à qui peut aussi les valider
can_validate = require_permission(PermissionCode.RECONCILIATION_VALIDATE)


@router.post("/run", response_model=RunOut)
def run(
    body: RunIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_validate),
) -> RunOut:
    """Propose des correspondances 1→1 pour les opérations de la période (aucune n'est validée)."""
    result = reconciliation_service.run(
        db,
        company_id=body.company_id,
        bank_account_id=body.bank_account_id,
        date_from=body.du,
        date_to=body.au,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return RunOut.from_result(result)


@router.get("/transactions", response_model=OperationsPageOut)
def list_transactions(
    company_id: Annotated[int, Query(description="Société dont on veut les opérations")],
    bank_account_id: int | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    statut: StatutRapprochement | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Libellé ou référence")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    sans_a_verifier: Annotated[
        bool, Query(description="Ne pas lister les opérations « À vérifier » (onglet Propositions)")
    ] = False,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> OperationsPageOut:
    """Volet « Transactions bancaires » : opérations, des plus récentes aux plus anciennes."""
    result = reconciliation_service.list_transactions(
        db,
        company_id,
        bank_account_id=bank_account_id,
        date_from=date_from,
        date_to=date_to,
        statut=statut,
        q=q,
        page=page,
        sans_a_verifier=sans_a_verifier,
    )
    return OperationsPageOut.from_page(result)


@router.get("/ambiguous", response_model=AmbiguesOut)
def list_ambiguous(
    company_id: Annotated[int, Query(description="Société dont on veut les opérations ambiguës")],
    bank_account_id: int | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> AmbiguesOut:
    """Opérations « À vérifier » sans proposition, avec leurs écritures candidates."""
    seuil, views = reconciliation_service.list_ambiguous(
        db,
        company_id,
        bank_account_id=bank_account_id,
        date_from=date_from,
        date_to=date_to,
    )
    return AmbiguesOut(seuil_fort=seuil, ambigues=[AmbigueOut.from_view(v) for v in views])


@router.get("/history", response_model=HistoriqueOut)
def list_history(
    company_id: Annotated[int, Query(description="Société dont on veut l'historique")],
    statut: StatutDecision | None = None,
    bank_account_id: int | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> HistoriqueOut:
    """Historique des décisions (validées, rejetées, annulées), les plus récentes d'abord."""
    result = reconciliation_service.list_history(
        db,
        company_id,
        statut=statut,
        bank_account_id=bank_account_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
    )
    return HistoriqueOut.from_page(result)


@router.get("/proposals", response_model=CorrespondancesOut)
def list_proposals(
    company_id: Annotated[int, Query(description="Société dont on veut les correspondances")],
    statut: StatutCorrespondance = "Proposée",
    bank_account_id: int | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> CorrespondancesOut:
    """Correspondances 1→1, par défaut celles qui attendent une décision."""
    seuil, views = reconciliation_service.list_matches(
        db,
        company_id,
        statut=statut,
        bank_account_id=bank_account_id,
        date_from=date_from,
        date_to=date_to,
    )
    return CorrespondancesOut(
        seuil_fort=seuil, correspondances=[CorrespondanceOut.from_view(v) for v in views]
    )


@router.get("/candidates", response_model=CandidatsOut)
def list_candidates(
    transaction_id: int,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(can_view),
) -> CandidatsOut:
    """Écritures qui pourraient correspondre à une opération, avec leur score détaillé."""
    tx, code, items, seuil_proposition, seuil_fort = reconciliation_service.candidates(
        db, transaction_id
    )
    return CandidatsOut(
        operation=OperationOut.of(tx, code),
        seuil_proposition=seuil_proposition,
        seuil_fort=seuil_fort,
        candidats=[CandidatOut.from_candidate(item) for item in items],
    )


def _out(db: Session, match_id: int) -> CorrespondanceOut:
    return CorrespondanceOut.from_view(reconciliation_service.get_match_view(db, match_id))


@router.get("/matches/{match_id}", response_model=CorrespondanceOut)
def get_match(
    match_id: int, db: Session = Depends(get_db), _user: CurrentUser = Depends(can_view)
) -> CorrespondanceOut:
    """Une correspondance, avec son opération, son écriture et le détail de son score."""
    return _out(db, match_id)


@router.post("/matches/validate-batch", response_model=ValidationLotOut)
def validate_batch(
    body: ValidationLotIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_validate),
) -> ValidationLotOut:
    """Valide en lot les propositions choisies (toutes ou aucune ; montants égaux exigés)."""
    matches = reconciliation_service.validate_batch(
        db, body.ids, acteur_id=user.id, ip=client_ip(request)
    )
    return ValidationLotOut(nb_validees=len(matches))


@router.post("/matches/{match_id}/validate", response_model=CorrespondanceOut)
def validate(
    match_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_validate),
) -> CorrespondanceOut:
    """Confirme une proposition : l'opération et l'écriture deviennent « Rapprochée »."""
    reconciliation_service.validate(db, match_id, acteur_id=user.id, ip=client_ip(request))
    return _out(db, match_id)


@router.post("/matches/{match_id}/reject", response_model=CorrespondanceOut)
def reject(
    match_id: int,
    request: Request,
    body: RejetIn | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_validate),
) -> CorrespondanceOut:
    """Refuse une proposition ; la même paire ne sera plus proposée."""
    reconciliation_service.reject(
        db,
        match_id,
        commentaire=body.commentaire if body else None,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return _out(db, match_id)


@router.post("/matches", response_model=CorrespondanceOut, status_code=201)
def match_manually(
    body: ManuelIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_validate),
) -> CorrespondanceOut:
    """Rapprochement manuel 1→1, validé d'emblée (montants égaux, sens opposé)."""
    match = reconciliation_service.match_manually(
        db,
        transaction_id=body.transaction_id,
        entry_id=body.ecriture_id,
        commentaire=body.commentaire,
        acteur_id=user.id,
        ip=client_ip(request),
    )
    return _out(db, match.id)


@router.delete("/matches/{match_id}", response_model=CorrespondanceOut)
def cancel(
    match_id: int,
    body: AnnulationIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(can_validate),
) -> CorrespondanceOut:
    """Annule un rapprochement validé (motif obligatoire) ; la correspondance reste tracée."""
    reconciliation_service.cancel(
        db, match_id, motif=body.motif, acteur_id=user.id, ip=client_ip(request)
    )
    return _out(db, match_id)
