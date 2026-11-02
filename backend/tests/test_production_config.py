from app.production import production_errors, require_production_configuration
import pytest

BASE = {'APP_ENV':'production','APP_ORIGIN':'https://shop.example.com','COOKIE_SECURE':'true',
        'DATABASE_URL':'postgresql://stockdesk:secret@db:5432/stockdesk',
        'ADMIN_PASSWORD':'a-unique-long-admin-password'}

def test_secure_prod_configuration():
    assert production_errors(BASE) == []
    require_production_configuration(BASE)

@pytest.mark.parametrize('changed', [
    {'COOKIE_SECURE':'false'}, {'APP_ORIGIN':'http://shop.example.com'},
    {'APP_ORIGIN':'https://shop.example.com/path'}, {'DATABASE_URL':'sqlite:///foo'},
    {'ADMIN_PASSWORD':'password'}, {'DEMO_SEED_CONFIRM':'I_UNDERSTAND_THIS_IS_DEMO_DATA'},
])
def test_unsafe_production_blocked(changed):
    env = {**BASE, **changed}
    assert production_errors(env)
    with pytest.raises(RuntimeError):
        require_production_configuration(env)

def test_development_mode_not_blocked():
    assert production_errors({'APP_ENV':'development'}) == []
