from decimal import Decimal

from app.audit.split import split_bill

LINES = [
    {"id": 0, "kind": "item", "amount": "600.00"},
    {"id": 1, "kind": "item", "amount": "400.00"},
    {"id": 2, "kind": "tax", "amount": "160.00"},
    {"id": 3, "kind": "fee", "amount": "40.00"},
]


def test_tax_and_fees_shared_proportionally():
    r = split_bill(LINES, {"0": ["Ali"], "1": ["Sara"]}, ["Ali", "Sara"])
    assert r["owes"] == {"Ali": "720.00", "Sara": "480.00"}


def test_shared_item_and_total_adds_up():
    r = split_bill(LINES, {"0": ["Ali", "Sara"], "1": ["Sara"]}, ["Ali", "Sara"])
    assert sum(Decimal(v) for v in r["owes"].values()) == Decimal("1200.00")


def test_unassigned_items_reported():
    r = split_bill(LINES, {"0": ["Ali"]}, ["Ali", "Sara"])
    assert r["unassigned"] == "400.00"