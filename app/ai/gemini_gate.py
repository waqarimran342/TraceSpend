"""The ONLY file that talks to Gemini. One attempt, daily cap, cache, no retries."""
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import date

import cv2
import numpy as np


class AIBudgetError(Exception):
    pass


def _db():
    con = sqlite3.connect(os.getenv("SPENDTRACE_DB", "spendtrace.db"))
    con.execute("CREATE TABLE IF NOT EXISTS ai_usage(day TEXT PRIMARY KEY, count INTEGER NOT NULL)")
    con.execute("CREATE TABLE IF NOT EXISTS ai_cache(sha TEXT PRIMARY KEY, resp TEXT NOT NULL, created TEXT NOT NULL)")
    return con


def daily_cap():
    try:
        return max(0, int(os.getenv("DAILY_CAP", "8")))
    except ValueError:
        return 8


def requests_left():
    with closing(_db()) as con:
        row = con.execute("SELECT count FROM ai_usage WHERE day=?", (date.today().isoformat(),)).fetchone()
    return max(0, daily_cap() - (row[0] if row else 0))


def contact_sheet(crops):
    """crops: list of (crop_id, image). Stacks labeled crops into ONE JPEG so a batch costs ONE request."""
    rows = []
    for cid, img in crops:
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        k = 70 / max(img.shape[0], 1)
        img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
        label = np.full((img.shape[0], 110, 3), 255, np.uint8)
        cv2.putText(label, cid, (8, img.shape[0] // 2 + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
        rows.append(np.hstack([label, img]))
    width = max(r.shape[1] for r in rows)
    padded = [cv2.copyMakeBorder(r, 6, 6, 0, width - r.shape[1], cv2.BORDER_CONSTANT, value=(255, 255, 255))
              for r in rows]
    ok, buf = cv2.imencode(".jpg", np.vstack(padded), [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes()


def _call_model(image_bytes, prompt):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"),
                          http_options=types.HttpOptions(timeout=20000))
    resp = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL"),
        contents=[types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"), prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return resp.text


def ask(image_bytes, prompt, schema_keys):
    if not os.getenv("GEMINI_API_KEY") or not os.getenv("GEMINI_MODEL"):
        raise AIBudgetError("Gemini key or model is not configured. Showing local result.")

    sha = hashlib.sha256(image_bytes + prompt.encode()).hexdigest()
    with closing(_db()) as con:
        hit = con.execute("SELECT resp FROM ai_cache WHERE sha=?", (sha,)).fetchone()
    if hit:  # cache hit costs nothing
        return json.loads(hit[0])

    if requests_left() <= 0:
        raise AIBudgetError("Daily AI budget used. Showing local result.")

    with closing(_db()) as con, con:  # count BEFORE the call: failed calls still count
        con.execute("INSERT INTO ai_usage(day,count) VALUES(?,1) "
                    "ON CONFLICT(day) DO UPDATE SET count=count+1", (date.today().isoformat(),))
    try:
        data = json.loads(_call_model(image_bytes, prompt))  # one attempt, no retries
    except Exception:
        raise AIBudgetError("The AI request failed or timed out. Showing local result.")

    if not isinstance(data, dict) or not set(data).issubset(set(schema_keys)):
        raise AIBudgetError("The AI response was invalid and was discarded. Showing local result.")

    with closing(_db()) as con, con:
        con.execute("INSERT OR REPLACE INTO ai_cache(sha,resp,created) VALUES(?,?,?)",
                    (sha, json.dumps(data), date.today().isoformat()))
    return data