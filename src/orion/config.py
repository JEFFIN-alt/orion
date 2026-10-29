import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    database: Path
    log_dir: Path

    @classmethod
    def load(cls, database: str | None = None, log_dir: str | None = None) -> "Config":
        root = Path(os.environ.get("ORION_HOME", Path(__file__).resolve().parents[2])).expanduser().resolve()
        def resolve(value: str | Path) -> Path:
            path = Path(value).expanduser()
            return (path if path.is_absolute() else root / path).resolve()
        return cls(resolve(database or os.environ.get("ORION_DATABASE", "data/orion.sqlite3")),
                   resolve(log_dir or os.environ.get("ORION_LOG_DIR", "logs")))
