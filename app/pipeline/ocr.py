import os
import shutil

import pytesseract
from pytesseract import Output

candidate = os.getenv("TESSERACT_CMD")
if not candidate:
    candidate = shutil.which("tesseract")
if not candidate and os.name == "nt":
    win_default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(win_default):
        candidate = win_default
if candidate:
    pytesseract.pytesseract.tesseract_cmd = candidate


def read_words(gray):
    """OCR a grayscale image. Returns word dicts with box (x,y,w,h) and confidence."""
    d = pytesseract.image_to_data(gray, config="--oem 3 --psm 6", output_type=Output.DICT)
    words = []
    for i, text in enumerate(d["text"]):
        text = text.strip()
        conf = float(d["conf"][i])
        if not text or conf < 0:
            continue
        words.append({
            "id": len(words), "text": text, "conf": conf,
            "x": int(d["left"][i]), "y": int(d["top"][i]),
            "w": int(d["width"][i]), "h": int(d["height"][i]),
            "line": f"{d['block_num'][i]}-{d['par_num'][i]}-{d['line_num'][i]}",
        })
    return words


def mean_conf(words):
    return round(sum(w["conf"] for w in words) / len(words), 1) if words else 0.0