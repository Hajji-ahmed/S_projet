"""Import des écritures comptables d'un export Sage / SI (P10), en deux temps : analyse, puis
confirmation. SIMTIS n'est pas un second Sage : aucune écriture n'est créée ni corrigée ici.

Règles (décisions du 05/10/2026) :
- le fichier est importé pour une société ; seules les lignes d'un journal de banque sont retenues :
  journal = `journal_sage` d'un compte bancaire actif de la société, et compte qui commence par le
  `compte_comptable` de ce compte bancaire (s'il est renseigné) ; les autres lignes sont ignorées ;
- débit et crédit sont gardés tels que dans Sage ; une ligne en erreur se corrige dans Sage ;
- doublon : ligne déjà importée pour la société, ou identique à une autre ligne du fichier.
"""

from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AccountingEntry, BankAccount, ColumnMapping, Company, ImportBatch
from app.repositories import account_repository, accounting_repository, import_repository
from app.services import audit_service, import_file, position_service
from app.services.errors import ConflictError, NotFoundError
from app.services.import_file import Column, IgnoredLine, ImportField, Mapping
from app.services.normalization_service import (
    clean_libelle,
    clean_text,
    file_hash,
    is_blank,
    line_hash,
    parse_amount,
    parse_date,
)

TYPE_IMPORT = "Comptabilité"
JOURNAL_MAX = 20
COMPTE_MAX = 20
REFERENCE_MAX = 60
PIECE_MAX = 60
TIERS_MAX = 120

ACCOUNTING_FIELDS: tuple[ImportField, ...] = (
    ImportField(
        "date_ecriture",
        "Date",
        True,
        ("date", "date ecriture", "date piece", "date comptable"),
    ),
    ImportField("journal", "Journal", True, ("journal", "code journal", "jnl")),
    ImportField(
        "compte", "Compte", True, ("compte", "compte general", "n compte", "numero de compte")
    ),
    ImportField("libelle", "Libellé", True, ("libelle", "libelle ecriture", "intitule")),
    ImportField("reference", "Référence", False, ("reference", "ref")),
    ImportField("debit", "Débit", False, ("debit", "montant debit")),
    ImportField("credit", "Crédit", False, ("credit", "montant credit")),
    ImportField("montant", "Montant signé", False, ("montant", "montant signe")),
    ImportField(
        "numero_piece",
        "N° pièce",
        False,
        (
            "n piece",
            "numero piece",
            "piece",
            "no piece",
            "n de piece",
            "n de pieces",
            "numero de piece",
            "numero de pieces",
            "pieces",
            "n pieces",
            "no de piece",
        ),  # fmt: skip
    ),
    ImportField("echeance", "Échéance", False, ("echeance", "date echeance")),
    ImportField("tiers", "Tiers", False, ("tiers", "compte tiers", "client fournisseur")),
)
FIELD_LABELS = {item.code: item.libelle for item in ACCOUNTING_FIELDS}


@dataclass
class EntryLine:
    numero: int  # numéro de la ligne dans Excel
    statut: str  # Valide / Erreur / Doublon
    motifs: list[str]
    date_ecriture: date | None = None
    journal: str | None = None
    compte: str | None = None
    libelle: str | None = None
    reference: str | None = None
    debit: Decimal | None = None
    credit: Decimal | None = None
    montant: Decimal | None = None
    numero_piece: str | None = None
    echeance: date | None = None
    tiers: str | None = None
    bank_account_id: int | None = None
    bank_code: str | None = None
    hash_ligne: str | None = None
    # Doublon interne au fichier : numéro de la première ligne identique (gardable à la confirmation)
    doublon_de: int | None = None


@dataclass
class AccountTotal:
    bank_account_id: int
    bank_code: str
    journal: str  # deux comptes d'une même banque se distinguent par leur journal Sage
    nb: int = 0
    total_debit: Decimal = Decimal("0.00")
    total_credit: Decimal = Decimal("0.00")


@dataclass
class EntriesSummary:
    nb_lignes: int = 0
    nb_valides: int = 0
    nb_erreurs: int = 0
    nb_doublons: int = 0
    nb_ignorees: int = 0
    total_debit: Decimal = Decimal("0.00")
    total_credit: Decimal = Decimal("0.00")
    periode_debut: date | None = None
    periode_fin: date | None = None
    par_compte: list[AccountTotal] = field(default_factory=list)


@dataclass
class AccountingAnalysis:
    company: Company
    fichier_nom: str
    fichier_hash: str
    deja_importe: bool
    feuilles: list[str]
    feuille: str
    ligne_entete: int
    colonnes: list[Column]
    mapping: Mapping
    mapping_source: str  # Détection / Modèle de la société / Utilisateur
    erreurs_mapping: list[str]
    lignes: list[EntryLine] = field(default_factory=list)
    resume: EntriesSummary = field(default_factory=EntriesSummary)
    # Lignes non retenues (titres, autres journaux, contreparties) et leur raison : affichées seulement
    lignes_ignorees: list[IgnoredLine] = field(default_factory=list)


def _company(db: Session, company_id: int) -> Company:
    company = account_repository.get_company(db, company_id)
    if company is None or not company.actif:
        raise NotFoundError("Société introuvable.")
    return company


def _code(value: object) -> str:
    """Journal ou compte lu dans une cellule : texte en majuscules, sans espaces ; un nombre lu par
    Excel (514100, 514100.0) redevient son texte entier."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return "".join((clean_text(value) or "").split()).upper()


def _is_ignored(cells: dict[str, object]) -> bool:
    """Ligne de titre ou de total : ni date ni montant."""
    amounts = ("debit", "credit", "montant")
    return is_blank(cells.get("date_ecriture")) and all(
        is_blank(cells.get(code)) for code in amounts
    )


def _ignored_reason(cells: dict[str, object], journals: dict[str, BankAccount]) -> str:
    """Pourquoi une ligne n'est pas une ligne banque d'un journal de banque."""
    if _is_ignored(cells):
        return "Ligne de titre ou de total : ni date ni montant"
    journal = _code(cells.get("journal"))
    account = journals.get(journal)
    if account is None:
        return (
            f"Journal « {journal} » : pas le journal Sage d'un compte bancaire"
            if journal
            else "Pas de journal"
        )
    return (
        f"Compte {_code(cells.get('compte')) or '(vide)'} : contrepartie, pas la ligne banque "
        f"({account.compte_comptable}…) du journal {journal}"
    )


def _bank_account_of(
    cells: dict[str, object], journals: dict[str, BankAccount]
) -> BankAccount | None:
    """Compte bancaire de la ligne, ou None si ce n'est pas la ligne banque d'un journal de banque."""
    account = journals.get(_code(cells.get("journal")))
    if account is None:
        return None
    compte = _code(cells.get("compte"))
    if account.compte_comptable and not compte.startswith(account.compte_comptable):
        return None  # contrepartie (411, 441, 6147...)
    return account


def _read_entry(
    numero: int, cells: dict[str, object], mapping: Mapping, account: BankAccount, today: date
) -> EntryLine:
    line = EntryLine(numero=numero, statut="Valide", motifs=[])
    line.journal = _code(cells.get("journal"))[:JOURNAL_MAX]
    line.compte = _code(cells.get("compte"))[:COMPTE_MAX]
    line.bank_account_id, line.bank_code = account.id, account.bank.code

    def amount(code: str) -> Decimal | None:
        try:
            return parse_amount(cells.get(code))
        except ValueError as error:
            line.motifs.append(f"{FIELD_LABELS[code]} : {error}")
            return None

    try:
        line.date_ecriture = parse_date(cells.get("date_ecriture"))
        if line.date_ecriture is None:
            line.motifs.append("Date manquante.")
        elif line.date_ecriture > today:
            line.motifs.append("Date dans le futur.")
    except ValueError as error:
        line.motifs.append(f"Date : {error}")
    try:
        line.echeance = parse_date(cells.get("echeance"))
    except ValueError as error:
        line.motifs.append(f"Échéance : {error}")

    line.libelle = clean_libelle(cells.get("libelle"))
    if line.libelle is None:
        line.motifs.append("Libellé manquant.")

    unreadable = len(line.motifs)
    if mapping.get("montant") is not None:
        signed = amount("montant")
        if signed:
            line.credit = max(signed, Decimal("0.00"))
            line.debit = max(-signed, Decimal("0.00"))
        elif len(line.motifs) == unreadable:  # vide ou nul (un montant illisible est déjà signalé)
            line.motifs.append("Montant manquant ou nul.")
    else:
        debit, credit = amount("debit"), amount("credit")
        if len(line.motifs) == unreadable:
            debit = debit if debit is not None else Decimal("0.00")
            credit = credit if credit is not None else Decimal("0.00")
            # Un montant négatif (extourne) n'est pas remis en positif : son sens s'inverserait
            negatives = [
                f"{FIELD_LABELS[code]} négatif."
                for code, value in (("debit", debit), ("credit", credit))
                if value < 0
            ]
            if negatives:
                line.motifs.extend(negatives)
            elif debit and credit:
                line.motifs.append("Débit et crédit renseignés sur la même ligne.")
            elif not debit and not credit:
                line.motifs.append("Montant manquant ou nul.")
            else:
                line.debit, line.credit = debit, credit
    if line.debit is not None and line.credit is not None:
        line.montant = line.credit - line.debit

    reference = clean_text(cells.get("reference"))
    line.reference = reference[:REFERENCE_MAX] if reference else None
    line.numero_piece = clean_text(cells.get("numero_piece"))
    if line.numero_piece and len(line.numero_piece) > PIECE_MAX:
        line.motifs.append(f"N° pièce : {PIECE_MAX} caractères au plus.")
    line.tiers = clean_text(cells.get("tiers"))
    if line.tiers and len(line.tiers) > TIERS_MAX:
        line.motifs.append(f"Tiers : {TIERS_MAX} caractères au plus.")

    if line.motifs:
        line.statut = "Erreur"
    return line


def _line_key(line: EntryLine) -> tuple:
    """Valeurs qui identifient une écriture : base de son empreinte (`line_hash`)."""
    return (
        line.date_ecriture,
        line.journal,
        line.compte,
        line.libelle,
        line.debit,
        line.credit,
        line.numero_piece,
        line.reference,
    )


def _mark_duplicates(db: Session, company_id: int, lines: list[EntryLine]) -> None:
    first_seen: dict[tuple, int] = {}
    occurrences: Counter[tuple] = Counter()
    for line in lines:
        if line.statut != "Valide":
            continue
        key = _line_key(line)
        occurrences[key] += 1
        line.hash_ligne = line_hash(company_id, key, occurrences[key])
        if key in first_seen:
            line.statut = "Doublon"
            line.doublon_de = first_seen[key]
            line.motifs.append(f"Ligne identique à la ligne {first_seen[key]} du fichier.")
        else:
            first_seen[key] = line.numero
    # Une ligne déjà importée l'emporte sur « identique dans le fichier » : elle ne peut être gardée
    hashes = [line.hash_ligne for line in lines if line.hash_ligne]
    known = accounting_repository.existing_entry_hashes(db, company_id, hashes)
    for line in lines:
        if line.hash_ligne in known:
            line.statut = "Doublon"
            line.doublon_de = None
            line.motifs = ["Déjà importée pour cette société."]


def _summarise(lines: list[EntryLine], ignored: int) -> EntriesSummary:
    summary = EntriesSummary(nb_lignes=len(lines), nb_ignorees=ignored)
    valid = [line for line in lines if line.statut == "Valide"]
    summary.nb_valides = len(valid)
    summary.nb_erreurs = sum(1 for line in lines if line.statut == "Erreur")
    summary.nb_doublons = sum(1 for line in lines if line.statut == "Doublon")
    summary.total_debit = sum((line.debit for line in valid), Decimal("0.00"))
    summary.total_credit = sum((line.credit for line in valid), Decimal("0.00"))
    if valid:
        dates = [line.date_ecriture for line in valid]
        summary.periode_debut, summary.periode_fin = min(dates), max(dates)
    totals: dict[int, AccountTotal] = {}
    for line in valid:
        total = totals.setdefault(
            line.bank_account_id,
            AccountTotal(line.bank_account_id, line.bank_code, line.journal),
        )
        total.nb += 1
        total.total_debit += line.debit
        total.total_credit += line.credit
    summary.par_compte = sorted(totals.values(), key=lambda item: (item.bank_code, item.journal))
    return summary


def analyse_entries(
    db: Session,
    *,
    company_id: int,
    fichier_nom: str,
    content: bytes,
    mapping: Mapping | None = None,
    feuille: str | None = None,
    today: date | None = None,
) -> AccountingAnalysis:
    """Analyse un export Sage pour une société. Ne modifie pas la base."""
    company = _company(db, company_id)
    journals = {
        account.journal_sage: account
        for account in accounting_repository.bank_journals(db, company.id)
    }
    if not journals:
        raise ConflictError("Renseignez le journal Sage de vos comptes bancaires (écran Comptes).")
    import_file.check_file(fichier_nom, content)
    feuilles, feuille, rows = import_file.read_sheet(content, feuille)
    header_index = import_file.detect_header(rows, ACCOUNTING_FIELDS)
    data = rows[header_index + 1 :]
    if len(data) > import_file.MAX_ROWS:
        raise ConflictError(
            f"Fichier trop long : {import_file.MAX_ROWS_TEXTE} lignes au plus par fichier."
        )
    columns = import_file.columns_of(rows[header_index], data)

    if mapping is not None:
        source = "Utilisateur"
        mapping = {item.code: mapping.get(item.code) for item in ACCOUNTING_FIELDS}
    else:
        saved = accounting_repository.latest_company_mapping(db, company.id, TYPE_IMPORT)
        found = (
            import_file.mapping_from_headers(saved.mapping, columns, ACCOUNTING_FIELDS)
            if saved
            else None
        )
        source = "Modèle de la société" if found else "Détection"
        mapping = found or import_file.propose_mapping(columns, ACCOUNTING_FIELDS)

    fhash = file_hash(content)
    analysis = AccountingAnalysis(
        company=company,
        fichier_nom=fichier_nom,
        fichier_hash=fhash,
        deja_importe=import_repository.confirmed_file(db, company.id, TYPE_IMPORT, fhash)
        is not None,
        feuilles=feuilles,
        feuille=feuille,
        ligne_entete=header_index + 1,
        colonnes=columns,
        mapping=mapping,
        mapping_source=source,
        erreurs_mapping=import_file.mapping_errors(mapping, len(columns), ACCOUNTING_FIELDS),
    )
    if analysis.erreurs_mapping:
        return analysis  # pas de lecture des lignes tant que la correspondance est incomplète

    today = today or position_service.business_today()
    lines, ignored = [], 0
    for offset, row in enumerate(data):
        if all(is_blank(cell) for cell in row):
            continue
        cells = {
            code: row[index] if index < len(row) else None
            for code, index in mapping.items()
            if index is not None
        }
        numero = header_index + 2 + offset
        account = None if _is_ignored(cells) else _bank_account_of(cells, journals)
        if account is None:
            ignored += 1
            analysis.lignes_ignorees.append(
                import_file.ignored_line(numero, _ignored_reason(cells, journals), row)
            )
            continue
        lines.append(_read_entry(numero, cells, mapping, account, today))

    _mark_duplicates(db, company.id, lines)
    analysis.lignes = lines
    analysis.resume = _summarise(lines, ignored)
    return analysis


# --- Confirmation ----------------------------------------------------------------------------------


@dataclass
class EntriesImport:
    batch: ImportBatch
    nb_importees: int
    nb_erreurs_ecartees: int
    nb_doublons_ecartes: int
    par_compte: list[AccountTotal]
    periode_debut: date | None
    periode_fin: date | None
    modele_enregistre: bool


def _save_mapping(db: Session, company: Company, analysis: AccountingAnalysis) -> bool:
    """Mémorise la correspondance (par en-tête) pour les prochains exports de la société."""
    headers = import_file.headers_of(analysis.mapping, analysis.colonnes)
    if headers is None:
        return False
    saved = accounting_repository.latest_company_mapping(db, company.id, TYPE_IMPORT)
    if saved is None:
        accounting_repository.add(
            db,
            ColumnMapping(
                type=TYPE_IMPORT,
                company_id=company.id,
                nom=f"Export Sage {company.nom}",
                mapping=headers,
            ),
        )
    else:
        saved.mapping = headers
    return True


def confirm_entries(
    db: Session,
    *,
    company_id: int,
    fichier_nom: str,
    content: bytes,
    mapping: Mapping | None,
    feuille: str | None,
    garder_doublons: list[int] | None,
    ecarter_erreurs: bool,
    acteur_id: int,
    lignes_choisies: list[int] | None = None,
    ip: str | None = None,
    today: date | None = None,
) -> EntriesImport:
    """Enregistre l'export : le fichier est analysé à nouveau (sans état entre les deux temps)."""
    analysis = analyse_entries(
        db,
        company_id=company_id,
        fichier_nom=fichier_nom,
        content=content,
        mapping=mapping,
        feuille=feuille,
        today=today,
    )
    if analysis.erreurs_mapping:
        raise ConflictError(" ".join(analysis.erreurs_mapping))
    if analysis.deja_importe:
        raise ConflictError("Ce fichier a déjà été importé pour cette société.")
    errors = [line for line in analysis.lignes if line.statut == "Erreur"]
    by_number = {line.numero: line for line in analysis.lignes}
    if lignes_choisies is not None:
        # Cases cochées (08/10/2026) : seules ces lignes sont importées
        chosen = set(lignes_choisies)
        _check_chosen(chosen, by_number)
        lines = [line for line in analysis.lignes if line.numero in chosen]
        keep = {line.numero for line in lines if line.statut == "Doublon"}
    else:
        if errors and not ecarter_erreurs:
            plural = "s" if len(errors) > 1 else ""
            raise ConflictError(
                f"{len(errors)} ligne{plural} en erreur : corrigez l'export dans Sage, "
                f"ou confirmez en l'écartant{plural}."
            )
        keep = set(garder_doublons or [])
        for numero in sorted(keep):
            line = by_number.get(numero)
            if line is None or line.doublon_de is None:
                raise ConflictError(
                    f"La ligne {numero} n'est pas identique à une autre ligne du fichier : "
                    "elle ne peut pas être gardée."
                )
        lines = [line for line in analysis.lignes if line.statut == "Valide" or line.numero in keep]
    if not lines:
        raise ConflictError("Aucune écriture de banque à importer dans ce fichier.")

    company = analysis.company
    nb_doublons = sum(1 for line in analysis.lignes if line.statut == "Doublon") - len(keep)
    nb_ecartees = len(analysis.lignes) - len(lines) - nb_doublons
    batch = ImportBatch(
        type=TYPE_IMPORT,
        company_id=company.id,
        fichier_nom=fichier_nom,
        fichier_hash=analysis.fichier_hash,
        statut="Confirmé",
        nb_lignes=len(lines),
        nb_erreurs=len(errors),
        nb_doublons=nb_doublons,
        user_id=acteur_id,
    )
    accounting_repository.add(db, batch)
    db.flush()
    for line in lines:
        accounting_repository.add(
            db,
            AccountingEntry(
                import_batch_id=batch.id,
                company_id=company.id,
                bank_account_id=line.bank_account_id,
                journal=line.journal,
                compte=line.compte,
                date_ecriture=line.date_ecriture,
                libelle=line.libelle,
                reference=line.reference,
                debit=line.debit,
                credit=line.credit,
                montant=line.montant,
                numero_piece=line.numero_piece,
                echeance=line.echeance,
                tiers=line.tiers,
                hash_ligne=line.hash_ligne,
            ),
        )
    modele = _save_mapping(db, company, analysis)
    # Les doublons gardés comptent comme des lignes importées
    summary = _summarise([replace(line, statut="Valide") for line in lines], 0)
    audit_service.log(
        db,
        user_id=acteur_id,
        action="import_ecritures",
        entite="import_batch",
        entite_id=batch.id,
        apres={
            "fichier": fichier_nom,
            "ecritures": len(lines),
            "par_compte": {
                f"{item.bank_code} · {item.journal}": item.nb for item in summary.par_compte
            },
            "erreurs_ecartees": len(errors),
            "doublons_gardes": sorted(keep),
            "lignes_decochees": None if lignes_choisies is None else nb_ecartees,
        },
        ip=ip,
    )
    try:
        db.commit()
    except IntegrityError as error:  # même fichier confirmé en même temps
        db.rollback()
        raise ConflictError("Ce fichier a déjà été importé pour cette société.") from error
    return EntriesImport(
        batch=batch,
        nb_importees=len(lines),
        nb_erreurs_ecartees=len(errors),
        nb_doublons_ecartes=nb_doublons,
        par_compte=summary.par_compte,
        periode_debut=summary.periode_debut,
        periode_fin=summary.periode_fin,
        modele_enregistre=modele,
    )


def _check_chosen(chosen: set[int], by_number: dict[int, "EntryLine"]) -> None:
    """Une ligne cochée doit exister, ne pas être en erreur ni déjà importée."""
    for numero in sorted(chosen):
        line = by_number.get(numero)
        if line is None:
            raise ConflictError(f"Ligne {numero} : introuvable dans le fichier.")
        if line.statut == "Erreur":
            raise ConflictError(f"Ligne {numero} : en erreur, à corriger dans Sage ou à décocher.")
        if line.statut == "Doublon" and line.doublon_de is None:
            raise ConflictError(f"Ligne {numero} : déjà importée, elle ne peut pas être cochée.")


# --- Lecture ---------------------------------------------------------------------------------------

PAGE_SIZE = 50
CENT = Decimal("0.01")


@dataclass
class EntriesPage:
    total: int
    page: int
    taille: int
    total_debit: Decimal
    total_credit: Decimal
    # (écriture, code de sa banque), de la plus récente à la plus ancienne
    ecritures: list[tuple[AccountingEntry, str | None]]


def list_entries(
    db: Session,
    company_id: int,
    *,
    bank_account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    statut: str | None = None,
    q: str | None = None,
    page: int = 1,
) -> EntriesPage:
    """Une page d'écritures de la société (50 par page) ; les totaux portent sur tout le filtre."""
    company = _company(db, company_id)
    if date_from and date_to and date_from > date_to:
        raise ConflictError("La date de début doit précéder la date de fin.")
    query = accounting_repository.entries_query(
        company.id,
        bank_account_id=bank_account_id,
        date_from=date_from,
        date_to=date_to,
        statut=statut,
        q=q,
    )
    total, debit, credit = accounting_repository.totals_of_entries(db, query)
    rows = accounting_repository.page_of_entries(
        db, query, offset=(page - 1) * PAGE_SIZE, limit=PAGE_SIZE
    )
    return EntriesPage(
        total=total,
        page=page,
        taille=PAGE_SIZE,
        total_debit=debit.quantize(CENT),
        total_credit=credit.quantize(CENT),
        ecritures=rows,
    )


def get_entry(
    db: Session, entry_id: int
) -> tuple[AccountingEntry, str | None, ImportBatch | None, str | None]:
    row = accounting_repository.get_entry(db, entry_id)
    if row is None:
        raise NotFoundError("Écriture introuvable.")
    return row


def list_imports(db: Session, company_id: int) -> list[tuple]:
    """Journal des imports comptables de la société."""
    company = _company(db, company_id)
    return accounting_repository.list_imports(db, company.id, TYPE_IMPORT)
