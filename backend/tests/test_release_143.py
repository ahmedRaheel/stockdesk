"""1.43 contracts: safe product media, offline conflict decisions and migration preview."""
import base64
import io
from PIL import Image
from fastapi import HTTPException
import pytest
from pydantic import ValidationError

from app.api.storefront import ProductPhoto, optimized_photo
from app.api.operations_extensions import OfflineResolution
from app.api.migration_wizard import LegacyBatch, Commit, fingerprint


def encoded_image(mode='RGB', size=(240, 160)):
    stream = io.BytesIO()
    Image.new(mode, size, (34, 78, 120)).save(stream, format='PNG')
    return base64.b64encode(stream.getvalue()).decode('ascii')


def test_product_photo_safely_converted_to_bounded_jpeg():
    result, width, height = optimized_photo(encoded_image())
    assert (width, height) == (240, 160)
    assert result[:3] == b'\xff\xd8\xff'
    assert len(result) < 600_000
    with Image.open(io.BytesIO(result)) as image:
        assert image.format == 'JPEG' and not image.getexif()


def test_photo_enforces_source_validation_and_pixel_limits():
    with pytest.raises(HTTPException) as exc:
        optimized_photo('not-valid-base64%%')
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        optimized_photo(base64.b64encode(b'GIF89a').decode())
    assert exc.value.status_code in (415,422)


def test_photo_rejects_oversized_base64_payload():
    with pytest.raises(ValidationError):
        ProductPhoto(image_base64='x' * 2_800_001)


def test_rejected_replay_resolution_requires_reference_only_for_replacement():
    assert OfflineResolution(resolution='dismissed', notes='Duplicate customer draft').replacement_sale is None
    assert OfflineResolution(resolution='replaced', replacement_sale='sale-123', notes='Reprocessed at the till').replacement_sale == 'sale-123'
    with pytest.raises(ValidationError):
        OfflineResolution(resolution='replaced', notes='Missing POS sale')
    with pytest.raises(ValidationError):
        OfflineResolution(resolution='dismissed', replacement_sale='sale-123', notes='Incorrectly linked')


def test_migration_preview_token_matches_identical_commit():
    preview = LegacyBatch(products_csv='sku,name,price\nA,Soap,10.00\n', location_id=None)
    token = fingerprint('tenant-a', preview)
    commit = Commit(**preview.model_dump(), preview_token=token, request_id='request-143')
    assert fingerprint('tenant-a', commit) == token
    assert fingerprint('tenant-b', commit) != token
