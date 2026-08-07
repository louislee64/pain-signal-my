from unittest.mock import patch

from intelligence.config import Settings
from intelligence.health import check_health


def test_check_health_reports_unhealthy_when_dependencies_unreachable():
    settings = Settings(
        database_url="postgresql+psycopg://nobody:nobody@localhost:1/nonexistent",
        redis_url="redis://localhost:1/0",
    )

    report = check_health(settings)

    assert report.database is False
    assert report.redis is False
    assert report.healthy is False


def test_check_health_reports_healthy_when_dependencies_reachable():
    with (
        patch("intelligence.health.check_database", return_value=True),
        patch("intelligence.health.check_redis", return_value=True),
    ):
        report = check_health(Settings.from_env())

    assert report.healthy is True
