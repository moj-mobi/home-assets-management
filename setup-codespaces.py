"""Create first-run settings in a Codespace; never overwrite an existing .env."""
import os
from pathlib import Path
import re
import secrets


def prepare(root: Path):
    name = os.environ.get("CODESPACE_NAME", "")
    domain = os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "")
    if not re.fullmatch(r"[a-zA-Z0-9-]+", name) or not re.fullmatch(r"[a-zA-Z0-9.-]+", domain):
        raise SystemExit("Zaženite v terminalu GitHub Codespaces (manjkata ime ali domena okolja).")
    path = root / ".env"
    if path.exists():
        raise SystemExit(".env že obstaja in ni bila spremenjena. Za nadgradnjo uporabite navodila v README.")
    host = f"{name}-8000.{domain}"
    settings = {
        "HAM_BIND_ADDRESS": "127.0.0.1", "HAM_HOST_PORT": "8000",
        "HAM_UID": str(os.getuid()), "HAM_GID": str(os.getgid()),
        "HAM_SESSION_SECRET": secrets.token_urlsafe(48),
        "HAM_SECURE_COOKIES": "true",
        "HAM_ALLOWED_HOSTS": f"127.0.0.1,localhost,{host}",
    }
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write("".join(f"{key}={value}\n" for key, value in settings.items()))
    for child in ("database", "attachments", "backups", "imports"):
        (root / "data" / child).mkdir(parents=True, exist_ok=True)
    print("Nastavitve so pripravljene. Vrednosti skrivnosti niso izpisane.")
    print(f"Naslov po zagonu: https://{host}")


if __name__ == "__main__":
    prepare(Path(__file__).resolve().parent)
