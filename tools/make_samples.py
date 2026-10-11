"""Generate synthetic receipts with known ground truth. Run: python -m tools.make_samples"""
import random
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ITEMS = [("Chicken Biryani", 450), ("Zinger Burger", 520), ("French Fries", 180), ("Cold Drink", 90),
         ("Karahi Half", 1250), ("Garlic Naan", 40), ("Doodh Patti", 80), ("Pizza Small", 700),
         ("Pasta Alfredo", 600), ("Brownie", 250)]


def _font(size):
    for name in ("DejaVuSansMono.ttf", "cour.ttf", "LiberationMono-Regular.ttf", "Menlo.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _draw(rows, subtotal, tax, total):
    f, fb = _font(34), _font(40)
    height = 200 + len(rows) * 54 + 4 * 54 + 80
    im = Image.new("L", (760, height), 255)
    d = ImageDraw.Draw(im)
    d.text((380, 40), "FOOD HUB LAHORE", font=fb, fill=0, anchor="mm")
    d.text((380, 95), "Order No 4821", font=f, fill=0, anchor="mm")
    y = 150
    for name, price in rows:
        d.text((40, y), name, font=f, fill=0)
        d.text((720, y), f"{price:,.2f}", font=f, fill=0, anchor="ra")
        y += 54
    y += 14
    d.line((40, y, 720, y), fill=0, width=2)
    y += 22
    for label, value in (("Subtotal", subtotal), ("GST 16%", tax), ("Total", total)):
        d.text((40, y), label, font=f, fill=0)
        d.text((720, y), f"{value:,.2f}", font=f, fill=0, anchor="ra")
        y += 54
    return np.array(im)


def make(seed, kind="clean", aug="none"):
    """kind: clean | wrong_total | wrong_subtotal | duplicate | wrong_tax.
    aug: none | tilt | shadow | blur | fade. Returns (BGR image, printed values)."""
    rnd = random.Random(seed)
    items = rnd.sample(ITEMS, rnd.randint(3, 5))
    rows = list(items)
    subtotal = sum(p for _, p in items)
    if kind == "duplicate":
        rows.insert(1, rows[0])
    if kind == "wrong_subtotal":
        subtotal += rnd.choice([100, 150, 200])
    tax = round(subtotal * 0.16, 2)
    if kind == "wrong_tax":
        tax += rnd.choice([40, 60, 90])
    total = round(subtotal + tax, 2)
    if kind == "wrong_total":
        total += rnd.choice([100, 200, 300])

    g = _draw(rows, subtotal, tax, total).astype(np.float32)
    h, w = g.shape
    if aug == "shadow":
        g = g * np.linspace(1.0, 0.55, w)[None, :]
    if aug == "fade":
        g = 255 - (255 - g) * 0.4 + np.random.default_rng(seed).normal(0, 4, g.shape)
    g = np.clip(g, 0, 255).astype(np.uint8)
    if aug == "blur":
        g = cv2.GaussianBlur(g, (0, 0), 1.4)

    canvas = np.full((h + 160, w + 160), 80, np.uint8)
    canvas[80:80 + h, 80:80 + w] = g
    angle = rnd.uniform(-8, 8) if aug == "tilt" else 0
    M = cv2.getRotationMatrix2D((canvas.shape[1] / 2, canvas.shape[0] / 2), angle, 1.0)
    canvas = cv2.warpAffine(canvas, M, (canvas.shape[1], canvas.shape[0]), borderValue=80)
    return cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR), {"subtotal": subtotal, "tax": tax, "total": total}


if __name__ == "__main__":
    Path("samples").mkdir(exist_ok=True)
    combos = [("clean", "tilt"), ("wrong_total", "shadow"), ("duplicate", "none"),
              ("wrong_tax", "blur"), ("wrong_subtotal", "tilt"), ("clean", "fade")]
    for i, (kind, aug) in enumerate(combos, 1):
        img, truth = make(i, kind, aug)
        name = f"samples/{i}_{kind}_{aug}.png"
        cv2.imwrite(name, img)
        print(name, truth)