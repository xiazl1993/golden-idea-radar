from __future__ import annotations

import argparse

from .collectors.github import GitHubIssueCollector
from .collectors.manual import CsvCollector
from .config import settings
from .models import SessionLocal, init_db
from .pipeline import run_pipeline
from .storage import upsert_observations


def main() -> None:
    parser = argparse.ArgumentParser(prog="golden-idea-radar")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_csv = sub.add_parser("ingest-csv")
    p_csv.add_argument("path")
    p_gh = sub.add_parser("ingest-github")
    p_gh.add_argument("--per-query", type=int, default=30)
    p_run = sub.add_parser("run")
    p_run.add_argument("--include-demo", action="store_true")
    p_run.add_argument("--report", default="reports/latest.md")
    args = parser.parse_args()
    init_db()
    if args.cmd == "ingest-csv":
        items = CsvCollector(args.path).collect()
        with SessionLocal() as session:
            inserted = upsert_observations(session, items)
        print({"received": len(items), "inserted": inserted})
    elif args.cmd == "ingest-github":
        items = GitHubIssueCollector(settings.github_token, per_query=args.per_query).collect()
        with SessionLocal() as session:
            inserted = upsert_observations(session, items)
        print({"received": len(items), "inserted": inserted})
    elif args.cmd == "run":
        print(run_pipeline(include_demo=args.include_demo, report_path=args.report))


if __name__ == "__main__":
    main()
