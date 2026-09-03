"""Private, atomic credential storage. An empty saved key disables env fallback."""
import csv
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx


def restrict_access(path: Path, directory=False):
    if os.name == "nt":
        identity = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], check=True, capture_output=True, text=True)
        sid = next(csv.reader(identity.stdout.strip().splitlines()))[1]
        rights = "(OI)(CI)F" if directory else "F"
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:{rights}"], check=True, capture_output=True)
    else:
        path.chmod(0o700 if directory else 0o600)


class AIKeyStore:
    def __init__(self, data_dir: Path, fallback=""):
        self.directory = data_dir / "private"
        self.path = self.directory / "gemini.json"
        self.fallback = fallback

    def read(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"key": self.fallback, "validity": "unchecked", "checked_at": None}

    def key(self):
        return self.read()["key"]

    def public_state(self):
        state = self.read()
        key = state.pop("key")
        return {**state, "configured": bool(key), "masked_key": key[:4] + "*****" if key else ""}

    def save(self, key, validity="unchecked", checked_at=None):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        restrict_access(self.directory, directory=True)
        fd, name = tempfile.mkstemp(dir=self.directory, prefix=".gemini-")
        temporary = Path(name)
        try:
            # Restrict the empty file before writing any credential.
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                restrict_access(temporary)
                json.dump({"key": key, "validity": validity, "checked_at": checked_at}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)


def valid_key_format(key):
    # Credentials are opaque: newer auth keys include punctuation and can be
    # longer than legacy API keys. Reject only unsafe header characters/size.
    return bool(re.fullmatch(r"[\x21-\x7e]{8,4096}", key))


async def check_key(key):
    """Check credentials without generating content or exposing provider errors."""
    checked_at = datetime.now(timezone.utc).strftime("%d. %m. %Y %H:%M UTC")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": key}, params={"pageSize": 1})
        if response.status_code == 200:
            return "valid", checked_at
        if response.status_code in {400, 401, 403}:
            return "invalid", checked_at
    except httpx.RequestError:
        pass
    return "unavailable", checked_at
