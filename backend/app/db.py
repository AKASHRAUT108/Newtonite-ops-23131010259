from app.config import settings
from app.db import Base
import os

# Force the asyncpg driver regardless of what the cloud platform provides
_db_url = os.environ.get("DATABASE_URL", settings.database_url)
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    _db_url,
    echo=False,
    pool_pre_ping=True,
)