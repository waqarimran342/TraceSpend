from app.audit.engine import run_audit


def L(i, label, kind, amount, conf=95):
    return {"id": i, "label": label, "kind": kind, "amount": amount, "conf": conf}


CLEAN = [L(0, "Biryani", "item", "450.00"), L(1, "Naan", "item", "300.00"),
         L(2, "Subtotal", "subtotal", "750.00"), L(3, "GST", "tax", "120.00"),
         L(4, "Total", "total", "870.00")]


def titles(findings):
    return [f["title"] for f in findings if f["severity"] in ("red", "amber")]


def test_clean_receipt_has_no_findings():
    assert titles(run_audit(CLEAN, tax_rate=16)) == []


def test_wrong_total():
    lines = [dict(l) for l in CLEAN]
    lines[4]["amount"] = "900.00"
    assert "Grand total does not match" in titles(run_audit(lines, tax_rate=16))


def test_wrong_tax_rate():
    lines = [dict(l) for l in CLEAN]
    lines[3]["amount"] = "200.00"
    assert any("Tax does not match" in t for t in titles(run_audit(lines, tax_rate=16)))


def test_items_vs_subtotal():
    lines = [dict(l) for l in CLEAN]
    lines[2]["amount"] = "800.00"
    assert "Items do not add up to the subtotal" in titles(run_audit(lines))


def test_duplicate_item():
    lines = CLEAN[:2] + [L(9, "Biryani", "item", "450.00")]
    assert "Possible duplicate item" in titles(run_audit(lines))


def test_fee_is_reported_as_info_and_counted_in_total():
    lines = CLEAN[:4] + [L(5, "Service Charge", "fee", "50.00"), L(6, "Total", "total", "920.00")]
    f = run_audit(lines, tax_rate=16)
    assert titles(f) == []
    assert any(x["severity"] == "info" for x in f)


def test_missing_fields_are_not_findings():
    assert run_audit([L(0, "Tea", "item", "80.00")]) == []


def test_rounding_tolerance():
    lines = [dict(l) for l in CLEAN]
    lines[4]["amount"] = "870.50"
    assert titles(run_audit(lines, tax_rate=16)) == []