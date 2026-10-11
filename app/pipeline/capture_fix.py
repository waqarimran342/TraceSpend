import cv2
import numpy as np

MIN_WIDTH = 1200
MAX_SIDE = 3000
TIPS = "Retake the photo: lay the receipt flat, use good light, get closer, and avoid glare."


def quality_problems(bgr):
    """Return a list of plain-English problems (empty list = photo is usable)."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    k = 1000 / max(gray.shape)
    small = cv2.resize(gray, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    problems = []
    if cv2.Laplacian(small, cv2.CV_64F).var() < 10:
        problems.append("The photo is too blurry.")
    mean = small.mean()
    if mean < 60:
        problems.append("The photo is too dark.")
    if mean > 250:
        problems.append("The photo is washed out (glare or overexposed).")
    if problems:
        problems.append(TIPS)
    return problems


def _order(pts):
    pts = np.array(pts, dtype="float32")
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[s.argmin()], pts[d.argmin()], pts[s.argmax()], pts[d.argmax()]], dtype="float32")


def find_quad(bgr):
    """Find the receipt rectangle (handles tilt). Returns 4 points or None."""
    h, w = bgr.shape[:2]
    k = 800 / max(h, w)
    small = cv2.resize(bgr, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (7, 7), 0)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 0.25 * small.shape[0] * small.shape[1]:
        return None
    return _order(cv2.boxPoints(cv2.minAreaRect(c))) / k


def warp(bgr, quad):
    tl, tr, br, bl = quad
    w = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    h = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(quad, dst)
    return cv2.warpPerspective(bgr, M, (w, h), borderValue=(255, 255, 255)), M


def enhance(bgr):
    """Remove shadows (divide by estimated background) and sharpen text."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    bg = cv2.medianBlur(cv2.dilate(gray, np.ones((7, 7), np.uint8)), 31)
    norm = cv2.divide(gray, bg, scale=255)
    blur = cv2.GaussianBlur(norm, (0, 0), 2)
    return cv2.addWeighted(norm, 1.5, blur, -0.5, 0)


def fix(bgr):
    """Returns (fixed grayscale image, 3x3 transform matrix original -> fixed)."""
    quad = find_quad(bgr)
    if quad is None:
        warped, M = bgr, np.eye(3)
    else:
        warped, M = warp(bgr, quad)
    h, w = warped.shape[:2]
    s = max(1.0, MIN_WIDTH / w)
    if max(h, w) * s > MAX_SIDE:
        s = MAX_SIDE / max(h, w)
    if abs(s - 1.0) > 1e-6:
        warped = cv2.resize(warped, None, fx=s, fy=s,
                            interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
        M = np.diag([s, s, 1.0]) @ M
    return enhance(warped), M