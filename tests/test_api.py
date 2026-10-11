import io

import cv2
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from tools.make_samples import make

client = TestClient(app)


def png_bytes(img):
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def post(data, name="receipt.png"):
    return client.post("/upload", files={"file": (name, data, "image/png")})


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_rejects_bad_files():
    small = io.BytesIO()
    Image.new("RGB", (300, 400), "white").save(small, "PNG")
    assert post(small.getvalue()).status_code == 400
    assert post(b"not an image").status_code == 400
    assert post(b"").status_code == 400
    assert post(b"0" * (10 * 1024 * 1024 + 1)).status_code == 400


def test_full_flow_wrong_total_is_flagged_and_fixable():
    img, truth = make(2, "wrong_total", "shadow")
    r = post(png_bytes(img), name="../../bad name?.png")
    assert r.status_code == 200
    body = r.json()
    assert any(f["title"] == "Grand total does not match" for f in body["findings"])
    assert body["preliminary"] is True
    rid = body["id"]
    total = next(l for l in body["lines"] if l["kind"] == "total")
    # the printed total (1,039.60) is deliberately wrong; the correct one is 810 + 129.60 = 939.60
    fixed = client.post(f"/receipt/{rid}/edit", json={"line_id": total["id"], "amount": "939.60"}).json()
    assert not any(f["title"] == "Grand total does not match" for f in fixed["findings"])
    assert client.get(f"/receipt/{rid}/image/current").status_code == 200


def test_edit_validation():
    img, _ = make(1, "clean", "none")
    body = post(png_bytes(img)).json()
    rid, lid = body["id"], body["lines"][0]["id"]
    assert client.post(f"/receipt/{rid}/edit", json={"line_id": lid, "amount": "abc"}).status_code == 400
    assert client.post(f"/receipt/{rid}/edit", json={"line_id": lid, "amount": "-5"}).status_code == 400
    assert client.post(f"/receipt/{rid}/tax", json={"tax_rate": 150}).status_code == 400
    assert client.get("/receipt/../etc/passwd").status_code in (404, 422)


def test_restore_and_split():
    img, _ = make(5, "clean", "fade")
    body = post(png_bytes(img)).json()
    rid = body["id"]
    r = client.post(f"/receipt/{rid}/restore").json()
    assert r["restore"]["after"] >= r["restore"]["before"] or not r["restore"]["adopted"]
    items = [l for l in r["lines"] if l["kind"] == "item"]
    s = client.post(f"/receipt/{rid}/split", json={
        "people": ["Ali", "Sara"], "assignments": {str(items[0]["id"]): ["Ali"], str(items[1]["id"]): ["Sara"]}})
    assert s.status_code == 200 and set(s.json()["owes"]) == {"Ali", "Sara"}
    dup = client.post(f"/receipt/{rid}/split", json={"people": ["Ali", "ali"], "assignments": {}})
    assert dup.status_code == 400