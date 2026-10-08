import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


def ollama_url(host: str) -> str:
    value = host.strip().rstrip("/")
    if not value:
        raise ValueError("Ollama host cannot be empty.")
    if "://" not in value:
        value = "http://" + value
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("Use an HTTP(S) URL or hostname for Ollama.")
    if parts.username or parts.password or parts.query or parts.fragment or parts.path:
        raise ValueError("Use an Ollama host without credentials, paths, or query parameters.")
    port = parts.port or 11434
    hostname = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    return f"{parts.scheme}://{hostname}:{port}"


@dataclass(frozen=True)
class Settings:
    host: str = "10.3.81.142"
    model: str = ""
    database: str = "data/knowledge.sqlite3"
    timeout: float = 120

    @classmethod
    def from_env(cls):
        return cls(
            host=os.getenv("OLLAMA_HOST", "10.3.81.142"),
            model=os.getenv("OLLAMA_MODEL", ""),
            database=os.getenv("METROPOLE_DB", "data/knowledge.sqlite3"),
            timeout=float(os.getenv("OLLAMA_TIMEOUT", "120")),
        )

    @property
    def base_url(self):
        return ollama_url(self.host)

    @property
    def db_path(self):
        return Path(self.database).expanduser()
