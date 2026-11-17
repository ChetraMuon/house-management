"""Pure money helpers (no database) so they are easy to unit test."""
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")

# Denominations used to tell the cashier how to hand back change (USD).
DENOMINATIONS = [
    Decimal("100"), Decimal("50"), Decimal("20"), Decimal("10"), Decimal("5"), Decimal("1"),
    Decimal("0.50"), Decimal("0.25"), Decimal("0.10"), Decimal("0.05"), Decimal("0.01"),
]


def q(value) -> Decimal:
    """Round to 2 decimals using bank-style 'half up'."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_change(total: Decimal, received: Decimal) -> Decimal:
    total, received = q(total), q(received)
    if received < total:
        raise ValueError(f"Insufficient payment: short by {q(total - received)}")
    return q(received - total)


def change_breakdown(change: Decimal) -> list[dict]:
    """Greedy breakdown of change into bills/coins, e.g. [{'denomination': '20.00', 'count': 2}]."""
    remaining = q(change)
    result = []
    for d in DENOMINATIONS:
        count = int(remaining // d)
        if count:
            result.append({"denomination": str(q(d)), "count": count})
            remaining = q(remaining - d * count)
    return result
