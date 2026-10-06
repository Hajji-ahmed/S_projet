"""Rapprochement bancaire 1→1 (P11). Montants et scores en texte exact."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import BankTransaction, ReconciliationMatch
from app.schemas.accounting import EcritureOut
from app.services.reconciliation_scoring import CRITERES, LIBELLES_CRITERES
from app.services.reconciliation_service import (
    Candidate,
    HistoryPage,
    MatchView,
    RunResult,
    TransactionsPage,
)

StatutRapprochement = Literal["Non rapprochée", "À vérifier", "Rapprochée", "Écart"]
StatutCorrespondance = Literal["Proposée", "Validée", "Rejetée", "Annulée"]
Commentaire = Annotated[str, Field(max_length=500)]


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: int
    bank_account_id: int | None = Field(None, description="Absent : tous les comptes de la société")
    du: date
    au: date


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nb_operations: int = Field(description="Opérations libres comparées")
    nb_ecritures: int = Field(description="Écritures libres comparées")
    nb_propositions: int
    nb_fortes: int
    nb_operations_ambigues: int
    nb_ecritures_ambigues: int

    @classmethod
    def from_result(cls, result: RunResult) -> "RunOut":
        return cls.model_validate(result)


class CritereOut(BaseModel):
    code: str
    libelle: str
    points: Decimal


def criteres(detail: dict[str, object] | None) -> list[CritereOut]:
    """Détail du score dans l'ordre d'affichage ; un critère absent vaut 0."""
    detail = detail or {}
    return [
        CritereOut(
            code=code,
            libelle=LIBELLES_CRITERES[code],
            points=Decimal(str(detail.get(code, "0.00"))),
        )
        for code in CRITERES
    ]


class CorrespondanceResumeOut(BaseModel):
    """Correspondance active d'une opération, telle que l'affiche le volet de gauche."""

    id: int
    statut: StatutCorrespondance
    origine: Literal["Automatique", "Manuelle"]
    score: Decimal | None
    ecriture_id: int | None


class OperationOut(BaseModel):
    id: int
    bank_account_id: int
    bank_code: str
    date_operation: date
    date_valeur: date | None
    libelle: str
    reference: str | None
    debit: Decimal
    credit: Decimal
    montant: Decimal
    statut: StatutRapprochement
    correspondance: CorrespondanceResumeOut | None = None
    ecart_id: int | None = Field(None, description="Écart ouvert de l'opération (P12)")

    @classmethod
    def of(
        cls,
        tx: BankTransaction,
        bank_code: str,
        match: ReconciliationMatch | None = None,
        ecart_id: int | None = None,
    ) -> "OperationOut":
        resume = None
        if match is not None:
            resume = CorrespondanceResumeOut(
                id=match.id,
                statut=match.statut,
                origine=match.origine,
                score=match.score,
                ecriture_id=next(
                    (i.accounting_entry_id for i in match.items if i.accounting_entry_id), None
                ),
            )
        return cls(
            id=tx.id,
            bank_account_id=tx.bank_account_id,
            bank_code=bank_code,
            date_operation=tx.date_operation,
            date_valeur=tx.date_valeur,
            libelle=tx.libelle,
            reference=tx.reference,
            debit=tx.debit,
            credit=tx.credit,
            montant=tx.montant,
            statut=tx.statut,
            correspondance=resume,
            ecart_id=ecart_id,
        )


class OperationsPageOut(BaseModel):
    """Une page de 50 opérations ; `total` et `par_statut` portent sur tout le filtre."""

    total: int
    page: int
    taille: int
    par_statut: dict[str, int]
    operations: list[OperationOut]

    @classmethod
    def from_page(cls, result: TransactionsPage) -> "OperationsPageOut":
        return cls(
            total=result.total,
            page=result.page,
            taille=result.taille,
            par_statut={
                statut: result.par_statut.get(statut, 0) for statut in StatutRapprochement.__args__
            },
            operations=[
                OperationOut.of(tx, code, match, result.ecarts.get(tx.id))
                for tx, code, match in result.operations
            ],
        )


class CorrespondanceOut(BaseModel):
    id: int
    type: str
    statut: StatutCorrespondance
    origine: Literal["Automatique", "Manuelle"]
    score: Decimal | None
    forte: bool = Field(description="Score au moins égal au seuil de forte correspondance")
    criteres: list[CritereOut]
    commentaire: str | None
    valide_par: str | None
    valide_le: datetime | None
    decide_par: str | None = Field(description="Auteur de la dernière décision (historique)")
    decide_le: datetime | None
    created_at: datetime
    operation: OperationOut
    ecriture: EcritureOut

    @classmethod
    def from_view(cls, view: MatchView) -> "CorrespondanceOut":
        match = view.match
        return cls(
            id=match.id,
            type=match.type,
            statut=match.statut,
            origine=match.origine,
            score=match.score,
            forte=view.forte,
            criteres=criteres(match.detail_score),
            commentaire=match.commentaire,
            valide_par=view.valide_par,
            valide_le=match.valide_le,
            decide_par=view.decide_par,
            decide_le=match.decide_le,
            created_at=match.created_at,
            operation=OperationOut.of(view.transaction, view.bank_code),
            ecriture=EcritureOut(**EcritureOut.fields_of(view.entry, view.entry_bank_code)),
        )


class CorrespondancesOut(BaseModel):
    seuil_fort: Decimal
    correspondances: list[CorrespondanceOut]


StatutDecision = Literal["Validée", "Rejetée", "Annulée"]


class HistoriqueOut(BaseModel):
    """Une page de 50 décisions ; `par_statut` porte sur tout le filtre, hors statut."""

    total: int
    page: int
    taille: int
    par_statut: dict[str, int]
    decisions: list[CorrespondanceOut]

    @classmethod
    def from_page(cls, result: HistoryPage) -> "HistoriqueOut":
        return cls(
            total=result.total,
            page=result.page,
            taille=result.taille,
            par_statut={
                statut: result.par_statut.get(statut, 0) for statut in StatutDecision.__args__
            },
            decisions=[CorrespondanceOut.from_view(view) for view in result.decisions],
        )


class CandidatOut(BaseModel):
    ecriture: EcritureOut
    score: Decimal
    criteres: list[CritereOut]
    rejetee: bool = Field(description="Paire déjà rejetée par un utilisateur")
    proposee_ailleurs: bool = Field(
        description="Proposée pour une autre opération : la choisir rejette cette proposition"
    )

    @classmethod
    def from_candidate(cls, item: Candidate) -> "CandidatOut":
        return cls(
            ecriture=EcritureOut(**EcritureOut.fields_of(item.entry, item.bank_code)),
            score=item.score.total,
            criteres=criteres({k: str(v) for k, v in item.score.detail.items()}),
            rejetee=item.rejetee,
            proposee_ailleurs=item.proposee_ailleurs,
        )


class CandidatsOut(BaseModel):
    operation: OperationOut
    seuil_proposition: Decimal
    seuil_fort: Decimal
    candidats: list[CandidatOut]


class RejetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commentaire: Commentaire | None = None


class AnnulationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motif: Annotated[str, Field(min_length=1, max_length=500)]


class ManuelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: int
    ecriture_id: int
    commentaire: Commentaire | None = None


class ValidationLotIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: Annotated[list[int], Field(min_length=1, max_length=500)]


class ValidationLotOut(BaseModel):
    nb_validees: int
