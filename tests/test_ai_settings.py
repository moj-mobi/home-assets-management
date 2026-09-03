import asyncio
import os

import httpx
import pytest

from app.ai_settings import AIKeyStore, check_key, valid_key_format
from app.asset_ai import GeminiVisionAnalyzer
from app.asset_valuation import GeminiAssetValuator
from app.models import Asset
from conftest import csrf_from, login


def test_settings_lifecycle(app_client, monkeypatch):
    app, client = app_client
    assert client.get('/settings/ai', follow_redirects=False).status_code == 303
    login(client)
    page = client.get('/settings/ai')
    csrf = csrf_from(page)
    assert page.headers['cache-control'] == 'no-store'
    key = 'ABCD-secret-test-key'
    async def valid(key):
        return 'valid', '03. 09. 2026 12:00 UTC'
    monkeypatch.setattr('app.main.check_key', valid)
    assert client.post('/settings/ai', data={'action': 'save', 'api_key': key}).status_code == 403
    page = client.post('/settings/ai', data={'action': 'save', 'api_key': key, 'csrf_token': csrf})
    assert 'ABCD*****' in page.text and key not in page.text
    assert 'key-status-valid' in page.text
    store = AIKeyStore(app.state.settings.data_dir, 'ENV-fallback-key')
    assert store.key() == key
    assert 'AI-prepoznava še ni nastavljena' not in client.get('/assets/scan').text
    async def invalid(key):
        return 'invalid', '03. 09. 2026 12:01 UTC'
    monkeypatch.setattr('app.main.check_key', invalid)
    page = client.post('/settings/ai', data={'action': 'check', 'csrf_token': csrf})
    assert 'key-status-invalid' in page.text
    page = client.post('/settings/ai', data={'action': 'save', 'api_key': 'EFGH-replacement-key', 'csrf_token': csrf})
    assert 'EFGH*****' in page.text and 'ABCD*****' not in page.text
    page = client.post('/settings/ai', data={'action': 'remove', 'csrf_token': csrf})
    assert 'Ključ ni nastavljen' in page.text
    assert store.key() == ''  # Persisted removal overrides environment even after restart.
    assert 'AI-prepoznava še ni nastavljena' in client.get('/assets/scan').text


def test_private_atomic_storage(tmp_path, monkeypatch):
    store = AIKeyStore(tmp_path, 'environment-key')
    assert store.key() == 'environment-key'
    store.save('ABCD-first-key')
    if os.name != 'nt':
        assert store.path.stat().st_mode & 0o777 == 0o600
        assert store.directory.stat().st_mode & 0o777 == 0o700
    def fail(*args):
        raise OSError('simulated disk error')
    monkeypatch.setattr('app.ai_settings.os.replace', fail)
    with pytest.raises(OSError):
        store.save('EFGH-new-key')
    assert store.key() == 'ABCD-first-key'
    assert list(store.directory.iterdir()) == [store.path]


@pytest.mark.parametrize('key', ['AIza' + 'a' * 35, 'AQ.A' + 'a' * 300 + '._-='])
def test_opaque_key_formats(key):
    assert valid_key_format(key)


@pytest.mark.parametrize('key', ['', 'short', 'a' * 4097, 'test key here', 'test\r\nInjected: value', 'test\tkey', 'test\x00key', 'test\x7fkey', 'testključ'])
def test_unsafe_key_formats(key):
    assert not valid_key_format(key)


def test_migrated_auth_key_check_and_replacement(app_client, monkeypatch):
    app, client = app_client
    login(client)
    store = AIKeyStore(app.state.settings.data_dir)
    key = 'AQ.A' + 'x' * 300 + '.token_=-'
    store.save(key)
    checked = []
    async def valid(candidate):
        checked.append(candidate)
        return 'valid', '03. 09. 2026 12:00 UTC'
    monkeypatch.setattr('app.main.check_key', valid)
    csrf = csrf_from(client.get('/settings/ai'))
    page = client.post('/settings/ai', data={'action': 'check', 'csrf_token': csrf})
    assert page.status_code == 200 and 'key-status-valid' in page.text
    assert checked == [key] and key not in page.text
    assert 'AQ.A*****' in page.text
    page = client.post('/settings/ai', data={'action': 'save', 'api_key': key + 'new', 'csrf_token': csrf})
    assert page.status_code == 200 and checked[-1] == key + 'new'
    assert store.key() == key + 'new'


@pytest.mark.parametrize('status, expected', [(200, 'valid'), (400, 'invalid'), (401, 'invalid'), (403, 'invalid'), (429, 'unavailable'), (500, 'unavailable')])
def test_check_response(monkeypatch, status, expected):
    async def get(self, url, **kwargs):
        assert 'secret' not in url
        assert kwargs['headers']['x-goog-api-key'] == 'secret'
        return httpx.Response(status, json={'error': {'message': 'secret'}})
    monkeypatch.setattr(httpx.AsyncClient, 'get', get)
    assert asyncio.run(check_key('secret'))[0] == expected


def test_check_timeout(monkeypatch):
    async def get(*args, **kwargs):
        raise httpx.ConnectError('secret')
    monkeypatch.setattr(httpx.AsyncClient, 'get', get)
    assert asyncio.run(check_key('secret'))[0] == 'unavailable'


def test_clients_read_current_key(tmp_path, monkeypatch):
    store = AIKeyStore(tmp_path)
    vision = GeminiVisionAnalyzer(store.key)
    valuator = GeminiAssetValuator(store.key, 'test-model')
    seen = []
    async def post(self, url, **kwargs):
        seen.append(kwargs['headers']['x-goog-api-key'])
        return httpx.Response(200, json={'output_text': '{}'}, request=httpx.Request('POST', url))
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    store.save('ABCD-first-key')
    asyncio.run(vision.analyze([]))
    store.save('EFGH-second-key')
    asyncio.run(valuator.estimate(Asset(name='Test')))
    assert seen == ['ABCD-first-key', 'EFGH-second-key']
    store.save('')
    with pytest.raises(RuntimeError, match='ni nastavljena'):
        asyncio.run(vision.analyze([]))
