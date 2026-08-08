import argparse
import json
import sys

from intelligence.aggregate import aggregate_all_topic_daily_metrics
from intelligence.db import get_engine
from intelligence.health import check_health
from intelligence.ingest import UnknownSourceError, run_ingestion
from intelligence.normalize import normalize_pending_documents
from intelligence.process import classify_and_extract_signals
from intelligence.trends.base import TrendProviderError
from intelligence.trends.pipeline import (
    check_provider,
    collect_trends,
    compute_trend_metrics,
    discover_trend_terms,
)


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

    trends_parser = subparsers.add_parser("trends", help="Google Trends collection and metrics")
    trends_sub = trends_parser.add_subparsers(dest="trends_command", required=True)

    collect_parser = trends_sub.add_parser("collect", help="Store interest-over-time observations")
    collect_parser.add_argument("provider", help="Registered trend provider name")
    collect_parser.add_argument("--path", default=None, help="CSV export path (google_trends_csv)")
    collect_parser.add_argument("--geo", default="MY", help="Geo code for the collected series")

    discover_parser = trends_sub.add_parser("discover", help="Register top/rising terms (§15A)")
    discover_parser.add_argument("provider", help="Registered trend provider name")

    trends_sub.add_parser("compute", help="Recompute rolling averages, growth and z-scores")

    check_parser = trends_sub.add_parser("check", help="Report whether a provider can run")
    check_parser.add_argument("provider", help="Registered trend provider name")
    check_parser.add_argument("--path", default=None, help="CSV export path (google_trends_csv)")

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

    if args.command == "trends":
        _run_trends_command(args)
        return


def _run_trends_command(args) -> None:
    config = {"path": getattr(args, "path", None), "geo": getattr(args, "geo", "MY")}

    if args.trends_command == "check":
        result = check_provider(args.provider, config)
        print(json.dumps(result))
        sys.exit(0 if result["available"] else 1)

    if args.trends_command == "compute":
        print(json.dumps(compute_trend_metrics(get_engine())))
        return

    runner = collect_trends if args.trends_command == "collect" else discover_trend_terms

    try:
        print(json.dumps(runner(get_engine(), args.provider, config=config)))
    except TrendProviderError as exc:
        # An unavailable provider is a configuration problem with an actionable
        # fix, not a crash — report it plainly and exit non-zero.
        print(json.dumps({"error": str(exc), "provider": args.provider}))
        sys.exit(1)


if __name__ == "__main__":
    main()
