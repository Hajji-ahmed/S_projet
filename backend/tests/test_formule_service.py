"""Formules des cellules Prévisions : mêmes cas que `frontend/lib/formule.test.ts`."""

from decimal import Decimal

import pytest

from app.services.formule_service import est_formule, evaluer


def test_est_formule():
    assert est_formule("=1+2")
    assert est_formule("  =1+2")
    assert not est_formule("1+2")


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("=1200+350,50", "1550.50"),
        ("=5000-1200", "3800.00"),
        ("=100-250", "-150.00"),
        ("=100+50*2", "200.00"),
        ("=(1000+500)*2", "3000.00"),
        ("=((2+3)*(4-1))/5", "3.00"),
        ("= 1 200 000,50 + 0.25", "1200000.75"),
        ("=1 200+1 000", "2200.00"),
        ("=−500+200", "-300.00"),
        ("=-(100+50)", "-150.00"),
        ("=2×3÷4", "1.50"),
        ("=0,1+0,2", "0.30"),
        ("=10/3", "3.33"),
        ("=0,005*1", "0.01"),
        ("=-0,005*1", "-0.01"),
        ("=0,004", "0.00"),
        ("=-0,004", "0.00"),
    ],
)
def test_evaluer(texte, attendu):
    assert evaluer(texte) == Decimal(attendu)


@pytest.mark.parametrize(
    "texte",
    ["", "1+2", "=", "=12++", "=12+", "=(1+2", "=1+2)", "=abc", "=1,2,3", "=5/0", "=5/(2-2)"],
)
def test_formule_fausse(texte):
    assert evaluer(texte) is None


def test_texte_demesure_refuse_sans_planter():
    assert evaluer("=" + "(" * 100 + "1" + ")" * 100) is None
    assert evaluer("=" + "-" * 100_000 + "1") is None
