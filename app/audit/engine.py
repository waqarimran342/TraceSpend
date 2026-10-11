from decimal import Decimal, ROUND_HALF_UP

from rapidfuzz import fuzz

TOL = Decimal("1")  # about 1 rupee of rounding tolerance
ZERO = Decimal(0)
CENT = Decimal("0.01")


def effective(lines, overrides):
    """Apply user corrections (never touches the original OCR values)."""
    out = []
    for l in lines:
        l = dict(l)
        if str(l["id"]) in overrides:
            l["amount"] = overrides[str(l["id"])]
        out.append(l)
    return out


def _amt(l):
    return Decimal(l["amount"])


def _fmt(d):
    return f"{d.quantize(CENT, ROUND_HALF_UP):,.2f}"


def run_audit(lines, tax_rate=None):
    """Plain deterministic checks. A missing field is 'not found', never a finding."""
    findings = []

    def add(severity, title, explain, arithmetic, line_ids):
        findings.append({"id": len(findings), "severity": severity, "title": title,
                         "explain": explain, "arithmetic": arithmetic, "line_ids": line_ids})

    items = [l for l in lines if l["kind"] == "item"]
    fees = [l for l in lines if l["kind"] == "fee"]

    def first(kind):
        return next((l for l in lines if l["kind"] == kind), None)

    sub, tax, disc, total = first("subtotal"), first("tax"), first("discount"), first("total")
    items_sum = sum((_amt(l) for l in items), ZERO)

    # 1. items vs subtotal
    if sub and items and abs(items_sum - _amt(sub)) > TOL:
        add("red", "Items do not add up to the subtotal",
            "The listed items sum to a different amount than the printed subtotal.",
            " + ".join(_fmt(_amt(l)) for l in items) + f" = {_fmt(items_sum)}, but subtotal says "
            f"{_fmt(_amt(sub))} (difference {_fmt(abs(items_sum - _amt(sub)))})",
            [l["id"] for l in items] + [sub["id"]])

    base = _amt(sub) if sub else (items_sum if items else None)

    # 2. tax recalculation
    if tax and tax_rate is not None and base is not None:
        expected = base * Decimal(str(tax_rate)) / 100
        if abs(expected - _amt(tax)) > TOL:
            add("red", f"Tax does not match {tax_rate}%",
                "Recalculated tax differs from the printed tax.",
                f"{_fmt(base)} x {tax_rate}% = {_fmt(expected)}, but tax says {_fmt(_amt(tax))}",
                [tax["id"]] + ([sub["id"]] if sub else []))

    # 3. grand total
    if total and base is not None:
        expected = base
        parts = [_fmt(base)]
        if tax:
            expected += _amt(tax)
            parts.append("+ " + _fmt(_amt(tax)) + " tax")
        if disc:
            expected -= abs(_amt(disc))
            parts.append("- " + _fmt(abs(_amt(disc))) + " discount")
        for f in fees:
            expected += _amt(f)
            parts.append("+ " + _fmt(_amt(f)) + f" {f['label'].lower()}")
        if abs(expected - _amt(total)) > TOL:
            ids = [total["id"]] + [l["id"] for l in (sub, tax, disc) if l] + [f["id"] for f in fees]
            add("red", "Grand total does not match",
                "Subtotal plus tax and fees (minus discount) differs from the printed total.",
                " ".join(parts) + f" = {_fmt(expected)}, but total says {_fmt(_amt(total))} "
                f"(difference {_fmt(abs(expected - _amt(total)))})", ids)

    # 4. duplicates / near-duplicates
    seen = set()
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            if a["id"] in seen or b["id"] in seen:
                continue
            if _amt(a) == _amt(b) and fuzz.ratio(a["label"].lower(), b["label"].lower()) >= 90:
                seen.update([a["id"], b["id"]])
                add("amber", "Possible duplicate item",
                    "Same item and same price appear twice. Check if it was really ordered twice.",
                    f"'{a['label']}' {_fmt(_amt(a))} appears twice", [a["id"], b["id"]])

    # 5. extra charges (information, not an error)
    for f in fees:
        pct = f" ({(_amt(f) / base * 100).quantize(Decimal('0.1'))}% of subtotal)" if base else ""
        add("info", f"Extra charge: {f['label']}",
            "Service, packaging and delivery charges are easy to miss. Make sure you agreed to it.",
            f"{f['label']}: {_fmt(_amt(f))}{pct}", [f["id"]])
    return findings