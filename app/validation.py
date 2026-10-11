import io
import re
from pathlib import Path

from PIL import Image, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
MIN_LONG_SIDE = 800
UPLOAD_DIR = Path("uploads")


class ValidationError(Exception):
    pass


def safe_name(name):
    name = Path(name or "receipt").name
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:80]


def validate_image(data):
    if len(data) == 0:
        raise ValidationError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise ValidationError("File is larger than 10 MB.")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise ValidationError("File is corrupt or not an image.")
    if img.format not in ALLOWED_FORMATS:
        raise ValidationError("Only JPG, PNG and WEBP images are accepted.")
    if max(img.size) < MIN_LONG_SIDE:
        raise ValidationError(
            f"Image is too small ({img.size[0]}x{img.size[1]}). "
            "Retake the photo closer, with the long side at least 800 px."
        )
    return img
