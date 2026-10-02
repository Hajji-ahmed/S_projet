"""Relevés bancaires : analyse (P7.1), confirmation (P7.2) et consultation (P7.3).

Les montants circulent en texte exact.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

from app.models import BankAccount, BankTransaction
from app.services.import_service import (
    STATEMENT_FIELDS,
    AccountStatement,
    StatementAnalysis,
    StatementImport,
    StatementRow,
)

FieldCode = Literal[
    "date_operation",
    "date_valeur",
    "libelle",
    "reference",
    "debit",
    "credit",
    "montant",
    "solde",
    "pointage",
    "lettrage_escompte",
    "commentaire",
    "banque",
]


# Index d'une colonne Excel : 0 = A ... 16383 = XFD
ColumnIndex = Annotated[int, Field(ge=0, le=16383)]


class MappingIn(RootModel[dict[FieldCode, ColumnIndex | None]]):
    """Correspondance choisie par l'utilisateur : champ standard → index de colonne (0 = colonne A).
    Un champ absent ou `null` n'est associé à aucune colonne."""


class PointageTypeOut(BaseModel):
    """Type d'opération (Pointage) proposé dans les listes de choix."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    libelle: str


class ChampOut(BaseModel):
    code: str
    libelle: str
    obligatoire: bool


class ColonneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    index: int
    lettre: str
    entete: str
    exemples: list[str]


class LigneAnalyseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    numero: int = Field(description="Numéro de la ligne dans le fichier Excel")
    statut: Literal["Valide", "Erreur", "Doublon"]
    motifs: list[str]
    date_operation: date | None
    date_valeur: date | None
    libelle: str | None
    reference: str | None
    debit: Decimal | None
    credit: Decimal | None
    montant: Decimal | None
    solde: Decimal | None
    pointage: str | None = Field(description="Valeur lue dans le fichier, telle quelle")
    pointage_type_id: int | None
    pointage_libelle: str | None
    pointage_auto: bool = Field(description="Déduit du libellé et du sens, pas lu dans le fichier")
    lettrage_escompte: str | None
    commentaire: str | None
    hash_ligne: str | None
    doublon_de: int | None = Field(
        description="Ligne identique plus haut dans le fichier : celle-ci peut être gardée"
    )


class ResumeOut(BaseModel):
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
    solde_ouverture: Decimal | None
    solde_cloture: Decimal | None
    solde_ouverture_fichier: bool = Field(description="Lu sur une ligne SOLDE INITIAL du fichier")
    solde_cloture_fichier: bool = Field(description="Lu sur une ligne SOLDE FINAL du fichier")
    soldes_coherents: bool | None


class AnalyseOut(BaseModel):
    """Aperçu d'un relevé : rien n'est encore enregistré."""

    bank_account_id: int
    company_id: int
    bank_code: str
    devise: str
    fichier_nom: str
    fichier_hash: str
    deja_importe: bool = Field(description="Ce fichier a déjà été confirmé pour cette société")
    feuilles: list[str]
    feuille: str
    ligne_entete: int = Field(description="Numéro de la ligne d'en-tête dans le fichier Excel")
    colonnes: list[ColonneOut]
    champs: list[ChampOut]
    mapping: dict[str, int | None]
    mapping_source: Literal["Détection", "Modèle de la banque", "Utilisateur"]
    erreurs_mapping: list[str]
    lignes: list[LigneAnalyseOut]
    resume: ResumeOut

    @classmethod
    def from_analysis(cls, analysis: StatementAnalysis) -> "AnalyseOut":
        account = analysis.account
        return cls(
            bank_account_id=account.id,
            company_id=account.company_id,
            bank_code=account.bank.code,
            devise=account.devise,
            fichier_nom=analysis.fichier_nom,
            fichier_hash=analysis.fichier_hash,
            deja_importe=analysis.deja_importe,
            feuilles=analysis.feuilles,
            feuille=analysis.feuille,
            ligne_entete=analysis.ligne_entete,
            colonnes=[ColonneOut.model_validate(column) for column in analysis.colonnes],
            champs=[
                ChampOut(code=item.code, libelle=item.libelle, obligatoire=item.obligatoire)
                for item in STATEMENT_FIELDS
            ],
            mapping=analysis.mapping,
            mapping_source=analysis.mapping_source,
            erreurs_mapping=analysis.erreurs_mapping,
            lignes=[LigneAnalyseOut.model_validate(line) for line in analysis.lignes],
            resume=ResumeOut.model_validate(analysis.resume),
        )


class LigneSoumiseIn(BaseModel):
    """Une ligne du fichier, telle que l'utilisateur l'a laissée dans l'aperçu (corrigée ou non).

    Les valeurs sont revérifiées par le serveur avec les mêmes règles que l'analyse : elles arrivent
    en texte, comme des cellules de fichier. Pas d'ajout de ligne : le numéro est obligatoire.
    """

    model_config = ConfigDict(extra="forbid")

    numero: Annotated[int, Field(ge=1)]
    date_operation: str | None = None
    date_valeur: str | None = None
    libelle: str | None = Field(default=None, max_length=500)
    reference: str | None = Field(default=None, max_length=60)
    debit: str | None = None
    credit: str | None = None
    solde: str | None = None
    pointage_type_id: int | None = None
    lettrage_escompte: str | None = Field(default=None, max_length=200)
    commentaire: str | None = Field(default=None, max_length=1000)


class LignesSoumisesIn(RootModel[list[LigneSoumiseIn]]):
    """Lignes à importer ; un même numéro ne peut pas apparaître deux fois."""

    @model_validator(mode="after")
    def _numeros_uniques(self) -> "LignesSoumisesIn":
        numeros = [line.numero for line in self.root]
        if len(numeros) != len(set(numeros)):
            raise ValueError("Une ligne du fichier apparaît deux fois.")
        return self


class LignesGardeesIn(RootModel[list[Annotated[int, Field(ge=1)]]]):
    """Numéros des lignes identiques à une autre du fichier que l'utilisateur garde."""


class ControleSoldeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    statut: Literal["Conforme", "Écart", "À vérifier"]
    date_controle: date
    solde_releve: Decimal
    solde_enregistre: Decimal
    ecart: Decimal
    commentaire: str | None


class ConfirmationOut(BaseModel):
    """Résultat d'un import confirmé."""

    import_id: int
    statement_id: int
    bank_account_id: int
    fichier_nom: str
    nb_importees: int
    nb_erreurs_ecartees: int
    nb_doublons_ecartes: int
    total_debit: Decimal
    total_credit: Decimal
    periode_debut: date
    periode_fin: date
    solde_ouverture: Decimal | None
    solde_cloture: Decimal | None
    soldes_coherents: bool | None
    controle_solde: ControleSoldeOut | None = Field(
        description="Comparaison avec le solde déjà enregistré ce jour-là (aucun : pas de contrôle)"
    )
    solde_du_jour: Literal["Créé", "Corrigé", "Inchangé"] | None = Field(
        description="Effet sur le solde du jour de clôture (aucun sans colonne Solde)"
    )
    modele_enregistre: bool

    @classmethod
    def from_import(cls, result: StatementImport) -> "ConfirmationOut":
        statement = result.statement
        return cls(
            import_id=result.batch.id,
            statement_id=statement.id,
            bank_account_id=statement.bank_account_id,
            fichier_nom=result.batch.fichier_nom,
            nb_importees=result.nb_importees,
            nb_erreurs_ecartees=result.nb_erreurs_ecartees,
            nb_doublons_ecartes=result.nb_doublons_ecartes,
            total_debit=result.total_debit,
            total_credit=result.total_credit,
            periode_debut=statement.periode_debut,
            periode_fin=statement.periode_fin,
            solde_ouverture=statement.solde_ouverture,
            solde_cloture=statement.solde_cloture,
            soldes_coherents=result.soldes_coherents,
            controle_solde=(
                ControleSoldeOut.model_validate(result.controle) if result.controle else None
            ),
            solde_du_jour=result.solde_du_jour,
            modele_enregistre=result.modele_enregistre,
        )


# --- Consultation (P7.3) ---------------------------------------------------------------------------


class StatementOut(BaseModel):
    """Un relevé importé, pour l'historique de la page Relevés."""

    id: int
    import_id: int
    fichier_nom: str
    importe_le: datetime
    importe_par: str | None
    bank_account_id: int
    bank_code: str
    devise: str
    compte_libelle: str
    compte_numero: str
    periode_debut: date | None
    periode_fin: date | None
    solde_ouverture: Decimal | None
    solde_cloture: Decimal | None
    nb_lignes: int
    nb_erreurs: int
    nb_doublons: int
    controle_solde: ControleSoldeOut | None

    @classmethod
    def from_row(cls, row: StatementRow) -> "StatementOut":
        statement, batch, account = row.statement, row.batch, row.account
        return cls(
            id=statement.id,
            import_id=batch.id,
            fichier_nom=batch.fichier_nom,
            importe_le=batch.created_at,
            importe_par=row.importe_par,
            bank_account_id=account.id,
            bank_code=account.bank.code,
            devise=account.devise,
            compte_libelle=account.libelle,
            compte_numero=account.numero,
            periode_debut=statement.periode_debut,
            periode_fin=statement.periode_fin,
            solde_ouverture=statement.solde_ouverture,
            solde_cloture=statement.solde_cloture,
            nb_lignes=batch.nb_lignes,
            nb_erreurs=batch.nb_erreurs,
            nb_doublons=batch.nb_doublons,
            controle_solde=(
                ControleSoldeOut.model_validate(row.controle) if row.controle else None
            ),
        )


class TransactionOut(BaseModel):
    """Une opération bancaire, au format standard du relevé (CDC §4), dans l'ordre de ses 11 champs.

    Suivent, hors format standard : la référence, le montant signé et le statut de rapprochement.
    """

    id: int
    societe: str
    pointage: str | None = Field(description="Type d'opération ; vide s'il est inconnu")
    banque: str = Field(description="Code de la banque (AWB, BMCE...)")
    date_operation: date
    date_valeur: date | None
    libelle: str
    debit: Decimal
    credit: Decimal
    solde: Decimal | None
    lettrage_escompte: str | None
    commentaire: str | None
    reference: str | None
    montant: Decimal
    statut: str
    origine: str = Field(description="« Fichier », ou « Corrigée » dans l'aperçu avant l'import")
    # Pour préremplir la fenêtre de modification (le libellé seul ne suffit pas)
    pointage_type_id: int | None

    @classmethod
    def from_row(
        cls, account: BankAccount, transaction: BankTransaction, pointage: str | None
    ) -> "TransactionOut":
        return cls(
            pointage_type_id=transaction.pointage_type_id,
            id=transaction.id,
            societe=account.company.nom,
            pointage=pointage,
            banque=account.bank.code,
            date_operation=transaction.date_operation,
            date_valeur=transaction.date_valeur,
            libelle=transaction.libelle,
            debit=transaction.debit,
            credit=transaction.credit,
            solde=transaction.solde,
            lettrage_escompte=transaction.lettrage_escompte,
            commentaire=transaction.commentaire,
            reference=transaction.reference,
            montant=transaction.montant,
            statut=transaction.statut,
            origine=transaction.origine,
        )


class TransactionUpdateIn(BaseModel):
    """Champs métier d'une opération importée : les seuls modifiables après l'import."""

    model_config = ConfigDict(extra="forbid")

    pointage_type_id: int | None = None
    lettrage_escompte: str | None = Field(default=None, max_length=120)
    commentaire: str | None = Field(default=None, max_length=1000)


class AccountStatementOut(BaseModel):
    """Relevé continu d'un compte : toutes ses opérations importées, quel que soit le fichier."""

    bank_account_id: int
    societe: str
    bank_code: str
    devise: str
    compte_libelle: str
    compte_numero: str
    periode_debut: date | None
    periode_fin: date | None
    nb_operations: int
    total_debit: Decimal
    total_credit: Decimal
    solde_ouverture: Decimal | None
    solde_cloture: Decimal | None
    operations: list[TransactionOut]

    @classmethod
    def from_result(cls, result: AccountStatement) -> "AccountStatementOut":
        account = result.account
        return cls(
            bank_account_id=account.id,
            societe=account.company.nom,
            bank_code=account.bank.code,
            devise=account.devise,
            compte_libelle=account.libelle,
            compte_numero=account.numero,
            periode_debut=result.periode_debut,
            periode_fin=result.periode_fin,
            nb_operations=len(result.rows),
            total_debit=result.total_debit,
            total_credit=result.total_credit,
            solde_ouverture=result.solde_ouverture,
            solde_cloture=result.solde_cloture,
            operations=[
                TransactionOut.from_row(account, transaction, pointage)
                for transaction, pointage in result.rows
            ],
        )
