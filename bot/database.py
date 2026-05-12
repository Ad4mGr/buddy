import asyncio
import logging
import pathlib

import aiosqlite

from bot import config

logger = logging.getLogger(__name__)

_db: aiosqlite.Connection | None = None
_init_lock = asyncio.Lock()


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is not None:
        return _db

    async with _init_lock:
        if _db is not None:
            return _db

        path = pathlib.Path(config.DATABASE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)

        _db = await aiosqlite.connect(str(path))
        _db.row_factory = aiosqlite.Row

        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")

        await _init_schema(_db)

        logger.info("Database opened: %s", path)

    return _db


async def close_db():
    global _db
    if _db is None:
        return
    try:
        await _db.close()
    except Exception as e:
        logger.warning("Error closing database: %s", e)
    finally:
        _db = None


async def _init_schema(db: aiosqlite.Connection):
    schema_path = pathlib.Path(__file__).resolve().parent.parent / "schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    try:
        schema = schema_path.read_text()
        await db.executescript(schema)
        await db.commit()
    except Exception as e:
        logger.error("Failed to initialize schema: %s", e)
        raise
