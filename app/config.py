from dataclasses import dataclass
from pathlib import Path
import os
import secrets


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str
    session_secret: str
    environment: str = "development"
    secure_cookies: bool = False
    session_max_age_seconds: int = 3600
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "testserver")
    app_name: str = "HAM"
    max_attachment_bytes: int = 10 * 1024 * 1024
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.7-flash"

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("HAM_DATA_DIR", "data")).resolve()
        default_db = f"sqlite:///{(data_dir / 'database' / 'ham.db').as_posix()}"
        environment = os.getenv("HAM_ENV", "development").lower()
        session_secret = os.getenv("HAM_SESSION_SECRET", "")
        if environment == "server" and len(session_secret) < 32:
            raise RuntimeError("HAM_SESSION_SECRET must contain at least 32 characters in server mode")
        if not session_secret:
            session_secret = secrets.token_urlsafe(48)
        return cls(
            data_dir=data_dir,
            database_url=os.getenv("HAM_DATABASE_URL", default_db),
            session_secret=session_secret,
            environment=environment,
            secure_cookies=os.getenv("HAM_SECURE_COOKIES", "false").lower() in {"1", "true", "yes"},
            session_max_age_seconds=int(os.getenv("HAM_SESSION_MAX_AGE_SECONDS", "3600")),
            allowed_hosts=tuple(h.strip() for h in os.getenv("HAM_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver").split(",") if h.strip()),
            max_attachment_bytes=int(os.getenv("HAM_MAX_ATTACHMENT_BYTES", str(10 * 1024 * 1024))),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("HAM_GEMINI_MODEL", "gemini-3.7-flash"),
        )

    def ensure_directories(self) -> None:
        for child in ("database", "attachments", "backups", "imports"):
            (self.data_dir / child).mkdir(parents=True, exist_ok=True)
