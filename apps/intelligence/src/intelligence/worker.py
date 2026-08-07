import time

from intelligence.health import check_health
from intelligence.observability import get_logger, log_event

logger = get_logger("intelligence.worker")

HEARTBEAT_INTERVAL_SECONDS = 30


def main() -> None:
    log_event(logger, "worker.starting")

    while True:
        report = check_health()
        log_event(logger, "worker.heartbeat", database=report.database, redis=report.redis)
        time.sleep(HEARTBEAT_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
