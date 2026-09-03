import importlib.util
from pathlib import Path

import pytest


def test_codespaces_setup_preserves_existing_settings(tmp_path, monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location('codespaces_setup', Path(__file__).resolve().parents[1] / 'setup-codespaces.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('CODESPACE_NAME', 'example-space')
    monkeypatch.setenv('GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN', 'app.github.dev')
    monkeypatch.setattr(module.os, 'getuid', lambda: 1000, raising=False)
    monkeypatch.setattr(module.os, 'getgid', lambda: 1000, raising=False)
    module.prepare(tmp_path)
    original = (tmp_path / '.env').read_text()
    assert 'example-space-8000.app.github.dev' in original
    assert 'HAM_SECURE_COOKIES=true' in original
    secret = next(line.split('=', 1)[1] for line in original.splitlines() if line.startswith('HAM_SESSION_SECRET='))
    assert len(secret) >= 32 and secret not in capsys.readouterr().out
    with pytest.raises(SystemExit, match='že obstaja'):
        module.prepare(tmp_path)
    assert (tmp_path / '.env').read_text() == original
