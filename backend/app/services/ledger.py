"""Double-entry ledger helpers (PRD section 8).

Each economic event is posted as a balanced set of debit/credit rows that share a
`txn_group`. post() refuses to write an unbalanced transaction, so the ledger can
always be reconciled and is the financial source of truth (not Order.status).
"""
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import money
from app.models.common import LedgerDirection, utcnow
from app.models.finance import LedgerEntry


@dataclass
class Leg:
    account: str
    direction: LedgerDirection
    amount: Decimal
    memo: str | None = None


class UnbalancedTransaction(Exception):
    pass


def post(
    db: Session,
    *,
    txn_group: str,
    legs: list[Leg],
    order_id: int | None = None,
    currency: str = "INR",
) -> list[LedgerEntry]:
    debits = sum((money(l.amount) for l in legs if l.direction == LedgerDirection.DEBIT), money(0))
    credits = sum((money(l.amount) for l in legs if l.direction == LedgerDirection.CREDIT), money(0))
    if debits != credits:
        raise UnbalancedTransaction(
            f"debits {debits} != credits {credits} for txn {txn_group}"
        )
    rows = []
    now = utcnow()
    for leg in legs:
        row = LedgerEntry(
            txn_group=txn_group,
            order_id=order_id,
            account=leg.account,
            direction=leg.direction,
            amount=money(leg.amount),
            currency=currency,
            memo=leg.memo,
            at=now,
        )
        db.add(row)
        rows.append(row)
    return rows


def account_balance(db: Session, account: str, order_id: int | None = None) -> Decimal:
    """Net balance = credits - debits for an account (optionally one order)."""
    stmt = select(LedgerEntry).where(LedgerEntry.account == account)
    if order_id is not None:
        stmt = stmt.where(LedgerEntry.order_id == order_id)
    bal = money(0)
    for row in db.scalars(stmt):
        amt = money(row.amount)
        bal += amt if row.direction == LedgerDirection.CREDIT else -amt
    return bal
