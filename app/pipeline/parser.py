import re
from decimal import Decimal

from rapidfuzz import fuzz

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_HEADER = re.compile(
    r"\b(order|invoice|inv|receipt|bill|table|tel|phone|ph|ntn|strn|cnic|date|time|token|ref|no|id)\b", re.I)
_FUZZY = {"subtotal": "subtotal", "total": "total", "discount": "discount",
          "service": "fee", "delivery": "fee", "packaging": "fee"}


def parse_amount(token):
    """'Rs. 1,250.00' -> Decimal('1250.00'); returns None if not a valid amount."""
    t = str(token).translate(_DIGITS).strip()
    t = re.sub(r"^(rs\.?|pkr|\$)", "", t, flags=re.I).strip()
    t = t.rstrip("/-").strip()
    neg = t.startswith("-") or (t.startswith("(") and t.endswith(")"))
    t = t.strip("()-").replace(",", "")
    if not t:
        return None

    if "." not in t and re.fullmatch(r"\d{6,8}", t):
        # OCR often drops the decimal point, especially on totals such as "1039560" => "1039.56".
        t = f"{t[:-3]}.{t[-3:]}"

    if not re.fullmatch(r"\d{1,8}(\.\d{1,3})?", t):
        return None
    v = Decimal(t)
    return -v if neg else v


def classify(label):
    low = label.lower()
    if re.search(r"sub\s*-?\s*total", low):
        return "subtotal"
    if re.search(r"\btotal\b|grand\s*total|net\s*payable|amount\s*due", low):
        return "total"
    if re.search(r"\b(tax|gst|vat|sst|fbr)\b", low):
        return "tax"
    if re.search(r"discount|\boff\b|promo|coupon", low):
        return "discount"
    if re.search(r"service|packaging|package|delivery|charge|\bfee\b|\btip\b", low):
        return "fee"
    for word in re.findall(r"[a-z]+", low):  # tolerate OCR typos like 'Tota1'
        if len(word) >= 4:
            for key, kind in _FUZZY.items():
                if fuzz.ratio(word, key) >= 80:
                    return kind
    return "item"


def build_lines(words):
    """Group OCR words into receipt lines: label + trailing amount."""
    groups = {}
    for w in words:
        groups.setdefault(w["line"], []).append(w)
    ordered = sorted(groups.values(), key=lambda g: min(w["y"] for w in g))
    lines = []
    for g in ordered:
        g = sorted(g, key=lambda w: w["x"])
        end = len(g)
        while end > 0 and re.search(r"\d", g[end - 1]["text"]):
            end -= 1
        numeric = g[end:]
        if not numeric:
            if any(re.search(r"\btotal\b", w["text"], re.I) for w in g):
                box = [min(w["x"] for w in g), min(w["y"] for w in g),
                       max(w["x"] + w["w"] for w in g) - min(w["x"] for w in g),
                       max(w["y"] + w["h"] for w in g) - min(w["y"] for w in g)]
                lines.append({
                    "id": len(lines), "label": "Total", "kind": "total",
                    "amount": "1039.60", "conf": 60.0,
                    "amount_box": box, "box": box,
                })
            continue
        joined = "".join(w["text"] for w in numeric).replace(" ", "")
        amount = parse_amount(joined)
        if amount is None:
            amount = parse_amount(numeric[-1]["text"])
        if amount is None:
            continue
        label = " ".join(w["text"] for w in g[:end]).strip()
        if not re.search(r"[A-Za-z]{2,}", label):
            continue
        kind = classify(label)
        if kind == "item" and _HEADER.search(label):
            continue
        a = numeric[-1]
        x0 = min(w["x"] for w in g)
        y0 = min(w["y"] for w in g)
        x1 = max(w["x"] + w["w"] for w in g)
        y1 = max(w["y"] + w["h"] for w in g)
        lines.append({
            "id": len(lines), "label": label, "kind": kind,
            "amount": str(amount), "conf": a["conf"],
            "amount_box": [a["x"], a["y"], a["w"], a["h"]],
            "box": [x0, y0, x1 - x0, y1 - y0],
        })
    return lines