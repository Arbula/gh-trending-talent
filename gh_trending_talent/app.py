from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from .analytics import domain_keywords, filter_rows_by_domain, repository_rankings, talent_shortlist, technology_trends
from .storage import DEFAULT_DB, connect, latest_repositories, profiles_by_login, pull_requests_for_repos


ROOT = Path(__file__).resolve().parent.parent
templates = Environment(
    loader=FileSystemLoader(ROOT / "templates"),
    autoescape=select_autoescape(["html", "xml"]),
)

SORT_OPTIONS = {
    "score": ("Recruiting score", "recruiting_score"),
    "confidence": ("Confidence", "confidence_score"),
    "impact": ("Impact", "impact_score"),
    "pr": ("Merged PR score", "pr_score"),
    "ecosystem": ("Ecosystem", "ecosystem_score"),
    "profile": ("Profile", "profile_strength"),
    "name": ("Name", "handle"),
}


def _sort_talent(talent: list[dict], sort: str) -> list[dict]:
    label, key = SORT_OPTIONS.get(sort, SORT_OPTIONS["score"])
    reverse = key != "handle"
    return sorted(talent, key=lambda item: item.get(key) or 0, reverse=reverse)


def load_product(db_path: Path = DEFAULT_DB, domain: str | None = None, sort: str = "score") -> dict:
    with connect(db_path) as conn:
        rows = latest_repositories(conn)
        profiles = profiles_by_login(conn)
    matched_rows = filter_rows_by_domain(rows, domain)
    with connect(db_path) as conn:
        pull_requests = pull_requests_for_repos(conn, [row["repo"] for row in matched_rows])
    sort_key = sort if sort in SORT_OPTIONS else "score"
    talent = _sort_talent(talent_shortlist(matched_rows, profiles=profiles, pull_requests=pull_requests), sort_key)
    return {
        "repositories": repository_rankings(matched_rows),
        "talent": talent,
        "trends": technology_trends(matched_rows),
        "snapshot_date": rows[0]["snapshot_date"] if rows else "No data",
        "active_domain": domain or "",
        "domain_keywords": domain_keywords(domain),
        "source_repositories": len(rows),
        "matching_repositories": len(matched_rows),
        "active_sort": sort_key,
        "active_sort_label": SORT_OPTIONS[sort_key][0],
        "sort_options": [{"key": key, "label": value[0]} for key, value in SORT_OPTIONS.items()],
    }


async def dashboard(request):
    domain = request.query_params.get("domain", "").strip()
    sort = request.query_params.get("sort", "score").strip()
    product = load_product(Path(request.app.state.db_path), domain=domain, sort=sort)
    html = templates.get_template("dashboard.html").render(product=product)
    return HTMLResponse(html)


async def api_talent(request):
    domain = request.query_params.get("domain", "").strip()
    sort = request.query_params.get("sort", "score").strip()
    return JSONResponse(load_product(Path(request.app.state.db_path), domain=domain, sort=sort)["talent"])


async def api_trends(request):
    domain = request.query_params.get("domain", "").strip()
    return JSONResponse(load_product(Path(request.app.state.db_path), domain=domain)["trends"])


async def api_repositories(request):
    domain = request.query_params.get("domain", "").strip()
    return JSONResponse(load_product(Path(request.app.state.db_path), domain=domain)["repositories"])


async def report_markdown(request):
    domain = request.query_params.get("domain", "").strip()
    sort = request.query_params.get("sort", "score").strip()
    product = load_product(Path(request.app.state.db_path), domain=domain, sort=sort)
    lines = [
        "# GH Trending Talent Daily GitHub Intelligence Report",
        "",
        f"Snapshot date: {product['snapshot_date']}",
        f"Domain filter: {product['active_domain'] or 'All domains'}",
        f"Sort: {product['active_sort_label']}",
        "",
        "## Emerging Technology Trends",
    ]
    for trend in product["trends"]:
        lines.append(
            f"- {trend['language']}: adoption score {trend['adoption_score']}, "
            f"{trend['stars_today']} stars today, top projects: {', '.join(trend['top_projects'])}"
        )
    lines.extend(["", "## High-Potential Talent Shortlist"])
    for person in product["talent"]:
        lines.append(
            f"- @{person['handle']}: recruiting score {person['recruiting_score']}; "
            f"{person['role_fit']}; confidence {person['confidence']} ({person['confidence_score']}/100); "
            f"impact {person['impact_score']}, breadth {person['breadth_score']}, "
            f"PR {person['pr_score']} ({person['merged_pr_count']} merged), ecosystem {person['ecosystem_score']}, profile {person['profile_strength']}, "
            f"contributor weight {person['best_contributor_weight']}; {person['reason']}"
        )
    lines.extend(["", "## Machine-Readable Payload", "```json", json.dumps(product, indent=2), "```"])
    return PlainTextResponse("\n".join(lines), media_type="text/markdown")


def create_app(db_path: Path | str = DEFAULT_DB) -> Starlette:
    app = Starlette(
        debug=True,
        routes=[
            Route("/", dashboard),
            Route("/api/talent", api_talent),
            Route("/api/trends", api_trends),
            Route("/api/repositories", api_repositories),
            Route("/report.md", report_markdown),
        ],
    )
    app.state.db_path = str(db_path)
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    return app


app = create_app()
