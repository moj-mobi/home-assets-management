import re
from urllib.parse import urlsplit

from app.main import query_without
from starlette.requests import Request


def test_static_assets_do_not_use_backend_scheme(app_client):
    _, client = app_client
    # TLS terminates upstream; the application itself still sees HTTP.
    page = client.get('/login', headers={'X-Forwarded-Proto': 'https'})
    paths = re.findall(r'(?:href|src)="([^\"]*static/[^\"]+)"', page.text)
    assert len(paths) >= 6
    for path in paths:
        assert path.startswith('/static/')
        response = client.get(path)
        assert response.status_code == 200
        if urlsplit(path).path.endswith('.css'):
            assert response.headers['content-type'].startswith('text/css')


def test_filter_links_preserve_external_origin():
    request = Request({'type': 'http', 'method': 'GET', 'scheme': 'http',
                       'server': ('internal', 8000), 'path': '/assets',
                       'query_string': b'q=chair&page=2&status=in_use', 'headers': []})
    assert query_without(request, 'page') == '/assets?q=chair&status=in_use'
