import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get(
                "INTELLIGENCE_DATABASE_URL",
                "postgresql+psycopg://pain_radar:pain_radar@postgres:5432/pain_radar",
            ),
            redis_url=os.environ.get("INTELLIGENCE_REDIS_URL", "redis://redis:6379/0"),
        )
