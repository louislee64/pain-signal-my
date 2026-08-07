import json
import logging
import sys
import time

from intelligence.health import check_health

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")
logger = logging.getLogger("intelligence.worker")

HEARTBEAT_INTERVAL_SECONDS = 30


def log_event(event: str, **fields) -> None:
    logger.info(json.dumps({"event": event, **fields}))


def main() -> None:
    log_event("worker.starting")

    while True:
        report = check_health()
        log_event("worker.heartbeat", database=report.database, redis=report.redis)
        time.sleep(HEARTBEAT_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
