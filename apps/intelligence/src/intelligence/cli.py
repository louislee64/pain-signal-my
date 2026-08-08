import argparse
import json
import sys

from intelligence.aggregate import aggregate_all_topic_daily_metrics
from intelligence.db import get_engine
from intelligence.health import check_health
from intelligence.ingest import UnknownSourceError, run_ingestion
from intelligence.llm.base import LLMProviderError
from intelligence.llm.evaluate import evaluate, record
from intelligence.llm.extract import extract_problems
from intelligence.llm.registry import build_llm_provider
from intelligence.llm.usage import get_llm_config, spend_this_month, spend_today
from intelligence.normalize import normalize_pending_documents
from intelligence.process import classify_and_extract_signals
from intelligence.scoring.engine import score_all_topics
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
    subparsers.add_parser("score", help="Score every topic and refresh opportunities (§26-§30)")

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

    llm_parser = subparsers.add_parser("llm", help="LLM extraction, evaluation and spend (§24, §44, §70)")
    llm_sub = llm_parser.add_subparsers(dest="llm_command", required=True)

    extract_parser = llm_sub.add_parser("extract", help="Extract problems from pending documents")
    extract_parser.add_argument("--source", dest="source_slug", default=None, help="Limit to one source")
    extract_parser.add_argument("--limit", type=int, default=None, help="Cap documents this run")
    extract_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report how many documents would be sent, without calling or spending",
    )

    eval_parser = llm_sub.add_parser("evaluate", help="Run the §70 evaluation cases")
    eval_parser.add_argument("--provider", default="fixture", help="Registered LLM provider name")
    eval_parser.add_argument("--recordings", default=None, help="Recordings path (fixture provider)")
    eval_parser.add_argument("--model", default=None, help="Model override (paid providers)")
    eval_parser.add_argument("--verbose", action="store_true", help="Print each case's extraction")

    record_parser = llm_sub.add_parser(
        "record", help="Run the evaluation cases against a paid provider and save the answers"
    )
    record_parser.add_argument("--provider", default="anthropic", help="Registered LLM provider name")
    record_parser.add_argument("--model", default=None, help="Model override")
    record_parser.add_argument(
        "--output",
        default="/app/evaluation/recordings/extract_problem_v1.json",
        help="Where to write the recordings",
    )

    usage_parser = llm_sub.add_parser("usage", help="Report AI spend against the configured budget")
    usage_parser.add_argument("--json", dest="as_json", action="store_true", help="Machine-readable output")

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

    if args.command == "score":
        print(json.dumps(score_all_topics()))
        return

    if args.command == "trends":
        _run_trends_command(args)
        return

    if args.command == "llm":
        _run_llm_command(args)
        return


def _build_eval_provider(args):
    config: dict = {}
    if getattr(args, "recordings", None):
        config["recordings_path"] = args.recordings
    if getattr(args, "model", None):
        config["model"] = args.model

    if args.provider == "fixture" and "recordings_path" not in config:
        config["recordings_path"] = get_llm_config().provider_config.get("recordings_path")

    return build_llm_provider(args.provider, config)


def _run_llm_command(args) -> None:
    if args.llm_command == "extract":
        result = extract_problems(
            get_engine(),
            limit=args.limit,
            source_slug=args.source_slug,
            dry_run=args.dry_run,
        )
        print(json.dumps(result.as_dict()))
        # A stopped run is not a crash — it is the guard doing its job — but it
        # must not report success either, or a scheduler will treat a
        # budget-halted run as a completed one.
        sys.exit(1 if result.stopped_reason and not args.dry_run else 0)

    if args.llm_command == "evaluate":
        try:
            report = evaluate(provider=_build_eval_provider(args))
        except (LLMProviderError, ValueError) as exc:
            print(json.dumps({"error": str(exc)}))
            sys.exit(1)

        payload = {
            "provider": report.provider,
            "model": report.model,
            "prompt_version": report.prompt_version,
            "passed": report.passed,
            "total": report.total,
            "failed_cases": report.failed_case_ids,
            "estimated_cost": round(report.estimated_cost, 6),
            "cases": [
                {
                    "id": r.case_id,
                    "passed": r.passed,
                    "failures": r.failures,
                    "error": r.error,
                    **({"extraction": r.extraction} if args.verbose else {}),
                }
                for r in report.results
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        sys.exit(0 if report.passed == report.total else 1)

    if args.llm_command == "record":
        config = {"model": args.model} if args.model else {}
        try:
            provider = build_llm_provider(args.provider, config)
            payload = record(provider, args.output)
        except (LLMProviderError, ValueError) as exc:
            print(json.dumps({"error": str(exc)}))
            sys.exit(1)

        print(json.dumps({"recorded": len(payload["extractions"]), "output": args.output}))
        return

    if args.llm_command == "usage":
        config = get_llm_config()
        engine = get_engine()
        with engine.begin() as conn:
            payload = {
                "spent_today_usd": round(spend_today(conn), 6),
                "spent_this_month_usd": round(spend_this_month(conn), 6),
                "daily_budget_usd": config.daily_budget_usd,
                "monthly_budget_usd": config.monthly_budget_usd,
                "enabled": config.enabled,
                "provider": config.provider,
            }
        print(json.dumps(payload))
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
