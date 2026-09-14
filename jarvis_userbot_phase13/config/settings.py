from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    session_name: str
    command_prefix: str
    database_path: Path
    owner_name: str

def load_settings() -> Settings:
    api_id = os.getenv("API_ID", "").strip()
    api_hash = os.getenv("API_HASH", "").strip()
    if not api_id or not api_hash:
        raise RuntimeError("API_ID va API_HASH .env faylida berilishi kerak.")
    return Settings(
        api_id=int(api_id),
        api_hash=api_hash,
        session_name=os.getenv("SESSION_NAME", "berdiyorov").strip(),
        command_prefix=os.getenv("COMMAND_PREFIX", ".").strip() or ".",
        database_path=Path(os.getenv("DATABASE_PATH", "jarvis.db")),
        owner_name=os.getenv("OWNER_NAME", "Berdiyorov").strip() or "Berdiyorov",
    )
