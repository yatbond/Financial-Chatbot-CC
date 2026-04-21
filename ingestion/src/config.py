import os
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


SUPABASE_URL: str = _require("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY: str = _require("SUPABASE_SERVICE_ROLE_KEY")
DATABASE_URL: str = _require("DATABASE_URL")
INGESTION_PORT: int = int(os.environ.get("INGESTION_PORT", "8000"))
