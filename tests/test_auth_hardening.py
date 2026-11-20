"""Login hardening: failed passwords are throttled per address, the session cookie carries its flags and
every response carries the browser security headers. No database."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'source'))

import WebApp  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('ADMIN_PASSWORD', 'correct horse')
    WebApp._auth_failures.clear()
    WebApp._auth_locked_until.clear()
    clock = {'t': 1000.0}
    monkeypatch.setattr(WebApp, '_auth_now', lambda: clock['t'])
    c = WebApp.app.test_client()
    c.clock = clock
    return c


def _try(client, pw, ip='9.9.9.9'):
    return client.post('/api/auth/verify', json={'password': pw}, headers={'X-Forwarded-For': ip})


def test_right_password_signs_in_and_wrong_one_does_not(client):
    assert _try(client, 'nope').get_json() == {'ok': False}
    assert _try(client, 'correct horse').get_json() == {'ok': True}
    assert client.get('/api/auth/check').get_json()['authenticated'] is True


def test_five_wrong_passwords_lock_the_address_even_for_the_right_one(client):
    for _ in range(WebApp.AUTH_MAX_FAILURES):
        assert _try(client, 'bad').status_code == 200
    r = _try(client, 'correct horse')
    assert r.status_code == 429 and int(r.headers['Retry-After']) > 0
    assert client.get('/api/auth/check').get_json()['authenticated'] is False
    assert _try(client, 'correct horse', ip='1.2.3.4').get_json() == {'ok': True}      # another address is not affected


def test_the_lock_ends_and_old_failures_expire(client):
    for _ in range(WebApp.AUTH_MAX_FAILURES):
        _try(client, 'bad')
    client.clock['t'] += WebApp.AUTH_LOCK_SECONDS + 1
    assert _try(client, 'correct horse').get_json() == {'ok': True}
    # failures older than the window do not add up
    WebApp._auth_failures.clear()
    for _ in range(WebApp.AUTH_MAX_FAILURES - 1):
        _try(client, 'bad', ip='5.5.5.5')
    client.clock['t'] += WebApp.AUTH_WINDOW_SECONDS + 1
    _try(client, 'bad', ip='5.5.5.5')
    assert _try(client, 'correct horse', ip='5.5.5.5').get_json() == {'ok': True}


def test_session_cookie_is_httponly_and_lax(client):
    r = _try(client, 'correct horse')
    cookie = r.headers.get('Set-Cookie', '')
    assert 'HttpOnly' in cookie and 'SameSite=Lax' in cookie


def test_security_headers_are_on_every_response(client):
    r = client.get('/api/version')
    assert r.headers['X-Content-Type-Options'] == 'nosniff'
    assert r.headers['X-Frame-Options'] == 'SAMEORIGIN'
    assert r.headers['Referrer-Policy'] == 'same-origin'


def test_the_landing_page_tells_a_locked_user_to_wait():
    page = open(os.path.join(os.path.dirname(__file__), '..', 'index.html'), encoding='utf-8').read()
    assert 'signInLocked = r.status === 429' in page and 'יותר מדי ניסיונות' in page
