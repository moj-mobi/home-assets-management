from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str
    app_name: str = "HAM"

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("HAM_DATA_DIR", "data")).resolve()
        default_db = f"sqlite:///{(data_dir / 'database' / 'ham.db').as_posix()}"
        return cls(
            data_dir=data_dir,
            database_url=os.getenv("HAM_DATABASE_URL", default_db),
        )

    def ensure_directories(self) -> None:
        for child in ("database", "attachments", "backups", "imports"):
            (self.data_dir / child).mkdir(parents=True, exist_ok=True)

