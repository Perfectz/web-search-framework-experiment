from __future__ import annotations

import argparse
import json
import time

from apartment_agent.browser import PlaywrightCapture
from apartment_agent.config import load_criteria, load_seed_listings, load_sources
from apartment_agent.pipeline import next_run_delay_seconds, run_live, run_seed


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        criteria = load_criteria(args.criteria)
        sources = load_sources(args.sources)
        browser_capture = _maybe_browser_capture(args)
        report = run_live(
            criteria=criteria,
            sources=sources,
            db_path=args.db,
            output_dir=args.output_dir,
            browser_capture=browser_capture,
        )
        print(json.dumps(_summary(report), indent=2))
        return 0

    if args.command == "run-seed":
        criteria = load_criteria(args.criteria)
        seed_payloads = load_seed_listings(args.seed)
        report = run_seed(
            criteria=criteria,
            seed_payloads=seed_payloads,
            db_path=args.db,
            output_dir=args.output_dir,
        )
        print(json.dumps(_summary(report), indent=2))
        return 0

    if args.command == "run-daily":
        while True:
            criteria = load_criteria(args.criteria)
            sources = load_sources(args.sources)
            browser_capture = _maybe_browser_capture(args)
            report = run_live(
                criteria=criteria,
                sources=sources,
                db_path=args.db,
                output_dir=args.output_dir,
                browser_capture=browser_capture,
            )
            print(json.dumps(_summary(report), indent=2))
            delay = next_run_delay_seconds(args.time, args.timezone)
            print(f"Sleeping {delay} seconds until next run.")
            time.sleep(delay)

    if args.command == "capture":
        browser_capture = PlaywrightCapture(
            headless=not args.headful,
            user_data_dir=args.profile_dir,
            wait_seconds=args.wait_seconds,
        )
        output = browser_capture.capture(args.url, args.output)
        print(str(output))
        return 0

    if args.command == "app":
        from apartment_agent.gui import launch_app

        launch_app(
            db_path=args.db,
            criteria_path=args.criteria,
            sources_path=args.sources,
            output_dir=args.output_dir,
        )
        return 0

    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="apartment_agent")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run live collection")
    _add_common_run_args(run_parser)

    seed_parser = subparsers.add_parser("run-seed", help="Run against seed listings")
    seed_parser.add_argument("--criteria", default="config/criteria.json")
    seed_parser.add_argument("--seed", default="config/seed_listings.json")
    seed_parser.add_argument("--db", default="data/apartment_agent.sqlite")
    seed_parser.add_argument("--output-dir", default="outputs")

    daily_parser = subparsers.add_parser("run-daily", help="Run forever on a daily interval")
    _add_common_run_args(daily_parser)
    daily_parser.add_argument("--time", default="09:00")
    daily_parser.add_argument("--timezone", default="Asia/Bangkok")

    capture_parser = subparsers.add_parser("capture", help="Capture a screenshot with Playwright")
    capture_parser.add_argument("--url", required=True)
    capture_parser.add_argument("--output", required=True)
    capture_parser.add_argument("--headful", action="store_true")
    capture_parser.add_argument("--profile-dir")
    capture_parser.add_argument("--wait-seconds", type=float, default=2.0)

    app_parser = subparsers.add_parser("app", help="Launch the desktop results viewer")
    app_parser.add_argument("--criteria", default="config/criteria.json")
    app_parser.add_argument("--sources", default="config/sources.json")
    app_parser.add_argument("--db", default="data/apartment_agent.sqlite")
    app_parser.add_argument("--output-dir", default="outputs")

    return parser


def _add_common_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--criteria", default="config/criteria.json")
    parser.add_argument("--sources", default="config/sources.json")
    parser.add_argument("--db", default="data/apartment_agent.sqlite")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--capture-conflicts", action="store_true")
    parser.add_argument("--headful", action="store_true")
    parser.add_argument("--profile-dir")
    parser.add_argument("--wait-seconds", type=float, default=2.0)


def _maybe_browser_capture(args: argparse.Namespace) -> PlaywrightCapture | None:
    if not getattr(args, "capture_conflicts", False):
        return None
    return PlaywrightCapture(
        headless=not getattr(args, "headful", False),
        user_data_dir=getattr(args, "profile_dir", None),
        wait_seconds=getattr(args, "wait_seconds", 2.0),
    )


def _summary(report: dict) -> dict:
    return {
        "run_id": report["run_id"],
        "alerts": len(report["alerts"]),
        "watch": len(report["watch"]),
        "new_records": report["new_records"],
        "json_report": report["json_report"],
        "markdown_report": report["markdown_report"],
        "errors": report["errors"],
    }
