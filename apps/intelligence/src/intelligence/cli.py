import argparse
import json
import sys

from intelligence.aggregate import aggregate_all_topic_daily_metrics
from intelligence.db import get_engine
from intelligence.health import check_health
from intelligence.ingest import UnknownSourceError, run_ingestion
from intelligence.normalize import normalize_pending_documents
from intelligence.process import classify_and_extract_signals


def main() -> None:
    parser = argparse.ArgumentParser(prog="intelligence")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health", help="Check dependency connectivity and exit")

    ingest_parser = subparsers.add_parser("ingest", help="Run a collector for one configured source")
    ingest_parser.add_argument("source_slug", help="Slug of a source synced via `php artisan sources:sync`")

    normalize_parser = subparsers.add_parser("normalize", help="Clean + language-tag pending raw_documents")
    normalize_parser.add_argument("--source", dest="source_slug", default=None, help="Limit to one source")

    classify_parser = subparsers.add_parser(
        "classify", help="Rule-based topic classification + problem-signal extraction"
    )
    classify_parser.add_argument("--source", dest="source_slug", default=None, help="Limit to one source")

    subparsers.add_parser("aggregate", help="Recompute topic_daily_metrics from problem_signals")

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

    if args.command == "normalize":
        print(json.dumps(normalize_pending_documents(get_engine(), source_slug=args.source_slug)))
        return

    if args.command == "classify":
        print(json.dumps(classify_and_extract_signals(get_engine(), source_slug=args.source_slug)))
        return

    if args.command == "aggregate":
        print(json.dumps(aggregate_all_topic_daily_metrics(get_engine())))
        return


if __name__ == "__main__":
    main()
