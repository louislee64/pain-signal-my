from dataclasses import dataclass

import redis as redis_lib
from sqlalchemy import create_engine, text

from intelligence.config import Settings


@dataclass(frozen=True)
class HealthReport:
    database: bool
    redis: bool

    @property
    def healthy(self) -> bool:
        return self.database and self.redis


def check_database(database_url: str) -> bool:
    try:
        engine = create_engine(database_url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def check_redis(redis_url: str) -> bool:
    try:
        client = redis_lib.from_url(redis_url, socket_connect_timeout=3)
        return bool(client.ping())
    except Exception:
        return False


def check_health(settings: Settings | None = None) -> HealthReport:
    settings = settings or Settings.from_env()
    return HealthReport(
        database=check_database(settings.database_url),
        redis=check_redis(settings.redis_url),
    )
