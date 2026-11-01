"""Validates content-addressed, re-encoded business images."""
import io
import hashlib
import pytest
from PIL import Image
from fastapi import HTTPException
from app.features.brand_images import normalize_logo


def png_bytes(size=(80, 40), color=(100, 35, 22)):
    buffer = io.BytesIO()
    Image.new('RGB', size, color).save(buffer, format='PNG')
    return buffer.getvalue()


def test_logo_is_content_addressed_and_deterministic():
    first_hash, first = normalize_logo(png_bytes())
    second_hash, second = normalize_logo(png_bytes())
    assert first == second
    assert first_hash == second_hash == hashlib.sha256(first).hexdigest()
    with Image.open(io.BytesIO(first)) as image:
        assert image.format == 'PNG'
        assert image.size == (80, 40)


def test_jpeg_normalizes_to_png():
    buff = io.BytesIO()
    Image.new('RGB', (64, 32), (20, 30, 40)).save(buff, 'JPEG')
    _, content = normalize_logo(buff.getvalue())
    assert content.startswith(b'\x89PNG\r\n\x1a\n')


@pytest.mark.parametrize('payload', [b'', b'not a picture', b'x' * (512*1024 + 1)])
def test_invalid_logo_rejected(payload):
    with pytest.raises(HTTPException):
        normalize_logo(payload)


def test_oversized_pixel_dimensions_rejected():
    with pytest.raises(HTTPException):
        normalize_logo(png_bytes((1201, 1200)))
