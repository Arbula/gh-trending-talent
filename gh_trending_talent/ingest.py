from __future__ import annotations

import re
from datetime import date
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

from .sample_data import sample_repositories


TRENDING_URL = "https://github.com/trending/{language}?since={since}"


def _parse_count(text: str) -> int:
    cleaned = text.strip().replace(",", "").replace("+", "")
    match = re.search(r"(\d+)", cleaned)
    return int(match.group(1)) if match else 0


def fetch_trending(language: str, since: str = "daily", limit: int = 10) -> list[dict]:
    url = TRENDING_URL.format(language=quote(language.lower()), since=quote(since))
    headers = {"User-Agent": "GH Trending Talent academic prototype"}
    response = httpx.get(url, headers=headers, timeout=20, follow_redirects=True)
    response.raise_for_status()
    return parse_trending_html(response.text, language=language, limit=limit)


def parse_trending_html(html: str, language: str, limit: int = 10) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for rank, article in enumerate(soup.select("article.Box-row")[:limit], start=1):
        title = article.select_one("h2 a")
        if not title:
            continue
        repo_path = " ".join(title.get_text(" ", strip=True).split()).replace(" / ", "/")
        description_node = article.select_one("p")
        count_links = article.select("a.Link--muted")
        stars = _parse_count(count_links[0].get_text(" ", strip=True)) if count_links else 0
        forks = _parse_count(count_links[1].get_text(" ", strip=True)) if len(count_links) > 1 else 0
        stars_today_node = article.find(string=re.compile(r"stars today"))
        contributors = [
            img.get("alt", "").lstrip("@")
            for img in article.select("span:has(img) img")
            if img.get("alt")
        ]
        rows.append(
            {
                "snapshot_date": date.today().isoformat(),
                "language": language.title(),
                "rank": rank,
                "repo": repo_path,
                "url": f"https://github.com/{repo_path}",
                "description": description_node.get_text(" ", strip=True) if description_node else "",
                "stars": stars,
                "forks": forks,
                "stars_today": _parse_count(str(stars_today_node or "")),
                "contributors": ", ".join(contributors[:5]),
            }
        )
    return rows


def collect(languages: list[str], since: str = "daily", limit: int = 10, offline: bool = False) -> list[dict]:
    if offline:
        return sample_repositories()
    all_rows: list[dict] = []
    for language in languages:
        all_rows.extend(fetch_trending(language, since=since, limit=limit))
    return all_rows
