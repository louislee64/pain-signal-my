import argparse
import json
import sys

from intelligence.health import check_health
from intelligence.ingest import UnknownSourceError, run_ingestion


def main() -> None:
    parser = argparse.ArgumentParser(prog="intelligence")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health", help="Check dependency connectivity and exit")

    ingest_parser = subparsers.add_parser("ingest", help="Run a collector for one configured source")
    ingest_parser.add_argument("source_slug", help="Slug of a source synced via `php artisan sources:sync`")

    args = parser.parse_args()

    if args.command == "health":
        report = check_health()
        print(json.dumps({"database": report.database, "redis": report.redis}))
        sys.exit(0 if report.healthy else 1)

    if args.command == "ingest":
        try:
            result = run_ingestion(args.source_slug)
        except UnknownSourceError as exc:
            print(json.dumps({"error": str(exc)}))
            sys.exit(1)

        print(json.dumps(result))
        sys.exit(0 if result["status"] == "succeeded" else 1)


if __name__ == "__main__":
    main()
