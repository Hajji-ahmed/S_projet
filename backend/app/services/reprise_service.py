"""Reprise d'un état de rapprochement tenu sous Excel (décision du 27/10/2026).

La comptabilité donne, à une date, deux listes : les opérations bancaires et les écritures Sage
encore non rapprochées. Tout le reste du compte jusqu'à cette date est rapproché : SIMTIS le met
dans UN rapprochement validé, d'origine « Reprise », qui doit s'équilibrer au centime (le contrôle
qui prouve que les deux listes vont ensemble) et s'annule comme les autres.

Les deux fichiers ont les colonnes DATE · LIBELLE · DEBIT · CREDIT (plus N° DE PIECES pour la
comptabilité), vues de l'autre côté : le DEBIT du fichier est un crédit du relevé (et un crédit de
Sage) ; SIMTIS inverse donc les deux colonnes. Une ligne sans montant est une ligne déjà pointée
dont le montant a été vidé : elle n'est pas gardée.

Tout est vérifié avant la première écriture ; au moindre problème (ligne introuvable, reprise
déséquilibrée, ligne en écart) rien n'est écrit. Une ligne gardée qui est déjà rapprochée ou
proposée dans SIMTIS n'est pas touchée (elle est seulement signalée).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import AccountingEntry, BankTransaction, ReconciliationMatch
from app.models import ReconciliationMatchItem as Item
from app.repositories import (
    account_repository,
    auth_repository,
    reconciliation_repository,
    reprise_repository,
)
from app.services import audit_service, reconciliation_service
from app.services.errors import ConflictError, NotFoundError
from app.services.import_file import read_sheet
from app.services.normalization_service import is_blank, label_key, parse_amount

ACTION = "reprise_rapprochement"
ORIGINE = "Reprise"
# Une date du fichier peut différer de celle du relevé (un impayé du 01/08 passé le 31/07)
TOLERANCE_JOURS = 3
# Lignes d'en-tête cherchées en haut de chaque feuille
LIGNES_EN_TETE = 30
ZERO = Decimal("0")


# --- Lecture des fichiers -------------------------------------------------------------------------


@dataclass(frozen=True)
class LigneFichier:
    """Une ligne d'un des deux fichiers, montants déjà dans le sens de SIMTIS."""

    ligne: int  # numéro de ligne Excel
    date: date | None
    libelle: str
    piece: str | None
    debit: Decimal | None  # None : ligne sans montant (déjà pointée)
    credit: Decimal | None

    @property
    def sans_montant(self) -> bool:
        return self.debit is None and self.credit is None

    def __str__(self) -> str:
        quand = self.date.strftime("%d/%m/%Y") if self.date else "sans date"
        montant = f"débit {self.debit or ZERO} · crédit {self.credit or ZERO}"
        piece = f" · pièce {self.piece}" if self.piece else ""
        return f"ligne {self.ligne} · {quand} · {self.libelle}{piece} · {montant}"


def cle(texte: str | None) -> str:
    """Libellé ou pièce comparable : majuscules sans accents, sans espaces ni ponctuation (le
    relevé importé écrit « ENCAISSEMENTCHEQUEN0576794… », le fichier « ENCAISSEMENT CHEQUE N … »)."""
    return label_key(texte).replace(" ", "")


def _date(valeur: object) -> date | None:
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur
    return None


def _colonnes(en_tete: tuple) -> dict[str, int]:
    trouvees: dict[str, int] = {}
    for index, cellule in enumerate(en_tete):
        nom = label_key(str(cellule)) if not is_blank(cellule) else ""
        if nom in ("DATE", "LIBELLE", "DEBIT", "CREDIT"):
            trouvees.setdefault(nom, index)
        elif "PIECE" in nom:
            trouvees.setdefault("PIECE", index)
    return trouvees


def _tableau(contenu: bytes, avec_piece: bool, feuille: str | None) -> tuple[str, int, dict, list]:
    """Feuille, ligne d'en-tête et colonnes du tableau : DATE · LIBELLE · DEBIT · CREDIT, avec
    une colonne de pièce pour la comptabilité et sans pour la banque. Sans `feuille`, la première
    feuille qui convient."""
    noms, _, _ = read_sheet(contenu, None)
    for nom in [feuille] if feuille else noms:
        _, _, lignes = read_sheet(contenu, nom)
        for index, ligne in enumerate(lignes[:LIGNES_EN_TETE]):
            colonnes = _colonnes(ligne)
            if {"DATE", "LIBELLE", "DEBIT", "CREDIT"} <= colonnes.keys() and (
                "PIECE" in colonnes
            ) == avec_piece:
                return nom, index, colonnes, lignes
    quoi = "DATE, LIBELLE, DEBIT, CREDIT" + (" et N° DE PIECES" if avec_piece else "")
    raise ConflictError(f"Aucune feuille du fichier n'a les colonnes {quoi}.")


def _montant(valeur: object) -> Decimal | None:
    try:
        montant = parse_amount(valeur)
    except ValueError:
        return None
    return montant or None  # 0 = vide


def lire(
    contenu: bytes, *, avec_piece: bool, feuille: str | None = None
) -> tuple[str, list[LigneFichier]]:
    """Lignes d'un fichier, DEBIT et CREDIT inversés (sens de SIMTIS). Une ligne sans date ni
    pièce (titre, total, solde) est ignorée ; une ligne de comptabilité sans date mais avec sa
    pièce et son montant est gardée."""
    nom, en_tete, colonnes, lignes = _tableau(contenu, avec_piece, feuille)
    resultat = []
    for numero, cellules in enumerate(lignes[en_tete + 1 :], start=en_tete + 2):

        def valeur(colonne: str, cellules: tuple = cellules) -> object:
            index = colonnes.get(colonne)
            return cellules[index] if index is not None and index < len(cellules) else None

        quand = _date(valeur("DATE"))
        piece = None if is_blank(valeur("PIECE")) else str(valeur("PIECE")).strip()
        if quand is None and piece is None:
            continue
        libelle = "" if is_blank(valeur("LIBELLE")) else " ".join(str(valeur("LIBELLE")).split())
        # Fichiers vus de l'autre côté : leur DEBIT est un crédit dans SIMTIS
        debit, credit = _montant(valeur("CREDIT")), _montant(valeur("DEBIT"))
        if quand is None and debit is None and credit is None:
            continue
        resultat.append(LigneFichier(numero, quand, libelle, piece, debit, credit))
    return nom, resultat


# --- Lignes de SIMTIS retrouvées (règles pures) ---------------------------------------------------


@dataclass(frozen=True)
class LigneSimtis:
    id: int
    date: date
    cle: str
    piece: str
    debit: Decimal
    credit: Decimal


def _meme_montant(ligne: LigneFichier, simtis: LigneSimtis) -> bool:
    return (ligne.debit or ZERO, ligne.credit or ZERO) == (simtis.debit, simtis.credit)


def _ecart(ligne: LigneFichier, simtis: LigneSimtis) -> int:
    return abs((simtis.date - ligne.date).days) if ligne.date else 0


def associer(
    lignes: list[LigneFichier], simtis: list[LigneSimtis], *, par_piece: bool
) -> tuple[dict[int, int], list[LigneFichier]]:
    """Ligne du fichier (numéro Excel) → ligne de SIMTIS, chacune prise une fois ; et les lignes
    introuvables. Une ligne sans montant n'est pas cherchée (déjà pointée).

    Banque : même libellé, même montant, date à `TOLERANCE_JOURS` près (la plus proche).
    Comptabilité : même pièce et même montant, de préférence le même libellé, la date la plus
    proche ; sans pièce, comme la banque. Les meilleures correspondances passent d'abord (même
    date, même libellé), pour qu'une ligne voisine ne prenne pas la place d'une ligne exacte.
    """
    par_cle: dict[str, list[LigneSimtis]] = defaultdict(list)
    par_num: dict[str, list[LigneSimtis]] = defaultdict(list)
    for ligne in simtis:
        par_cle[ligne.cle].append(ligne)
        if ligne.piece:
            par_num[ligne.piece].append(ligne)
    prises: set[int] = set()
    trouvees: dict[int, int] = {}
    a_chercher = [ligne for ligne in lignes if not ligne.sans_montant]

    def candidates(ligne: LigneFichier, strict: bool) -> list[LigneSimtis]:
        if par_piece and ligne.piece:
            liste = [
                s
                for s in par_num.get(cle(ligne.piece), [])
                if not strict or (s.cle == cle(ligne.libelle) and _ecart(ligne, s) == 0)
            ]
        else:
            liste = [
                s
                for s in par_cle.get(cle(ligne.libelle), [])
                if _ecart(ligne, s) <= (0 if strict else TOLERANCE_JOURS)
            ]
        liste = [s for s in liste if s.id not in prises and _meme_montant(ligne, s)]
        return sorted(liste, key=lambda s: (s.cle != cle(ligne.libelle), _ecart(ligne, s), s.id))

    for strict in (True, False):
        for ligne in a_chercher:
            if ligne.ligne in trouvees:
                continue
            liste = candidates(ligne, strict)
            if liste:
                trouvees[ligne.ligne] = liste[0].id
                prises.add(liste[0].id)
    introuvables = [ligne for ligne in a_chercher if ligne.ligne not in trouvees]
    return trouvees, introuvables


# --- Bilan et application -------------------------------------------------------------------------


@dataclass
class Bilan:
    compte: str
    jusqu_au: date
    feuille_banque: str
    feuille_compta: str
    lignes_banque: int = 0
    lignes_compta: int = 0
    banque_sans_montant: int = 0
    compta_sans_montant: int = 0
    gardees_operations: list[int] = field(default_factory=list)
    gardees_ecritures: list[int] = field(default_factory=list)
    operations: list[int] = field(default_factory=list)
    ecritures: list[int] = field(default_factory=list)
    total_operations: Decimal = ZERO  # crédit − débit des opérations rapprochées
    total_ecritures: Decimal = ZERO  # montant (crédit − débit Sage) des écritures rapprochées
    deja_rapprochees: list[str] = field(default_factory=list)  # lignes gardées, signalées
    problemes: list[str] = field(default_factory=list)  # bloquent l'application
    code: str | None = None
    propositions_rejetees: list[int] = field(default_factory=list)

    @property
    def ecart(self) -> Decimal:
        return self.total_operations + self.total_ecritures


def _ligne_operation(tx: BankTransaction) -> LigneSimtis:
    return LigneSimtis(tx.id, tx.date_operation, cle(tx.libelle), "", tx.debit, tx.credit)


def _ligne_ecriture(entry: AccountingEntry) -> LigneSimtis:
    return LigneSimtis(
        entry.id, entry.date_ecriture, cle(entry.libelle), cle(entry.numero_piece),
        entry.debit, entry.credit,
    )  # fmt: skip


def _actives(db: Session, tx_ids: list[int], entry_ids: list[int]) -> list[ReconciliationMatch]:
    return [
        match
        for match in reconciliation_repository.matches_touching(db, tx_ids, entry_ids)
        if any(item.actif for item in match.items)
    ]


def analyser(
    db: Session,
    *,
    numero_compte: str,
    banque: bytes,
    compta: bytes,
    jusqu_au: date,
    feuille_banque: str | None = None,
    feuille_compta: str | None = None,
) -> Bilan:
    """Ce que la reprise ferait, sans rien écrire."""
    account = account_repository.get_by_numero(db, numero_compte)
    if account is None:
        raise NotFoundError(f"Compte bancaire introuvable : {numero_compte}.")
    nom_banque, lignes_banque = lire(banque, avec_piece=False, feuille=feuille_banque)
    nom_compta, lignes_compta = lire(compta, avec_piece=True, feuille=feuille_compta)
    bilan = Bilan(account.numero, jusqu_au, nom_banque, nom_compta)
    bilan.lignes_banque, bilan.lignes_compta = len(lignes_banque), len(lignes_compta)
    bilan.banque_sans_montant = sum(ligne.sans_montant for ligne in lignes_banque)
    bilan.compta_sans_montant = sum(ligne.sans_montant for ligne in lignes_compta)

    operations = reprise_repository.operations_jusqu_au(db, account.id, jusqu_au)
    ecritures = reprise_repository.ecritures_jusqu_au(db, account.id, jusqu_au)
    gardees_tx, perdues_tx = associer(
        lignes_banque, [_ligne_operation(tx) for tx in operations], par_piece=False
    )
    gardees_ecr, perdues_ecr = associer(
        lignes_compta, [_ligne_ecriture(e) for e in ecritures], par_piece=True
    )
    bilan.problemes += [f"Banque, introuvable dans SIMTIS : {ligne}" for ligne in perdues_tx]
    bilan.problemes += [f"Comptabilité, introuvable dans SIMTIS : {ligne}" for ligne in perdues_ecr]
    bilan.gardees_operations = sorted(gardees_tx.values())
    bilan.gardees_ecritures = sorted(gardees_ecr.values())

    gardees = set(bilan.gardees_operations)
    for tx in operations:
        if tx.id in gardees:
            if tx.statut != "Non rapprochée":
                bilan.deja_rapprochees.append(f"Opération n° {tx.id} ({tx.statut}) : {tx.libelle}")
        elif tx.statut == "Écart":
            bilan.problemes.append(f"Opération n° {tx.id} en écart : {tx.libelle}")
        elif tx.statut != "Rapprochée" and not tx.en_cours and tx.remplacee_par_id is None:
            bilan.operations.append(tx.id)
            bilan.total_operations += tx.montant
    gardees = set(bilan.gardees_ecritures)
    for entry in ecritures:
        if entry.id in gardees:
            if entry.statut != "Non rapprochée":
                bilan.deja_rapprochees.append(
                    f"Écriture n° {entry.id} ({entry.statut}) : {entry.libelle}"
                )
        elif entry.statut == "Écart":
            bilan.problemes.append(f"Écriture n° {entry.id} en écart : {entry.libelle}")
        elif entry.statut != "Rapprochée":
            bilan.ecritures.append(entry.id)
            bilan.total_ecritures += reconciliation_service.montant_rapprochement(entry)

    if not bilan.operations or not bilan.ecritures:
        bilan.problemes.append("Rien à rapprocher d'un côté : aucune reprise possible.")
    if bilan.ecart != 0:
        bilan.problemes.append(
            f"La reprise ne s'équilibre pas : opérations {bilan.total_operations}, écritures "
            f"{bilan.total_ecritures}, écart {bilan.ecart}. Les deux fichiers ne vont pas ensemble."
        )
    return bilan


def appliquer(
    db: Session,
    *,
    numero_compte: str,
    banque: bytes,
    compta: bytes,
    noms_fichiers: tuple[str, str],
    jusqu_au: date,
    motif: str,
    email: str,
    feuille_banque: str | None = None,
    feuille_compta: str | None = None,
) -> Bilan:
    """Crée le rapprochement de reprise, tout ou rien ; refusé au moindre problème du bilan."""
    texte = " ".join(motif.split())
    if not texte:
        raise ConflictError("Indiquez le motif de la reprise.")
    user = auth_repository.get_user_by_email(db, email)
    if user is None or not user.actif:
        raise NotFoundError(f"Utilisateur introuvable ou inactif : {email}.")
    account = account_repository.get_by_numero(db, numero_compte)
    if account is None:
        raise NotFoundError(f"Compte bancaire introuvable : {numero_compte}.")
    reconciliation_service._company(db, account.company_id, lock=True)
    bilan = analyser(
        db,
        numero_compte=numero_compte,
        banque=banque,
        compta=compta,
        jusqu_au=jusqu_au,
        feuille_banque=feuille_banque,
        feuille_compta=feuille_compta,
    )
    if bilan.problemes:
        raise ConflictError(
            f"Reprise refusée, rien n'a été écrit ({len(bilan.problemes)} problème(s)) :\n"
            + "\n".join(bilan.problemes)
        )

    # Les propositions en attente de ces lignes sont rejetées (un rapprochement validé n'en
    # contient aucune : ses lignes sont déjà « Rapprochée »)
    for match in _actives(db, bilan.operations, bilan.ecritures):
        if match.statut != "Proposée":
            raise ConflictError(f"La correspondance n° {match.id} est déjà validée.")
        avant = reconciliation_service._snapshot(match)
        reconciliation_service._release(db, match, "Rejetée", texte, user.id)
        audit_service.log(
            db,
            user_id=user.id,
            action="rejet_rapprochement",
            entite=reconciliation_service.ENTITE,
            entite_id=match.id,
            avant=avant,
            apres=reconciliation_service._snapshot(match),
        )
        bilan.propositions_rejetees.append(match.id)

    operations = {
        tx.id: tx for tx in reprise_repository.operations_jusqu_au(db, account.id, jusqu_au)
    }
    ecritures = {e.id: e for e in reprise_repository.ecritures_jusqu_au(db, account.id, jusqu_au)}
    match = ReconciliationMatch(
        company_id=account.company_id,
        type="N-N",
        statut="Proposée",
        origine=ORIGINE,
        commentaire=texte,
        detail_score={
            "explication": (
                f"Reprise de l'état de rapprochement au {jusqu_au.strftime('%d/%m/%Y')} : "
                f"{len(bilan.operations)} opérations ↔ {len(bilan.ecritures)} écritures"
            )
        },
        items=[
            *(
                Item(bank_transaction_id=i, montant_affecte=abs(operations[i].montant), actif=True)
                for i in bilan.operations
            ),
            *(
                Item(
                    accounting_entry_id=i,
                    montant_affecte=abs(reconciliation_service.montant_rapprochement(ecritures[i])),
                    actif=True,
                )
                for i in bilan.ecritures
            ),
        ],
    )
    reconciliation_repository.add(db, match)
    db.flush()
    reconciliation_service._validate(db, match, user.id)
    bilan.code = match.code
    audit_service.log(
        db,
        user_id=user.id,
        action=ACTION,
        entite=reconciliation_service.ENTITE,
        entite_id=match.id,
        apres={
            "code": match.code,
            "compte": account.numero,
            "jusqu_au": jusqu_au.isoformat(),
            "motif": texte,
            "fichier_banque": noms_fichiers[0],
            "fichier_compta": noms_fichiers[1],
            "nb_operations": len(bilan.operations),
            "nb_ecritures": len(bilan.ecritures),
            "total_operations": bilan.total_operations,
            "total_ecritures": bilan.total_ecritures,
            "operations_gardees": bilan.gardees_operations,
            "ecritures_gardees": bilan.gardees_ecritures,
            "propositions_rejetees": bilan.propositions_rejetees,
            "operations": bilan.operations,
            "ecritures": bilan.ecritures,
        },
    )
    reconciliation_service._commit(db)
    return bilan
