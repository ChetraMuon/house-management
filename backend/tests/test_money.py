from decimal import Decimal

import pytest

from app.money import calculate_change, change_breakdown, q


def test_change_exact():
    assert calculate_change(Decimal("100.00"), Decimal("100")) == Decimal("0.00")


def test_change_normal():
    assert calculate_change(Decimal("86.35"), Decimal("100")) == Decimal("13.65")


def test_insufficient_payment():
    with pytest.raises(ValueError):
        calculate_change(Decimal("50"), Decimal("49.99"))


def test_breakdown_sums_back():
    change = Decimal("13.65")
    parts = change_breakdown(change)
    assert sum(Decimal(p["denomination"]) * p["count"] for p in parts) == change
    assert parts[0] == {"denomination": "10.00", "count": 1}


def test_breakdown_zero():
    assert change_breakdown(Decimal("0")) == []


def test_rounding():
    assert q(Decimal("1.005")) == Decimal("1.01")
