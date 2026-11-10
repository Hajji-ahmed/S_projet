"""Formules des cellules de montant du tableau Prévisions (« =1 200,50+350*2 »).

Même règle que `frontend/lib/formule.ts` : opérations + − * / et parenthèses, calcul exact en
fractions (jamais de float), résultat arrondi au centime, 0,005 vers le haut en valeur absolue. Le
texte est lu par un petit analyseur : rien n'est exécuté. Le serveur recalcule chaque formule reçue
pour que la formule gardée (10/11/2026) donne toujours le montant enregistré.
"""

import re
from decimal import Decimal
from fractions import Fraction

PROFONDEUR_MAX = 50
_NOMBRE = re.compile(r"(\d+)(?:[.,](\d+))?")
# Espaces (milliers, insécables) ignorés ; signes typographiques d'un copier-coller
_ESPACES = re.compile(r"[\s  ]")
_REMPLACEMENTS = str.maketrans({"−": "-", "‑": "-", "–": "-", "×": "*", "÷": "/"})


def est_formule(texte: str) -> bool:
    return texte.strip().startswith("=")


def evaluer(texte: str) -> Decimal | None:
    """« =1200+350,50 » → Decimal("1550.50") ; pas une formule, formule fausse ou division par zéro
    → None."""
    if not est_formule(texte):
        return None
    corps = _ESPACES.sub("", texte.strip()[1:]).translate(_REMPLACEMENTS)
    if not corps:
        return None
    lecteur = _Lecteur(corps)
    valeur = lecteur.expression()
    if valeur is None or not lecteur.fini():
        return None
    return _centimes(valeur)


def _centimes(valeur: Fraction) -> Decimal:
    num = abs(valeur.numerator) * 100
    den = valeur.denominator
    cents, reste = divmod(num, den)
    if reste * 2 >= den:
        cents += 1
    signe = -1 if valeur < 0 and cents else 1
    return (Decimal(signe * cents) / 100).quantize(Decimal("0.01"))


class _Lecteur:
    def __init__(self, texte: str) -> None:
        self.texte = texte
        self.pos = 0
        self.profondeur = 0

    def fini(self) -> bool:
        return self.pos == len(self.texte)

    def _voir(self) -> str:
        return self.texte[self.pos] if self.pos < len(self.texte) else ""

    # expression := terme (('+' | '-') terme)*
    def expression(self) -> Fraction | None:
        gauche = self._terme()
        while gauche is not None and self._voir() in ("+", "-"):
            op = self.texte[self.pos]
            self.pos += 1
            droite = self._terme()
            if droite is None:
                return None
            gauche = gauche + droite if op == "+" else gauche - droite
        return gauche

    # terme := facteur (('*' | '/') facteur)*
    def _terme(self) -> Fraction | None:
        gauche = self._facteur()
        while gauche is not None and self._voir() in ("*", "/"):
            op = self.texte[self.pos]
            self.pos += 1
            droite = self._facteur()
            if droite is None or (op == "/" and droite == 0):
                return None
            gauche = gauche * droite if op == "*" else gauche / droite
        return gauche

    # facteur := ('-' | '+') facteur | '(' expression ')' | nombre
    def _facteur(self) -> Fraction | None:
        c = self._voir()
        if c in ("-", "+"):
            # Profondeur comptée aussi pour « ------1 » : pas de récursion sans limite
            self.profondeur += 1
            if self.profondeur > PROFONDEUR_MAX * 4:
                return None
            self.pos += 1
            valeur = self._facteur()
            self.profondeur -= 1
            return -valeur if valeur is not None and c == "-" else valeur
        if c == "(":
            self.profondeur += 1
            if self.profondeur > PROFONDEUR_MAX:
                return None
            self.pos += 1
            valeur = self.expression()
            if valeur is None or self._voir() != ")":
                return None
            self.pos += 1
            self.profondeur -= 1
            return valeur
        return self._nombre()

    # nombre := chiffres ((',' | '.') chiffres)?
    def _nombre(self) -> Fraction | None:
        lu = _NOMBRE.match(self.texte, self.pos)
        if lu is None:
            return None
        self.pos = lu.end()
        decimales = lu.group(2) or ""
        return Fraction(int(lu.group(1) + decimales), 10 ** len(decimales))
