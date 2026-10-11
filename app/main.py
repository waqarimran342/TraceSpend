import json
import re
import uuid
from decimal import Decimal

import cv2
import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import ImageOps
from pydantic import BaseModel

from app.ai.gemini_gate import AIBudgetError, ask, contact_sheet, daily_cap, requests_left
from app.audit.engine import effective, run_audit
from app.audit.split import split_bill
from app.pipeline.capture_fix import fix, quality_problems
from app.pipeline.ocr import mean_conf, read_words
from app.pipeline.parser import build_lines, parse_amount
from app.pipeline.restore import restore
from app.validation import MAX_BYTES, UPLOAD_DIR, ValidationError, safe_name, validate_image

load_dotenv()

CONF_MIN = 85  # amounts read below this confidence stay yellow until the user confirms
EXT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}

app = FastAPI(title="SpendTrace")
app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------- storage helpers ----------
def _path(rid, suffix):
    if not re.fullmatch(r"[0-9a-f]{32}", rid):
        raise HTTPException(404, "Receipt not found")
    return UPLOAD_DIR / f"{rid}{suffix}"


def load(rid):
    p = _path(rid, ".json")
    if not p.exists():
        raise HTTPException(404, "Receipt not found")
    return json.loads(p.read_text())


def save(rid, data):
    _path(rid, ".json").write_text(json.dumps(data))


def current_image_path(d):
    return _path(d["id"], ".restored.png" if d["image"] == "restored" else ".fixed.png")


def view(d):
    lines = effective(d["lines"], d["overrides"])
    findings = run_audit(lines, d.get("tax_rate"))
    bad = {i for f in findings if f["severity"] in ("red", "amber") for i in f["line_ids"]}
    for l in lines:
        confirmed = str(l["id"]) in d["overrides"] or l["id"] in d["confirmed"]
        l["confirmed"] = confirmed
        if l["id"] in bad:
            l["status"] = "red"
        elif l["conf"] < CONF_MIN and not confirmed:
            l["status"] = "yellow"
        elif l["kind"] == "fee":
            l["status"] = "blue"
        else:
            l["status"] = "green"
    yellow = {l["id"] for l in lines if l["status"] == "yellow"}
    for f in findings:  # a finding built on a shaky number may just be an OCR misread
        f["uncertain"] = bool(set(f["line_ids"]) & yellow)
    return {"id": d["id"], "width": d["width"], "height": d["height"], "lines": lines,
            "findings": findings, "tax_rate": d.get("tax_rate"), "restored": d["restored"],
            "quality": {"mean_conf": d["mean_conf"]}, "preliminary": True,
            "ai_left": requests_left(), "ai_cap": daily_cap()}


# ---------- routes ----------
@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ai/status")
def ai_status():
    return {"ai_left": requests_left(), "ai_cap": daily_cap()}


@app.post("/upload")
def upload(file: UploadFile = File(...)):
    data = file.file.read(MAX_BYTES + 1)
    try:
        img = validate_image(data)
        fmt = img.format
        img = ImageOps.exif_transpose(img).convert("RGB")
        bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        problems = quality_problems(bgr)
        if problems:
            raise ValidationError(" ".join(problems))
    except ValidationError as e:
        raise HTTPException(400, str(e))

    UPLOAD_DIR.mkdir(exist_ok=True)
    rid = uuid.uuid4().hex
    (UPLOAD_DIR / f"{rid}.orig.{EXT[fmt]}").write_bytes(data)  # original is never modified
    fixed, M = fix(bgr)
    cv2.imwrite(str(UPLOAD_DIR / f"{rid}.fixed.png"), fixed)
    words = read_words(fixed)
    d = {"id": rid, "orig_ext": EXT[fmt], "orig_name": safe_name(file.filename),
         "width": int(fixed.shape[1]), "height": int(fixed.shape[0]), "transform": M.tolist(),
         "image": "fixed", "lines": build_lines(words), "mean_conf": mean_conf(words),
         "overrides": {}, "confirmed": [], "tax_rate": None, "restored": False}
    save(rid, d)
    return view(d)


@app.get("/receipt/{rid}")
def get_receipt(rid: str):
    return view(load(rid))


@app.get("/receipt/{rid}/image/{which}")
def get_image(rid: str, which: str):
    d = load(rid)
    if which == "original":
        p = _path(rid, f".orig.{d['orig_ext']}")
    elif which == "fixed":
        p = _path(rid, ".fixed.png")
    elif which == "restored":
        p = _path(rid, ".restored.png")
    else:
        p = current_image_path(d)
    if not p.exists():
        raise HTTPException(404, "Image not found")
    return FileResponse(p)


class Edit(BaseModel):
    line_id: int
    amount: str


@app.post("/receipt/{rid}/edit")
def edit(rid: str, body: Edit):
    d = load(rid)
    line = next((l for l in d["lines"] if l["id"] == body.line_id), None)
    if not line:
        raise HTTPException(404, "Line not found")
    v = parse_amount(body.amount)
    if v is None:
        raise HTTPException(400, "Enter a valid amount, for example 1250.00")
    if v < 0 and line["kind"] != "discount":
        raise HTTPException(400, "Negative amounts are only allowed for discounts.")
    d["overrides"][str(body.line_id)] = str(v)
    save(rid, d)
    return view(d)


class LineRef(BaseModel):
    line_id: int


@app.post("/receipt/{rid}/confirm")
def confirm(rid: str, body: LineRef):
    d = load(rid)
    if body.line_id not in d["confirmed"]:
        d["confirmed"].append(body.line_id)
    save(rid, d)
    return view(d)


class Tax(BaseModel):
    tax_rate: float | None = None


@app.post("/receipt/{rid}/tax")
def set_tax(rid: str, body: Tax):
    if body.tax_rate is not None and not (0 <= body.tax_rate <= 100):
        raise HTTPException(400, "Tax rate must be between 0 and 100.")
    d = load(rid)
    d["tax_rate"] = body.tax_rate
    save(rid, d)
    return view(d)


@app.post("/receipt/{rid}/restore")
def restore_receipt(rid: str):
    d = load(rid)
    fixed = cv2.imread(str(_path(rid, ".fixed.png")), cv2.IMREAD_GRAYSCALE)
    before = d["mean_conf"]
    restored = restore(fixed)
    cv2.imwrite(str(_path(rid, ".restored.png")), restored)
    words = read_words(restored)
    after = mean_conf(words)
    adopted = after >= before
    d["restored"] = True
    if adopted:
        d.update(image="restored", lines=build_lines(words), mean_conf=after, overrides={}, confirmed=[])
    save(rid, d)
    unreadable = [[w["x"], w["y"], w["w"], w["h"]] for w in words if w["conf"] < 30]
    out = view(d)
    out["restore"] = {"before": before, "after": after, "adopted": adopted, "unreadable": unreadable}
    return out


class SplitIn(BaseModel):
    people: list[str]
    assignments: dict[str, list[str]]


@app.post("/receipt/{rid}/split")
def split(rid: str, body: SplitIn):
    people = [p.strip() for p in body.people]
    if not people or any(not p for p in people):
        raise HTTPException(400, "Add at least one person, and no empty names.")
    if len({p.lower() for p in people}) != len(people):
        raise HTTPException(400, "Names must be unique.")
    d = load(rid)
    return split_bill(effective(d["lines"], d["overrides"]), body.assignments, people)


@app.post("/receipt/{rid}/ask-gemini")
def ask_gemini(rid: str):
    """Only runs on an explicit click. Sends cropped yellow amounts only. Never overwrites anything."""
    d = load(rid)
    v = view(d)
    img = cv2.imread(str(current_image_path(d)), cv2.IMREAD_GRAYSCALE)
    crops, yellow = [], {}
    for l in v["lines"]:
        if l["status"] != "yellow":
            continue
        x, y, w, h = l["amount_box"]
        crop = img[max(0, y - 6):y + h + 6, max(0, x - 6):x + w + 6]
        if crop.size:
            crops.append((f"L{l['id']}", crop))
            yellow[f"L{l['id']}"] = l
    if not crops:
        raise HTTPException(400, "No yellow items to check.")
    prompt = ("Each labeled crop is a small piece of a receipt showing one price. "
              "Read the text exactly as printed. Do NOT correct or guess. "
              "Return JSON only: {crop_id: reading}. Use null if unreadable.")
    try:
        resp = ask(contact_sheet(crops), prompt, list(yellow))
    except AIBudgetError as e:
        return {"ok": False, "message": str(e), "ai_left": requests_left()}
    suggestions = []
    for cid, l in yellow.items():
        reading = resp.get(cid)
        parsed = parse_amount(reading) if reading else None
        suggestions.append({"line_id": l["id"], "local": l["amount"], "ai": reading,
                            "agree": parsed is not None and parsed == Decimal(l["amount"])})
    return {"ok": True, "suggestions": suggestions, "ai_left": requests_left()}