"""Decimal money/quantity helpers.

Prices and quantities must never be floats. We store them as SQLAlchemy Numeric
and round explicitly with defined precision.
"""
from decimal import ROUND_HALF_UP, Decimal

MONEY_Q = Decimal("0.01")      # currency: 2 dp
QTY_Q = Decimal("0.001")       # quantity: 3 dp (kg to the gram)


def D(value) -> Decimal:
    """Coerce anything sane into a Decimal without float contamination."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money(value) -> Decimal:
    return D(value).quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def qty(value) -> Decimal:
    return D(value).quantize(QTY_Q, rounding=ROUND_HALF_UP)
