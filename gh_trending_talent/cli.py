from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

import uvicorn

from .app import create_app, load_product
from .github_accounts import classify_known_logins, enrich_rows_with_github
from .ingest import collect
from .sample_data import sample_profiles
from .storage import DEFAULT_DB, clear_data, connect, upsert_profiles, upsert_pull_requests, upsert_repositories


DEFAULT_LANGUAGES = ["python", "javascript", "typescript", "go", "rust"]


def _timeline(started_at: float, stage: str, message: str) -> None:
    elapsed = time.monotonic() - started_at
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp} +{elapsed:6.1f}s] {stage:<10} {message}", flush=True)


def ingest(args: argparse.Namespace) -> None:
    started_at = time.monotonic()
    log = lambda stage, message: _timeline(started_at, stage, message)
    log(
        "start",
        (
            f"languages={','.join(args.languages)} since={args.since} limit={args.limit} "
            f"contributors={args.max_contributors} prs={args.max_pull_requests} replace={args.replace}"
        ),
    )
    log("ingest", "fetching GitHub Trending pages" if not args.offline else "loading offline sample data")
    rows = collect(args.languages, since=args.since, limit=args.limit, offline=args.offline)
    log("ingest", f"collected {len(rows)} repository records")
    profiles = sample_profiles() if args.offline else []
    pull_requests = []
    if not args.offline and not args.no_github_api:
        log("github", "starting contributor/profile/merged-PR enrichment")
        rows, profiles, pull_requests = enrich_rows_with_github(
            rows,
            max_contributors=args.max_contributors,
            max_pull_requests=args.max_pull_requests,
            use_ai=args.ai_filter,
            progress=lambda message: log("github", message),
        )
        log("github", f"enrichment finished profiles={len(profiles)} merged_prs={len(pull_requests)}")
    elif not args.offline:
        logins = {
            name.strip()
            for row in rows
            for name in (row.get("contributors") or "").split(",")
            if name.strip()
        }
        log("github", f"classifying {len(logins)} existing contributor handles")
        profiles = classify_known_logins(logins, use_ai=args.ai_filter)
        log("github", f"classified {len(profiles)} profiles")
    log("storage", f"opening {args.db}")
    with connect(args.db) as conn:
        if args.replace:
            log("storage", "clearing existing repositories, profiles, and pull requests")
            clear_data(conn)
        count = upsert_repositories(conn, rows)
        profile_count = upsert_profiles(conn, profiles)
        pr_count = upsert_pull_requests(conn, pull_requests)
    log("storage", f"stored repos={count} profiles={profile_count} merged_prs={pr_count}")
    log("done", f"database ready at {args.db}")
    if not args.offline and not args.no_github_api and profile_count == 0:
        print("Warning: no GitHub profiles were stored. GitHub API rate limit may be exhausted; set GITHUB_TOKEN and rerun with --replace.")
    if not args.offline and not args.no_github_api and args.max_pull_requests > 0 and pr_count == 0:
        print("Warning: no merged PR records were stored. This is usually caused by GitHub API rate limits or private/unavailable PR data.")


def report(args: argparse.Namespace) -> None:
    product = load_product(args.db, domain=args.domain)
    print(f"Snapshot: {product['snapshot_date']}")
    print(f"Domain: {product['active_domain'] or 'All domains'}")
    if product["active_domain"]:
        print(f"Matched repositories: {product['matching_repositories']} of {product['source_repositories']}")
    print("\nTechnologies")
    for trend in product["trends"]:
        print(f"- {trend['language']}: {trend['adoption_score']} ({trend['stars_today']} stars today)")
    print("\nTalent")
    for person in product["talent"]:
        print(
            f"- @{person['handle']}: {person['recruiting_score']} "
            f"({person['role_fit']}, {person['confidence']} {person['confidence_score']}/100, "
            f"impact {person['impact_score']}, PR {person['pr_score']}, ecosystem {person['ecosystem_score']}) via {', '.join(person['projects'])}"
        )


def serve(args: argparse.Namespace) -> None:
    uvicorn.run(create_app(args.db), host=args.host, port=args.port)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GH Trending Talent GitHub trend intelligence service")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Collect GitHub Trending data")
    ingest_parser.add_argument("--languages", nargs="+", default=DEFAULT_LANGUAGES)
    ingest_parser.add_argument("--since", choices=["daily", "weekly", "monthly"], default="daily")
    ingest_parser.add_argument("--limit", type=int, default=10)
    ingest_parser.add_argument("--max-contributors", type=int, default=10)
    ingest_parser.add_argument("--max-pull-requests", type=int, default=10)
    ingest_parser.add_argument("--replace", action="store_true", help="Clear existing repository/profile data before storing this run")
    ingest_parser.add_argument("--no-github-api", action="store_true", help="Skip GitHub API contributor/profile enrichment")
    ingest_parser.add_argument("--ai-filter", action="store_true", help="Use Groq AI only for uncertain human-account classification")
    ingest_parser.add_argument("--offline", action="store_true", help="Use bundled sample data")
    ingest_parser.set_defaults(func=ingest)

    report_parser = subparsers.add_parser("report", help="Print a terminal summary")
    report_parser.add_argument("--domain", default="", help="Filter by hiring domain, such as product, payments, or LLM infra")
    report_parser.set_defaults(func=report)

    serve_parser = subparsers.add_parser("serve", help="Run the web/API service")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.set_defaults(func=serve)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
