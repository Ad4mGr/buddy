import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/buddy.db")
OWNER_IDS: list[int] = [
    int(id_) for id_ in os.getenv("OWNER_IDS", "").split(",") if id_
]

CHECKIN_TIMEOUT_MINUTES: int = int(os.getenv("CHECKIN_TIMEOUT_MINUTES", "60"))
CHECKIN_INTERVAL_SECONDS: int = int(os.getenv("CHECKIN_INTERVAL_SECONDS", "30"))
