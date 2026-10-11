from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal(0)


def split_bill(lines, assignments, people):
    """assignments: {line_id(str): [names]}. Tax/fees/discount are shared in proportion to items."""
    shares = {p: ZERO for p in people}
    unassigned = ZERO
    for l in lines:
        if l["kind"] != "item":
            continue
        names = [n for n in assignments.get(str(l["id"]), []) if n in shares]
        amount = Decimal(l["amount"])
        if not names:
            unassigned += amount
            continue
        for n in names:
            shares[n] += amount / len(names)

    extras = ZERO
    for l in lines:
        if l["kind"] in ("tax", "fee"):
            extras += Decimal(l["amount"])
        elif l["kind"] == "discount":
            extras -= abs(Decimal(l["amount"]))

    base = sum(shares.values(), ZERO)
    owes = {}
    for p in people:
        extra = extras * shares[p] / base if base else ZERO
        owes[p] = (shares[p] + extra).quantize(CENT, ROUND_HALF_UP)

    if base and people:  # put any rounding leftover on the person with the biggest share
        diff = (base + extras).quantize(CENT, ROUND_HALF_UP) - sum(owes.values(), ZERO)
        biggest = max(people, key=lambda p: shares[p])
        owes[biggest] += diff

    return {"owes": {p: str(v) for p, v in owes.items()},
            "unassigned": str(unassigned.quantize(CENT)),
            "extras": str(extras.quantize(CENT, ROUND_HALF_UP))}