import argparse
import json
import sys

from intelligence.health import check_health


def main() -> None:
    parser = argparse.ArgumentParser(prog="intelligence")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health", help="Check dependency connectivity and exit")

    args = parser.parse_args()

    if args.command == "health":
        report = check_health()
        print(json.dumps({"database": report.database, "redis": report.redis}))
        sys.exit(0 if report.healthy else 1)


if __name__ == "__main__":
    main()
