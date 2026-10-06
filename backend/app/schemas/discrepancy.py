"""Écarts (P12). Montants en texte exact."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import AccountingEntry, BankTransaction, User
from app.repositories.discrepancy_repository import Row
from app.services.discrepancy_service import (
    DiscrepanciesPage,
    DiscrepancyDetail,
    GenerationResult,
)

TypeEcart = Literal[
    "Banque sans écriture",
    "Écriture sans banque",
    "Montant différent",
    "Date différente",
    "Libellé ambigu",
    "Doublon potentiel",
]
StatutEcart = Literal["À traiter", "En cours", "Traité", "Clôturé"]
STATUTS = ("À traiter", "En cours", "Traité", "Clôturé")
Commentaire = Annotated[str, Field(max_length=1000)]


class OperationEcartOut(BaseModel):
    id: int
    date_operation: date
    libelle: str
    reference: str | None
    debit: Decimal
    credit: Decimal
    montant: Decimal
    statut: str

    @classmethod
    def of(cls, tx: BankTransaction | None) -> "OperationEcartOut | None":
        if tx is None:
            return None
        return cls(
            id=tx.id,
            date_operation=tx.date_operation,
            libelle=tx.libelle,
            reference=tx.reference,
            debit=tx.debit,
            credit=tx.credit,
            montant=tx.montant,
            statut=tx.statut,
        )


class EcritureEcartOut(BaseModel):
    id: int
    date_ecriture: date
    journal: str | None
    libelle: str
    numero_piece: str | None
    tiers: str | None
    debit: Decimal
    credit: Decimal
    montant: Decimal
    echeance: date | None
    statut: str

    @classmethod
    def of(cls, entry: AccountingEntry | None) -> "EcritureEcartOut | None":
        if entry is None:
            return None
        return cls(
            id=entry.id,
            date_ecriture=entry.date_ecriture,
            journal=entry.journal,
            libelle=entry.libelle,
            numero_piece=entry.numero_piece,
            tiers=entry.tiers,
            debit=entry.debit,
            credit=entry.credit,
            montant=entry.montant,
            echeance=entry.echeance,
            statut=entry.statut,
        )


class EcartOut(BaseModel):
    id: int
    type: TypeEcart
    statut: StatutEcart
    date_ecart: date
    montant: Decimal
    difference: Decimal | None
    devise: str | None
    bank_code: str | None
    libelle: str | None = Field(description="Libellé de l'opération, sinon de l'écriture")
    responsable_id: int | None
    responsable: str | None
    commentaire: str | None
    traite_le: datetime | None
    cloture_le: datetime | None
    created_at: datetime
    operation: OperationEcartOut | None
    ecriture: EcritureEcartOut | None

    @classmethod
    def of(cls, row: Row) -> "EcartOut":
        ecart, tx, entry, bank_code, devise, responsable = row
        return cls(
            id=ecart.id,
            type=ecart.type,
            statut=ecart.statut,
            date_ecart=ecart.date_ecart,
            montant=ecart.montant,
            difference=ecart.difference,
            devise=devise,
            bank_code=bank_code,
            libelle=tx.libelle if tx else entry.libelle if entry else None,
            responsable_id=ecart.responsable_id,
            responsable=responsable,
            commentaire=ecart.commentaire,
            traite_le=ecart.traite_le,
            cloture_le=ecart.cloture_le,
            created_at=ecart.created_at,
            operation=OperationEcartOut.of(tx),
            ecriture=EcritureEcartOut.of(entry),
        )


class EcartsPageOut(BaseModel):
    """Une page de 50 écarts ; `par_statut` et `montants_ouverts` portent sur tout le filtre."""

    total: int
    page: int
    taille: int
    par_statut: dict[str, int]
    montants_ouverts: dict[str, Decimal] = Field(
        description="Montant des écarts ouverts par devise (jamais additionné entre devises)"
    )
    ecarts: list[EcartOut]

    @classmethod
    def from_page(cls, result: DiscrepanciesPage) -> "EcartsPageOut":
        return cls(
            total=result.total,
            page=result.page,
            taille=result.taille,
            par_statut={statut: result.par_statut.get(statut, 0) for statut in STATUTS},
            montants_ouverts={
                k: v.quantize(Decimal("0.01")) for k, v in result.montants_ouverts.items()
            },
            ecarts=[EcartOut.of(row) for row in result.ecarts],
        )


class EvenementOut(BaseModel):
    action: str
    auteur: str | None
    le: datetime
    avant: dict[str, Any] | None
    apres: dict[str, Any] | None


class EcartDetailOut(EcartOut):
    cloture_par: str | None
    historique: list[EvenementOut]

    @classmethod
    def from_detail(cls, detail: DiscrepancyDetail) -> "EcartDetailOut":
        return cls(
            **EcartOut.of(detail.row).model_dump(),
            cloture_par=detail.cloture_par,
            historique=[
                EvenementOut(
                    action=log.action,
                    auteur=auteur,
                    le=log.created_at,
                    avant=log.ancienne_valeur,
                    apres=log.nouvelle_valeur,
                )
                for log, auteur in detail.historique
            ],
        )


class EcartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: TypeEcart
    transaction_id: int | None = None
    ecriture_id: int | None = None
    commentaire: Commentaire | None = None
    responsable_id: int | None = None


class EcartUpdateIn(BaseModel):
    """Champs absents : inchangés. `responsable_id: null` retire le responsable."""

    model_config = ConfigDict(extra="forbid")

    statut: Literal["À traiter", "En cours", "Traité"] | None = None
    responsable_id: int | None = None
    commentaire: Commentaire | None = None


class ClotureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commentaire: Annotated[str, Field(min_length=1, max_length=1000)]


class GenerationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: int
    bank_account_id: int | None = None
    du: date
    au: date


class GenerationOut(BaseModel):
    banque_sans_ecriture: int
    ecriture_sans_banque: int
    doublons: int
    total: int
    date_limite: date = Field(
        description="Seules les lignes datées jusqu'à ce jour peuvent être « sans écriture / banque »"
    )

    @classmethod
    def from_result(cls, result: GenerationResult) -> "GenerationOut":
        return cls(
            banque_sans_ecriture=result.banque_sans_ecriture,
            ecriture_sans_banque=result.ecriture_sans_banque,
            doublons=result.doublons,
            total=result.total,
            date_limite=result.date_limite,
        )


class ResponsableOut(BaseModel):
    id: int
    nom: str

    @classmethod
    def of(cls, user: User) -> "ResponsableOut":
        return cls(id=user.id, nom=user.nom)
