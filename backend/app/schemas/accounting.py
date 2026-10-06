"""Import et lecture des écritures comptables Sage / SI (P10). Montants en texte exact."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from app.models import AccountingEntry
from app.schemas.statement import ChampOut, ColonneOut
from app.services.accounting_import_service import (
    ACCOUNTING_FIELDS,
    AccountingAnalysis,
    EntriesImport,
    EntriesPage,
)

AccountingFieldCode = Literal[
    "date_ecriture",
    "journal",
    "compte",
    "libelle",
    "reference",
    "debit",
    "credit",
    "montant",
    "numero_piece",
    "echeance",
    "tiers",
]
# Index d'une colonne Excel : 0 = A ... 16383 = XFD
ColumnIndex = Annotated[int, Field(ge=0, le=16383)]


class MappingComptableIn(RootModel[dict[AccountingFieldCode, ColumnIndex | None]]):
    """Correspondance choisie : champ → index de colonne (0 = colonne A)."""


class LigneComptableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    numero: int = Field(description="Numéro de la ligne dans le fichier Excel")
    statut: Literal["Valide", "Erreur", "Doublon"]
    motifs: list[str]
    date_ecriture: date | None
    journal: str | None
    compte: str | None
    libelle: str | None
    reference: str | None
    debit: Decimal | None
    credit: Decimal | None
    montant: Decimal | None
    numero_piece: str | None
    echeance: date | None
    tiers: str | None
    bank_account_id: int | None
    bank_code: str | None
    hash_ligne: str | None
    doublon_de: int | None


class TotalCompteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bank_account_id: int
    bank_code: str
    journal: str
    nb: int
    total_debit: Decimal
    total_credit: Decimal


class ResumeComptableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nb_lignes: int
    nb_valides: int
    nb_erreurs: int
    nb_doublons: int
    nb_ignorees: int
    total_debit: Decimal
    total_credit: Decimal
    periode_debut: date | None
    periode_fin: date | None
    par_compte: list[TotalCompteOut]


class AnalyseComptableOut(BaseModel):
    """Aperçu d'un export Sage : rien n'est encore enregistré."""

    company_id: int
    fichier_nom: str
    fichier_hash: str
    deja_importe: bool = Field(description="Ce fichier a déjà été confirmé pour cette société")
    feuilles: list[str]
    feuille: str
    ligne_entete: int
    colonnes: list[ColonneOut]
    champs: list[ChampOut]
    mapping: dict[str, int | None]
    mapping_source: Literal["Détection", "Modèle de la société", "Utilisateur"]
    erreurs_mapping: list[str]
    lignes: list[LigneComptableOut]
    resume: ResumeComptableOut

    @classmethod
    def from_analysis(cls, analysis: AccountingAnalysis) -> "AnalyseComptableOut":
        return cls(
            company_id=analysis.company.id,
            fichier_nom=analysis.fichier_nom,
            fichier_hash=analysis.fichier_hash,
            deja_importe=analysis.deja_importe,
            feuilles=analysis.feuilles,
            feuille=analysis.feuille,
            ligne_entete=analysis.ligne_entete,
            colonnes=[ColonneOut.model_validate(column) for column in analysis.colonnes],
            champs=[
                ChampOut(code=item.code, libelle=item.libelle, obligatoire=item.obligatoire)
                for item in ACCOUNTING_FIELDS
            ],
            mapping=analysis.mapping,
            mapping_source=analysis.mapping_source,
            erreurs_mapping=analysis.erreurs_mapping,
            lignes=[LigneComptableOut.model_validate(line) for line in analysis.lignes],
            resume=ResumeComptableOut.model_validate(analysis.resume),
        )


class LignesGardeesIn(RootModel[list[Annotated[int, Field(ge=1)]]]):
    """Numéros des doublons internes au fichier à garder."""


class ConfirmationComptableOut(BaseModel):
    import_id: int
    fichier_nom: str
    nb_importees: int
    nb_erreurs_ecartees: int
    nb_doublons_ecartes: int
    par_compte: list[TotalCompteOut]
    periode_debut: date | None
    periode_fin: date | None
    modele_enregistre: bool = Field(description="Correspondance mémorisée pour la société")

    @classmethod
    def from_import(cls, result: EntriesImport) -> "ConfirmationComptableOut":
        return cls(
            import_id=result.batch.id,
            fichier_nom=result.batch.fichier_nom,
            nb_importees=result.nb_importees,
            nb_erreurs_ecartees=result.nb_erreurs_ecartees,
            nb_doublons_ecartes=result.nb_doublons_ecartes,
            par_compte=[TotalCompteOut.model_validate(item) for item in result.par_compte],
            periode_debut=result.periode_debut,
            periode_fin=result.periode_fin,
            modele_enregistre=result.modele_enregistre,
        )


# --- Lecture ---------------------------------------------------------------------------------------


class EcritureOut(BaseModel):
    id: int
    date_ecriture: date
    journal: str | None
    compte: str | None
    libelle: str
    reference: str | None
    debit: Decimal
    credit: Decimal
    montant: Decimal
    numero_piece: str | None
    echeance: date | None
    tiers: str | None
    bank_account_id: int | None
    bank_code: str | None
    statut: str

    @classmethod
    def fields_of(cls, entry: AccountingEntry, bank_code: str | None) -> dict:
        return {
            "id": entry.id,
            "date_ecriture": entry.date_ecriture,
            "journal": entry.journal,
            "compte": entry.compte,
            "libelle": entry.libelle,
            "reference": entry.reference,
            "debit": entry.debit,
            "credit": entry.credit,
            "montant": entry.montant,
            "numero_piece": entry.numero_piece,
            "echeance": entry.echeance,
            "tiers": entry.tiers,
            "bank_account_id": entry.bank_account_id,
            "bank_code": bank_code,
            "statut": entry.statut,
        }


class EcrituresPageOut(BaseModel):
    """Une page de 50 écritures ; `total`, `total_debit` et `total_credit` portent sur tout le filtre."""

    total: int
    page: int
    taille: int
    total_debit: Decimal
    total_credit: Decimal
    ecritures: list[EcritureOut]

    @classmethod
    def from_page(cls, result: EntriesPage) -> "EcrituresPageOut":
        return cls(
            total=result.total,
            page=result.page,
            taille=result.taille,
            total_debit=result.total_debit,
            total_credit=result.total_credit,
            ecritures=[
                EcritureOut(**EcritureOut.fields_of(entry, code))
                for entry, code in result.ecritures
            ],
        )


class EcritureDetailOut(EcritureOut):
    fichier_nom: str | None
    importe_le: datetime | None
    importe_par: str | None


class ImportComptableOut(BaseModel):
    id: int
    importe_le: datetime
    importe_par: str | None
    fichier_nom: str
    periode_debut: date | None
    periode_fin: date | None
    nb_ecritures: int
    total_debit: Decimal
    total_credit: Decimal

    @classmethod
    def from_row(cls, row: tuple) -> "ImportComptableOut":
        batch, author, debut, fin, nb, debit, credit = row
        return cls(
            id=batch.id,
            importe_le=batch.created_at,
            importe_par=author,
            fichier_nom=batch.fichier_nom,
            periode_debut=debut,
            periode_fin=fin,
            nb_ecritures=nb or 0,
            total_debit=debit if debit is not None else Decimal("0.00"),
            total_credit=credit if credit is not None else Decimal("0.00"),
        )
