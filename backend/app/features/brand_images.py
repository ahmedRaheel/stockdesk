"""Pure logo validation, decoding, normalization and content hashing."""
import hashlib
import io
from PIL import Image, ImageOps, UnidentifiedImageError
from ..rules import fail
MAX_INPUT = 512 * 1024
MAX_PIXELS = 1_440_000

def normalize_logo(raw: bytes) -> tuple[str, bytes]:
    if not raw or len(raw) > MAX_INPUT:
        fail("Logo must be a PNG or JPEG of no more than 512 KB.", 413)
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in ("PNG", "JPEG"):
                fail("Only PNG and JPEG logo images are supported.")
            if source.width * source.height > MAX_PIXELS:
                fail("Logo exceeds the 1.44 megapixel limit.")
            source.load()
            corrected = ImageOps.exif_transpose(source)
            output = corrected.convert("RGBA") if "A" in corrected.getbands() else corrected.convert("RGB")
            buffer = io.BytesIO()
            output.save(buffer, format="PNG", optimize=True)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        fail("The supplied image is invalid or damaged.")
    data = buffer.getvalue()
    if len(data) > 524288:
        fail("Processed logo exceeds 512 KB. Choose a simpler or smaller image.", 413)
    return hashlib.sha256(data).hexdigest(), data

