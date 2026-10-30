"""Rapprochement bancaire 1→1 (P11). Montants et scores en texte exact."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import BankTransaction, ReconciliationMatch
from app.schemas.accounting import EcritureOut
from app.services.reconciliation_scoring import CRITERES, LIBELLES_CRITERES
from app.services.reconciliation_service import (
    AmbiguousEntryView,
    AmbiguousView,
    Candidate,
    CandidateOperation,
    HistoryPage,
    MatchView,
    RunResult,
    TransactionsPage,
    montant_rapprochement,
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
    nb_groupes: int = Field(0, description="Groupes N → 1 proposés (12/10/2026)")

    @classmethod
    def from_result(cls, result: RunResult) -> "RunOut":
        return cls.model_validate(result)


class CritereOut(BaseModel):
    code: str
    libelle: str
    points: Decimal


def criteres(detail: dict[str, object] | None, actifs: tuple[str, ...]) -> list[CritereOut]:
    """Détail du score dans l'ordre d'affichage : les critères de la grille actuelle, plus ceux qui
    ont rapporté des points (score calculé avec une grille précédente) ; un absent vaut 0."""
    detail = detail or {}
    points = {code: Decimal(str(detail.get(code, "0.00"))) for code in CRITERES}
    return [
        CritereOut(code=code, libelle=LIBELLES_CRITERES[code], points=points[code])
        for code in CRITERES
        if code in actifs or points[code] > 0
    ]


class CorrespondanceResumeOut(BaseModel):
    """Correspondance active d'une opération, telle que l'affiche le volet de gauche."""

    id: int
    statut: StatutCorrespondance
    origine: Literal["Automatique", "Manuelle", "Frais", "Reprise"]
    score: Decimal | None
    ecriture_id: int | None
    # Code du rapprochement validé (« BP-26-000123 », 13/10/2026)
    code: str | None = None


class OperationOut(BaseModel):
    id: int
    bank_account_id: int
    bank_code: str
    # Devise du compte (EUR, USD…) : le montant est dans cette devise (14/10/2026)
    devise: str = "MAD"
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
    # Libellé terminé par « (*) » : en cours, jamais rapprochée (20/10/2026)
    en_cours: bool = False

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
                code=match.code,
            )
        return cls(
            id=tx.id,
            bank_account_id=tx.bank_account_id,
            bank_code=bank_code,
            devise=tx.bank_account.devise,
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
            en_cours=tx.en_cours,
        )


class OperationsPageOut(BaseModel):
    """Une page de 50 opérations ; `total` et `par_statut` portent sur tout le filtre."""

    total: int
    page: int
    taille: int
    par_statut: dict[str, int]
    # Frais bancaires non rapprochés (hors « Non rapprochée ») : à passer dans Sage (12/10/2026)
    a_comptabiliser: int = 0
    total_a_comptabiliser: Decimal = Decimal(0)
    # Opérations en cours du filtre, hors `par_statut` (20/10/2026)
    en_cours: int = 0
    operations: list[OperationOut]

    @classmethod
    def from_page(cls, result: TransactionsPage) -> "OperationsPageOut":
        return cls(
            total=result.total,
            page=result.page,
            taille=result.taille,
            a_comptabiliser=result.a_comptabiliser,
            total_a_comptabiliser=result.total_a_comptabiliser,
            en_cours=result.en_cours,
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
    # Code donné à la validation (« BP-26-000123 », 13/10/2026) ; None tant que proposée
    code: str | None = None
    type: str
    statut: StatutCorrespondance
    origine: Literal["Automatique", "Manuelle", "Frais", "Reprise"]
    score: Decimal | None
    forte: bool = Field(description="Score au moins égal au seuil de forte correspondance")
    score_second: Decimal | None = Field(
        None, description="Score du meilleur autre candidat au moment de la proposition"
    )
    concurrente_proche: bool = Field(
        False,
        description="Un autre candidat à moins de l'écart d'ambiguïté : jamais coché d'office",
    )
    # Recherche élargie (20/10/2026) : écart entre les dates ; jamais cochée d'office
    elargie: bool = False
    ecart_jours: int | None = None
    criteres: list[CritereOut]
    commentaire: str | None
    valide_par: str | None
    valide_le: datetime | None
    decide_par: str | None = Field(description="Auteur de la dernière décision (historique)")
    decide_le: datetime | None
    created_at: datetime
    # Opération principale (la seule en 1 → 1, la plus grosse d'un groupe N → 1)
    operation: OperationOut
    # Groupe N → 1 (12/10/2026) : toutes les opérations, leur total, l'écart et l'explication
    operations: list[OperationOut] = Field(default_factory=list)
    total_operations: Decimal = Decimal("0")
    ecart: Decimal = Field(
        Decimal("0"), description="Total des opérations + montant de l'écriture (0 = équilibré)"
    )
    explication: str | None = None
    ecriture: EcritureOut
    # Plusieurs écritures (1 → N, N → N, P13 du 15/10/2026) : toutes, la plus grosse en tête
    ecritures: list[EcritureOut] = Field(default_factory=list)
    total_ecritures: Decimal = Decimal("0")
    # Nombre de toutes les lignes : `operations` et `ecritures` en gardent au plus 20 (27/10/2026)
    nb_operations: int = 1
    nb_ecritures: int = 1

    @classmethod
    def from_view(cls, view: MatchView) -> "CorrespondanceOut":
        match = view.match
        lignes = view.transactions or [(view.transaction, view.bank_code)]
        total = view.total_operations
        if total is None:
            total = sum((tx.montant for tx, _ in lignes), Decimal("0"))
        ecritures = view.entries or [(view.entry, view.entry_bank_code)]
        total_sage = view.total_ecritures
        if total_sage is None:
            total_sage = sum((montant_rapprochement(e) for e, _ in ecritures), Decimal("0"))
        return cls(
            nb_operations=max(view.nb_operations, len(lignes)),
            nb_ecritures=max(view.nb_ecritures, len(ecritures)),
            code=match.code,
            operations=[OperationOut.of(tx, code) for tx, code in lignes],
            total_operations=total,
            ecritures=[EcritureOut(**EcritureOut.fields_of(e, code)) for e, code in ecritures],
            total_ecritures=total_sage,
            ecart=total + total_sage,
            explication=(match.detail_score or {}).get("explication"),
            id=match.id,
            type=match.type,
            statut=match.statut,
            origine=match.origine,
            score=match.score,
            forte=view.forte,
            score_second=view.score_second,
            concurrente_proche=view.concurrente_proche,
            elargie=view.elargie,
            ecart_jours=view.ecart_jours,
            criteres=criteres(match.detail_score, view.actifs),
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


class ConcurrenteOut(BaseModel):
    """Autre opération que l'écriture pourrait recevoir au même score (30/10/2026)."""

    id: int
    date_operation: date
    libelle: str
    score: Decimal


class CandidatOut(BaseModel):
    ecriture: EcritureOut
    score: Decimal
    criteres: list[CritereOut]
    rejetee: bool = Field(description="Paire déjà rejetée par un utilisateur")
    proposee_ailleurs: bool = Field(
        description="Proposée pour une autre opération : la choisir rejette cette proposition"
    )
    concurrentes: list[ConcurrenteOut] = Field(default_factory=list)

    @classmethod
    def from_candidate(cls, item: Candidate) -> "CandidatOut":
        return cls(
            ecriture=EcritureOut(**EcritureOut.fields_of(item.entry, item.bank_code)),
            score=item.score.total,
            criteres=criteres({k: str(v) for k, v in item.score.detail.items()}, item.actifs),
            rejetee=item.rejetee,
            proposee_ailleurs=item.proposee_ailleurs,
        )


class CandidatsOut(BaseModel):
    operation: OperationOut
    seuil_proposition: Decimal
    seuil_fort: Decimal
    candidats: list[CandidatOut]


class AmbigueOut(BaseModel):
    """Opération ambiguë : plusieurs écritures aussi proches, aucune proposée."""

    operation: OperationOut
    candidats: list[CandidatOut]

    @classmethod
    def from_view(cls, view: AmbiguousView) -> "AmbigueOut":
        return cls(
            operation=OperationOut.of(view.transaction, view.bank_code),
            candidats=[
                CandidatOut.from_candidate(item).model_copy(
                    update={
                        "concurrentes": [
                            ConcurrenteOut(
                                id=c.transaction.id,
                                date_operation=c.transaction.date_operation,
                                libelle=c.transaction.libelle,
                                score=c.score.total,
                            )
                            for c in view.concurrentes.get(item.entry.id, [])
                        ]
                    }
                )
                for item in view.candidats
            ],
        )


class AmbiguesOut(BaseModel):
    seuil_fort: Decimal
    # Nombre d'opérations ambiguës sur tout le filtre ; `ambigues` n'en donne qu'une page
    total: int
    page: int
    taille: int
    ambigues: list[AmbigueOut]


class CandidatOperationOut(BaseModel):
    operation: OperationOut
    score: Decimal
    criteres: list[CritereOut]
    rejetee: bool
    proposee_ailleurs: bool

    @classmethod
    def from_candidate(cls, item: CandidateOperation) -> "CandidatOperationOut":
        return cls(
            operation=OperationOut.of(item.transaction, item.bank_code),
            score=item.score.total,
            criteres=criteres({k: str(v) for k, v in item.score.detail.items()}, item.actifs),
            rejetee=item.rejetee,
            proposee_ailleurs=item.proposee_ailleurs,
        )


class EcritureAmbigueOut(BaseModel):
    """Écriture ambiguë (15/10/2026) : plusieurs opérations aussi proches, aucune proposée."""

    ecriture: EcritureOut
    candidats: list[CandidatOperationOut]

    @classmethod
    def from_view(cls, view: AmbiguousEntryView) -> "EcritureAmbigueOut":
        return cls(
            ecriture=EcritureOut(**EcritureOut.fields_of(view.entry, view.bank_code)),
            candidats=[CandidatOperationOut.from_candidate(item) for item in view.candidats],
        )


class EcrituresAmbiguesOut(BaseModel):
    total: int
    page: int
    taille: int
    ecritures: list[EcritureAmbigueOut]


class AucuneOperationOut(BaseModel):
    operations_ecartees: list[int]


class AucuneEcritureOut(BaseModel):
    """Écritures écartées par « Aucune écriture ne correspond » (15/10/2026)."""

    ecritures_ecartees: list[int]


class RejetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commentaire: Commentaire | None = None


class AnnulationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motif: Annotated[str, Field(min_length=1, max_length=500)]


class ManuelIn(BaseModel):
    """Rapprochement manuel : une opération et une écriture (`transaction_id`, `ecriture_id`), ou
    des listes (`transaction_ids`, `ecriture_ids`, P13 du 15/10/2026) ; pas les deux formes."""

    model_config = ConfigDict(extra="forbid")

    transaction_id: int | None = None
    ecriture_id: int | None = None
    transaction_ids: list[int] | None = None
    ecriture_ids: list[int] | None = None
    commentaire: Commentaire | None = None
    # Rapprochement depuis une carte ambiguë (16/10/2026) : le moteur ne refait que les lignes
    # qui étaient en concurrence avec celles-ci
    relance_ciblee: bool = False

    @model_validator(mode="after")
    def _une_seule_forme(self) -> "ManuelIn":
        simple = self.transaction_id is not None or self.ecriture_id is not None
        listes = self.transaction_ids is not None or self.ecriture_ids is not None
        if simple == listes:
            raise ValueError("Envoyez transaction_id et ecriture_id, ou les deux listes.")
        if simple and (self.transaction_id is None or self.ecriture_id is None):
            raise ValueError("transaction_id et ecriture_id vont ensemble.")
        return self

    def operations(self) -> list[int]:
        return (
            [self.transaction_id] if self.transaction_id is not None else self.transaction_ids or []
        )

    def ecritures(self) -> list[int]:
        return [self.ecriture_id] if self.ecriture_id is not None else self.ecriture_ids or []


# Propositions au plus par validation en lot (10 000 depuis le 12/10/2026 ; 5 000 puis 500 avant)
LOT_MAX = 10000


class ValidationLotIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: Annotated[list[int], Field(min_length=1, max_length=LOT_MAX)]


class RejetLotIn(BaseModel):
    """Rejet en lot des propositions choisies (15/10/2026)."""

    model_config = ConfigDict(extra="forbid")

    ids: Annotated[list[int], Field(min_length=1, max_length=LOT_MAX)]
    commentaire: Commentaire | None = None


class AucuneLotIn(BaseModel):
    """« Aucune correspondance » pour plusieurs opérations ou écritures ambiguës (15/10/2026)."""

    model_config = ConfigDict(extra="forbid")

    ids: Annotated[list[int], Field(min_length=1, max_length=500)]
    commentaire: Commentaire | None = None


class TraitementLotOut(BaseModel):
    nb_traitees: int


class ValidationLotOut(BaseModel):
    nb_validees: int
