"""Comptabilisation des frais bancaires par SIMTIS : droits de timbre, commissions (13/10/2026)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import BankTransaction
from app.services.account_service import journal_des_frais
from app.services.frais_service import (
    AutreFrais,
    Detail,
    EcritureSimtis,
    FraisInclus,
    JourEcarte,
    LigneGL,
    Proposition,
    lignes_gl,
    texte_ligne,
)

# Une validation porte au plus sur cinq ans de jours, comptes compris
JOURS_MAX = 5000


class TimbreOut(BaseModel):
    id: int
    date_operation: date
    libelle: str
    montant: Decimal

    @classmethod
    def of(cls, tx: BankTransaction) -> "TimbreOut":
        return cls(
            id=tx.id, date_operation=tx.date_operation, libelle=tx.libelle, montant=tx.montant
        )


class DetailOut(BaseModel):
    """Total d'un type dans l'écriture (commission, TVA, commission effet…)."""

    type: str
    libelle: str
    nb_operations: int
    total: Decimal

    @classmethod
    def of(cls, detail: Detail) -> "DetailOut":
        return cls(
            type=detail.type,
            libelle=detail.libelle,
            nb_operations=detail.nb,
            total=detail.total,
        )


class LigneGLOut(BaseModel):
    """Ligne de l'écriture au format du grand livre Sage ; `compte` vide = à renseigner."""

    type: str | None
    type_libelle: str
    # Libellé exporté pour Sage : celui de l'écriture, « TVA … » pour une ligne de TVA (14/10/2026)
    libelle: str
    compte: str | None
    debit: Decimal | None
    credit: Decimal | None

    @classmethod
    def of(cls, ligne: LigneGL, libelle_ecriture: str) -> "LigneGLOut":
        return cls(
            type=ligne.type,
            libelle=texte_ligne(libelle_ecriture, ligne),
            type_libelle=ligne.type_libelle,
            compte=ligne.compte,
            debit=ligne.debit,
            credit=ligne.credit,
        )


FamilleFrais = Literal["timbres", "commissions", "frais"]


class PropositionTimbresOut(BaseModel):
    """Écriture à passer (« DT D'ENREGISTREMENT », « COM ») : un jour, un compte, ses opérations."""

    famille: FamilleFrais
    bank_account_id: int
    bank_code: str
    bank_logo: str | None
    devise: str
    date: date
    libelle: str
    total: Decimal
    nb_operations: int
    details: list[DetailOut]
    operations: list[TimbreOut]
    # Format du grand livre : journal des frais du compte et lignes de l'écriture à passer
    journal: str | None
    lignes: list[LigneGLOut]

    @classmethod
    def of(cls, item: Proposition) -> "PropositionTimbresOut":
        return cls(
            famille=item.famille.code,
            bank_account_id=item.account.id,
            bank_code=item.bank_code,
            bank_logo=item.account.bank.logo,
            devise=item.account.devise,
            date=item.jour.jour,
            libelle=item.famille.libelle,
            total=item.jour.total,
            nb_operations=len(item.jour.operations),
            details=[DetailOut.of(detail) for detail in item.jour.details],
            journal=journal_des_frais(item.account),
            lignes=[
                LigneGLOut.of(ligne, item.famille.libelle)
                for ligne in lignes_gl(item.account, item.jour.details, item.jour.total)
            ],
            operations=[TimbreOut.of(tx) for tx in item.jour.operations],
        )


class EcritureFraisOut(BaseModel):
    """Écriture comptabilisée par SIMTIS, rapprochée de ses opérations."""

    # « manuelle » : écriture saisie à la main (13/10/2026)
    famille: Literal["timbres", "commissions", "frais", "manuelle"]
    id: int
    bank_account_id: int
    bank_code: str
    date: date
    journal: str | None
    compte: str | None
    libelle: str
    montant: Decimal
    code: str | None
    # N° pièce Sage AAMMNNN (15/10/2026) ; l'ancien n° pour une écriture exportée avant
    numero_piece: str | None
    nb_operations: int
    exportee_le: datetime | None
    lignes: list[LigneGLOut]
    # Libellé, date ou lignes changés avant la validation (19/10/2026)
    modifiee: bool = False

    @classmethod
    def of(cls, item: EcritureSimtis) -> "EcritureFraisOut":
        entry = item.entry
        return cls(
            famille=item.famille.code,
            id=entry.id,
            bank_account_id=entry.bank_account_id,
            bank_code=item.bank_code,
            date=entry.date_ecriture,
            journal=entry.journal,
            compte=entry.compte,
            libelle=entry.libelle,
            montant=entry.montant,
            code=item.code,
            numero_piece=entry.numero_piece,
            nb_operations=item.nb_operations,
            exportee_le=entry.exportee_le,
            lignes=[LigneGLOut.of(ligne, entry.libelle) for ligne in item.lignes],
            modifiee=item.modifiee,
        )


class AutreFraisOut(BaseModel):
    """Frais à comptabiliser à la main (13/10/2026) : une opération du relevé."""

    id: int
    bank_account_id: int
    bank_code: str
    bank_logo: str | None
    date_operation: date
    libelle: str
    montant: Decimal
    pointage: str | None

    @classmethod
    def of(cls, item: AutreFrais) -> "AutreFraisOut":
        tx = item.transaction
        return cls(
            id=tx.id,
            bank_account_id=tx.bank_account_id,
            bank_code=item.bank_code,
            bank_logo=item.bank_logo,
            date_operation=tx.date_operation,
            libelle=tx.libelle,
            montant=tx.montant,
            pointage=item.pointage,
        )


class EcritureSageOut(BaseModel):
    id: int
    date: date
    journal: str | None
    numero_piece: str | None
    libelle: str
    montant: Decimal


class FraisInclusOut(BaseModel):
    """Frais déjà dans une écriture Sage libre (13/10/2026) : à rapprocher, jamais à comptabiliser."""

    id: int
    bank_account_id: int
    bank_code: str
    bank_logo: str | None
    date_operation: date
    libelle: str
    montant: Decimal
    ecriture: EcritureSageOut

    @classmethod
    def of(cls, item: FraisInclus) -> "FraisInclusOut":
        tx, entry = item.transaction, item.ecriture
        return cls(
            id=tx.id,
            bank_account_id=tx.bank_account_id,
            bank_code=item.bank_code,
            bank_logo=item.bank_logo,
            date_operation=tx.date_operation,
            libelle=tx.libelle,
            montant=tx.montant,
            ecriture=EcritureSageOut(
                id=entry.id,
                date=entry.date_ecriture,
                journal=entry.journal,
                numero_piece=entry.numero_piece,
                libelle=entry.libelle,
                montant=entry.montant,
            ),
        )


class JourEcarteOut(BaseModel):
    """Journée écartée de la comptabilisation automatique (19/10/2026)."""

    famille: FamilleFrais
    famille_libelle: str
    bank_account_id: int
    bank_code: str
    bank_logo: str | None
    date: date
    motif: str | None
    ecarte_le: datetime

    @classmethod
    def of(cls, item: JourEcarte) -> "JourEcarteOut":
        row = item.ecarte
        return cls(
            famille=item.famille.code,
            famille_libelle=item.famille.libelle,
            bank_account_id=row.bank_account_id,
            bank_code=item.bank_code,
            bank_logo=item.bank_logo,
            date=row.jour,
            motif=row.motif,
            ecarte_le=row.created_at,
        )


class TimbresOut(BaseModel):
    propositions: list[PropositionTimbresOut]
    total_propositions: Decimal
    ecritures: list[EcritureFraisOut]
    # Frais restants, à comptabiliser à la main
    autres_frais: list[AutreFraisOut] = []
    # Déjà dans une écriture Sage : à rapprocher (13/10/2026)
    frais_inclus: list[FraisInclusOut] = []
    # Journées écartées de la comptabilisation automatique (19/10/2026)
    ecartes: list[JourEcarteOut] = []


class LigneIn(BaseModel):
    """Ligne saisie d'une proposition (19/10/2026) : montant positif et son sens."""

    model_config = ConfigDict(extra="forbid")

    compte: Annotated[str, Field(max_length=40)]
    libelle: Annotated[str, Field(max_length=120)]
    montant: Decimal
    sens: Literal["Crédit", "Débit"]


class JourIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    famille: FamilleFrais
    bank_account_id: int
    date: date
    # Modifications avant validation (19/10/2026), toutes facultatives
    libelle: Annotated[str | None, Field(max_length=120)] = None
    date_ecriture: date | None = None
    lignes: Annotated[list[LigneIn] | None, Field(max_length=50)] = None


class JourChoisiIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    famille: FamilleFrais
    bank_account_id: int
    date: date


class EcarterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: int
    jours: Annotated[list[JourChoisiIn], Field(min_length=1, max_length=JOURS_MAX)]
    motif: Annotated[str | None, Field(max_length=500)] = None


class ReproposerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: int
    jours: Annotated[list[JourChoisiIn], Field(min_length=1, max_length=JOURS_MAX)]


class NombreOut(BaseModel):
    nb: int


class ValidationTimbresIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: int
    jours: Annotated[list[JourIn], Field(min_length=1, max_length=JOURS_MAX)]


class ValidationTimbresOut(BaseModel):
    nb_ecritures: int
    codes: list[str]


class SuppressionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motif: Annotated[str, Field(min_length=1, max_length=500)]


# Taux de TVA en %, 2 décimales (10 = 10 %)
TauxTva = Annotated[Decimal, Field(gt=0, le=100, max_digits=6, decimal_places=2)]
MontantTva = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2)]


class ManuelleIn(BaseModel):
    """Écriture saisie à la main pour des frais d'un même compte (13/10/2026)."""

    model_config = ConfigDict(extra="forbid")

    company_id: int
    transaction_ids: Annotated[list[int], Field(min_length=1, max_length=500)]
    libelle: Annotated[str, Field(min_length=1, max_length=60)]
    # « date » dans le JSON ; le nom du champ ne doit pas masquer le type `date`
    date_ecriture: date | None = Field(default=None, alias="date")
    # TVA séparée : son montant, sinon calculée au taux donné
    taux_tva: TauxTva | None = None
    montant_tva: MontantTva | None = None
