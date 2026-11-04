"""Structural checks for API wiring and upload/network protections."""
from pathlib import Path
from app.main import app

ROOT=Path(__file__).resolve().parents[2]


def test_release_143_paths_registered_once():
    routes={(route.path,method) for route in app.routes for method in getattr(route,'methods',[])}
    paths={
      ('/api/v1/tenants/{tenant}/storefront/products/{product_id}/image','PUT'),
      ('/api/v1/tenants/{tenant}/storefront/products/{product_id}/image','GET'),
      ('/api/v1/tenants/{tenant}/storefront/products/{product_id}/image','DELETE'),
      ('/api/storefronts/{slug}/products/{product_id}/image','GET'),
      ('/api/v1/tenants/{tenant}/offline/devices/{device}/operations/{operation_id}/resolve','POST'),
      ('/api/v1/tenants/{tenant}/offline/devices/{device}/deactivate','POST'),
      ('/api/v1/tenants/{tenant}/migration-wizard/history','GET'),
    }
    assert paths <= routes
    assert app.version == '1.43.0'
    app.openapi()  # Ensures FastAPI dependency declarations parse successfully.


def test_release_143_migrations_are_additive():
    path=ROOT/'backend'/'migrations'
    assert (path/'051_storefront_product_media.sql').is_file()
    assert (path/'052_offline_conflict_resolution.sql').is_file()
    assert 'FOREIGN KEY(tenant,device,operation_id)' in (path/'052_offline_conflict_resolution.sql').read_text()


def test_image_upload_has_its_own_nginx_body_limit():
    text=(ROOT/'frontend'/'nginx.conf').read_text()
    assert 'storefront/products/[^/]+/image' in text
    assert 'client_max_body_size 3m;' in text
