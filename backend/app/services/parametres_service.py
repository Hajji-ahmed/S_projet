"""Paramètres (P16.3, 14/10/2026) : grille de rapprochement et modèles de mapping d'import.

La grille (`reconciliation_rules`) est lue par le moteur à chaque lancement
(`reconciliation_service.grille`) : une modification vaut pour le prochain lancement, les
propositions déjà en attente gardent leur score jusqu'à la relance. Toutes les lignes envoyées sont
vérifiées avant la première écriture (tout ou rien) ; chaque règle modifiée est auditée
(`modification_parametre`, avant / après).
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import ColumnMapping, ReconciliationRule
from app.repositories import parametres_repository
from app.services import audit_service
from app.services.errors import ConflictError, NotFoundError

CRITERES = ("REFERENCE", "MONTANT", "DATE", "LIBELLE", "TIERS")
SEUILS = ("SEUIL_PROPOSITION", "SEUIL_FORT", "ECART_AMBIGUITE")
FENETRE = "FENETRE"
# Recherche élargie (20/10/2026) : de 31 à 366 jours
FENETRE_ELARGIE = "FENETRE_ELARGIE"
# Espèces (27/10/2026) : de 0 à 10 jours
FENETRE_ESPECES = "FENETRE_ESPECES"
CENT = Decimal("100")

# Ce que chaque règle laisse modifier, pour l'écran : points, jours, activation
GENRES = {
    **{code: "critere" for code in CRITERES},
    **{code: "seuil" for code in SEUILS},
    FENETRE: "fenetre",
    FENETRE_ELARGIE: "fenetre",
    FENETRE_ESPECES: "fenetre",
}


@dataclass(frozen=True)
class Changement:
    code: str
    poids: Decimal
    tolerance: Decimal | None
    actif: bool


def _etat(rule: ReconciliationRule) -> dict:
    return {"poids": rule.poids, "tolerance": rule.tolerance, "actif": rule.actif}


def _jours(valeur: Decimal | None, mini: int, maxi: int, quoi: str) -> Decimal:
    if valeur is None or valeur != valeur.to_integral_value() or not mini <= valeur <= maxi:
        raise ConflictError(f"{quoi} : un nombre entier de jours entre {mini} et {maxi}.")
    return Decimal(int(valeur))


def _points(valeur: Decimal, quoi: str, *, mini: Decimal = Decimal("0")) -> Decimal:
    if not mini <= valeur <= CENT:
        raise ConflictError(f"{quoi} : entre {mini} et 100 points.")
    return valeur.quantize(Decimal("0.01"))


def verifier(rules: dict[str, ReconciliationRule], changements: list[Changement]) -> dict:
    """Valeurs finales de chaque règle modifiée, ou ConflictError (règle pure, sans écriture)."""
    finales: dict[str, dict] = {}
    for changement in changements:
        rule = rules.get(changement.code)
        if rule is None:
            raise NotFoundError(f"Paramètre inconnu : {changement.code}.")
        if changement.code in finales:
            raise ConflictError(f"Paramètre envoyé deux fois : {changement.code}.")
        genre = GENRES.get(changement.code)
        quoi = rule.libelle
        if genre == "critere":
            poids = _points(changement.poids, quoi)
            tolerance = (
                _jours(changement.tolerance, 0, 30, quoi)
                if changement.code == "DATE"
                else rule.tolerance
            )
            finales[changement.code] = {
                "poids": poids,
                "tolerance": tolerance,
                "actif": changement.actif,
            }
        elif genre == "seuil":
            mini = Decimal("1") if changement.code == "SEUIL_PROPOSITION" else Decimal("0")
            finales[changement.code] = {
                "poids": _points(changement.poids, quoi, mini=mini),
                "tolerance": rule.tolerance,
                # Un seuil reste toujours actif : désactivé, il reprendrait sa valeur par défaut
                "actif": True,
            }
        elif genre == "fenetre":
            # Recherche élargie (20/10/2026) : de 31 à 366 jours ; fenêtre normale : de 1 à 60
            # Espèces (27/10/2026) : de 0 à 10 jours
            mini, maxi = {FENETRE_ELARGIE: (31, 366), FENETRE_ESPECES: (0, 10)}.get(
                changement.code, (1, 60)
            )
            finales[changement.code] = {
                "poids": rule.poids,
                "tolerance": _jours(changement.tolerance, mini, maxi, quoi),
                "actif": True,
            }
        else:
            raise ConflictError(f"Le paramètre {changement.code} ne se modifie pas à l'écran.")

    def valeur(code: str) -> Decimal | None:
        if code in finales:
            return finales[code]["poids"]
        return rules[code].poids if code in rules else None

    proposition, fort = valeur("SEUIL_PROPOSITION"), valeur("SEUIL_FORT")
    if proposition is not None and fort is not None and fort < proposition:
        raise ConflictError(
            "Le score d'une forte correspondance ne peut pas être inférieur au score minimal "
            "d'une proposition."
        )
    actifs = [
        code
        for code in CRITERES
        if code in rules
        and (finales[code]["actif"] if code in finales else rules[code].actif)
        and (finales[code]["poids"] if code in finales else rules[code].poids) > 0
    ]
    if "MONTANT" not in actifs:
        raise ConflictError("Le critère Montant doit rester actif : il fonde chaque proposition.")
    return finales


def grille(db: Session) -> list[ReconciliationRule]:
    """Les règles dans l'ordre de l'écran : critères, fenêtre, seuils."""
    ordre = {
        code: index
        for index, code in enumerate(
            (*CRITERES, FENETRE, FENETRE_ESPECES, FENETRE_ELARGIE, *SEUILS)
        )
    }
    return sorted(
        parametres_repository.rules(db), key=lambda rule: ordre.get(rule.code, len(ordre))
    )


def modifier_grille(
    db: Session, changements: list[Changement], *, acteur_id: int, ip: str | None
) -> list[ReconciliationRule]:
    rules = {rule.code: rule for rule in parametres_repository.rules(db, lock=True)}
    finales = verifier(rules, changements)
    for code, valeurs in finales.items():
        rule = rules[code]
        avant = _etat(rule)
        if avant == valeurs:
            continue
        rule.poids, rule.tolerance, rule.actif = (
            valeurs["poids"],
            valeurs["tolerance"],
            valeurs["actif"],
        )
        audit_service.log(
            db,
            user_id=acteur_id,
            action="modification_parametre",
            entite="reconciliation_rule",
            entite_id=rule.id,
            avant={"code": code, **avant},
            apres={"code": code, **valeurs},
            ip=ip,
        )
    db.commit()
    return grille(db)


# --- Modèles de mapping d'import ------------------------------------------------------------------


def mappings(db: Session) -> list[ColumnMapping]:
    return parametres_repository.mappings(db)


def supprimer_mapping(db: Session, mapping_id: int, *, acteur_id: int, ip: str | None) -> None:
    """Le prochain import de cette banque (ou de cette société pour Sage) refait la détection
    des colonnes, et la mémorise de nouveau à la confirmation."""
    mapping = parametres_repository.mapping(db, mapping_id)
    if mapping is None:
        raise NotFoundError("Modèle de mapping introuvable.")
    avant = {
        "type": mapping.type,
        "nom": mapping.nom,
        "banque": mapping.bank.code if mapping.bank else None,
        "company_id": mapping.company_id,
        "mapping": mapping.mapping,
    }
    parametres_repository.delete(db, mapping)
    audit_service.log(
        db,
        user_id=acteur_id,
        action="suppression_mapping",
        entite="column_mapping",
        entite_id=mapping_id,
        avant=avant,
        ip=ip,
    )
    db.commit()
