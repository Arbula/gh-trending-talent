from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone


DOMAIN_ALIASES = {
    "ai": ["ai", "agent", "llm", "model", "inference", "rag", "machine learning"],
    "llm": ["llm", "large language model", "agent", "mcp", "model context protocol", "inference", "rag"],
    "infra": ["infra", "infrastructure", "runtime", "distributed", "cluster", "observability", "platform"],
    "developer tools": ["developer", "tool", "cli", "sdk", "package", "framework", "inspector", "model context protocol"],
    "devtools": ["developer", "tool", "cli", "sdk", "package", "framework", "inspector", "model context protocol"],
    "product": ["product", "production", "react", "api", "web", "frontend", "full-stack", "framework"],
    "frontend": ["frontend", "react", "javascript", "typescript", "web", "ui"],
    "backend": ["backend", "api", "server", "python", "go", "database", "service"],
    "mobile": ["mobile", "ios", "android", "react native", "flutter", "swift", "kotlin"],
    "payments": ["payment", "payments", "checkout", "billing", "stripe", "invoice", "subscription"],
    "ecommerce": ["commerce", "e-commerce", "ecommerce", "checkout", "shop", "cart", "retail"],
    "security": ["security", "auth", "authentication", "authorization", "crypto", "vulnerability"],
    "data": ["data", "warehouse", "etl", "pipeline", "analytics", "streaming"],
}


def domain_keywords(domain: str | None) -> list[str]:
    if not domain:
        return []
    raw_terms = [term.strip().lower() for term in domain.replace(",", " ").split() if term.strip()]
    phrases = [domain.strip().lower()] if domain.strip() else []
    keywords = set(raw_terms + phrases)
    for term in list(keywords):
        keywords.update(DOMAIN_ALIASES.get(term, []))
    return sorted(keywords)


def _row_text_dict(row: sqlite3.Row | dict) -> str:
    keys = row.keys() if hasattr(row, "keys") else row
    return " ".join(str(row[key] or "") for key in ["repo", "language", "description", "contributors"] if key in keys).lower()


def domain_match_score(row: sqlite3.Row | dict, domain: str | None) -> int:
    keywords = domain_keywords(domain)
    if not keywords:
        return 0
    text = _row_text_dict(row)
    return sum(1 for keyword in keywords if keyword in text)


def filter_rows_by_domain(rows: list[sqlite3.Row], domain: str | None) -> list[sqlite3.Row]:
    if not domain:
        return rows
    scored = [(domain_match_score(row, domain), row) for row in rows]
    return [row for score, row in scored if score > 0]


def momentum_score(row: sqlite3.Row | dict) -> float:
    stars_today = int(row["stars_today"] or 0)
    stars = int(row["stars"] or 0)
    forks = int(row["forks"] or 0)
    rank = int(row["rank"] or 99)
    freshness = max(0, 11 - rank) * 7
    return round(stars_today * 1.8 + math.log10(stars + 10) * 14 + math.log10(forks + 10) * 8 + freshness, 2)


def _role_fit(languages: set[str]) -> str:
    lowered = {language.lower() for language in languages}
    if {"typescript", "javascript"} & lowered and "python" in lowered:
        return "Full-stack product engineer"
    if "rust" in lowered or "go" in lowered:
        return "Systems or infrastructure engineer"
    if "python" in lowered:
        return "Backend or AI platform engineer"
    if {"typescript", "javascript"} & lowered:
        return "Frontend or developer tooling engineer"
    return "Open-source software engineer"


def _seniority_signal(project_count: int, total_stars_today: int, languages: set[str]) -> str:
    if project_count >= 3 or len(languages) >= 3:
        return "Senior/Staff signal"
    if project_count >= 2 or total_stars_today >= 700:
        return "Strong senior candidate"
    return "Specialist candidate"


def _contact_strategy(confidence: str, role_fit: str) -> str:
    if confidence == "High":
        return f"Prioritize direct outreach with a {role_fit.lower()} role tied to their visible OSS work."
    if confidence == "Medium":
        return "Review recent commits and issue activity before outreach."
    return "Use as a watchlist lead until more contribution evidence appears."


def _contributor_weight(position: int) -> float:
    return round(1 / math.sqrt(max(position, 1)), 4)


def _pr_recency_weight(merged_at: str) -> float:
    try:
        merged = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.5
    days = max(0, (datetime.now(timezone.utc) - merged).days)
    return round(max(0.25, math.exp(-days / 45)), 4)


def _pr_score(repo_score: float, merged_at: str) -> float:
    return round((18 + min(70, repo_score * 0.055)) * _pr_recency_weight(merged_at), 2)


def _profile_strength(profile: sqlite3.Row | dict | None) -> float:
    followers = float(_profile_value(profile, "followers", 0) or 0)
    public_repos = float(_profile_value(profile, "public_repos", 0) or 0)
    has_name = 1 if _profile_value(profile, "name", "") else 0
    has_bio = 1 if _profile_value(profile, "bio", "") else 0
    return round(
        min(30, math.log10(followers + 1) * 7 + math.log10(public_repos + 1) * 4 + has_name * 3 + has_bio * 4),
        2,
    )


def _evidence_confidence_score(
    project_count: int,
    language_count: int,
    weighted_impact: float,
    human_confidence: float,
    best_contributor_weight: float,
    profile_strength: float,
    merged_pr_count: int,
) -> float:
    score = (
        min(18, 5 + math.log1p(project_count) * 9)
        + min(11, 2.5 + math.log1p(language_count) * 5.5)
        + min(23, math.log10(weighted_impact + 10) * 6.7)
        + min(13, best_contributor_weight * 13)
        + min(12, math.log1p(merged_pr_count) * 6.5)
        + min(9, profile_strength / 3.4)
        + human_confidence * 13
    )
    return round(min(100, score), 2)


def _confidence_label(score: float) -> str:
    if score >= 75:
        return "High"
    if score >= 55:
        return "Medium"
    return "Low"


def _profile_value(profile: sqlite3.Row | dict | None, key: str, default=None):
    if not profile:
        return default
    try:
        return profile[key]
    except (KeyError, IndexError):
        return default


def _is_human_profile(profile: sqlite3.Row | dict | None) -> bool:
    return _profile_value(profile, "classification") == "human"


def _row_by_repo(rows: list[sqlite3.Row]) -> dict[str, sqlite3.Row]:
    return {row["repo"]: row for row in rows}


def _language_counts(rows: list[sqlite3.Row]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["language"]] += 1
    return dict(counts)


def _ecosystem_score(languages: set[str], language_counts: dict[str, int], stars_today_total: int) -> float:
    language_weights = {"Rust": 7.5, "Go": 6.8, "TypeScript": 5.2, "Python": 4.6, "JavaScript": 4.0, "Javascript": 4.0}
    base = sum(language_weights.get(language, 3.2) for language in languages)
    rarity = sum(5 / math.sqrt(max(language_counts.get(language, 1), 1)) for language in languages)
    attention = min(7, math.log10(stars_today_total + 10) * 2.1)
    mix_bonus = min(4, max(0, len(languages) - 1) * 1.6)
    return round(min(30, base + rarity + attention + mix_bonus), 2)


def _ensure_candidate(candidates: dict[str, dict], name: str, profile: sqlite3.Row | dict | None) -> dict:
    return candidates.setdefault(
        name,
        {
            "handle": name,
            "profile": profile,
            "evidence": [],
            "languages": set(),
            "impact_score": 0.0,
            "raw_impact_score": 0.0,
            "pr_score": 0.0,
            "merged_pr_count": 0,
            "stars_today": 0,
            "total_stars": 0,
            "seen_repos": set(),
        },
    )


def _add_repo_context(candidate: dict, row: sqlite3.Row) -> None:
    if row["repo"] in candidate["seen_repos"]:
        return
    candidate["seen_repos"].add(row["repo"])
    candidate["stars_today"] += int(row["stars_today"] or 0)
    candidate["total_stars"] += int(row["stars"] or 0)
    candidate["languages"].add(row["language"])


def talent_shortlist(
    rows: list[sqlite3.Row],
    profiles: dict[str, sqlite3.Row | dict] | None = None,
    pull_requests: list[sqlite3.Row] | None = None,
) -> list[dict]:
    candidates: dict[str, dict] = {}
    profiles = profiles or {}
    pull_requests = pull_requests or []
    repo_rows = _row_by_repo(rows)
    language_counts = _language_counts(rows)
    for row in rows:
        names = [name.strip() for name in (row["contributors"] or "").split(",") if name.strip()]
        for position, name in enumerate(names, start=1):
            profile = profiles.get(name)
            if not _is_human_profile(profile):
                continue
            current = _ensure_candidate(candidates, name, profile)
            score = momentum_score(row)
            contributor_weight = _contributor_weight(position)
            weighted_score = round(score * contributor_weight, 2)
            current["impact_score"] += weighted_score
            current["raw_impact_score"] += score
            _add_repo_context(current, row)
            current["evidence"].append(
                {
                    "type": "contributor",
                    "repo": row["repo"],
                    "language": row["language"],
                    "stars_today": int(row["stars_today"] or 0),
                    "repo_score": score,
                    "weighted_score": weighted_score,
                    "contributor_position": position,
                    "contributor_weight": contributor_weight,
                    "url": row["url"],
                }
            )
    for pr in pull_requests:
        row = repo_rows.get(pr["repo"])
        if not row:
            continue
        name = pr["author"]
        profile = profiles.get(name)
        if not _is_human_profile(profile):
            continue
        current = _ensure_candidate(candidates, name, profile)
        score = momentum_score(row)
        pr_weighted_score = _pr_score(score, pr["merged_at"])
        current["impact_score"] += pr_weighted_score
        current["raw_impact_score"] += score
        current["pr_score"] += pr_weighted_score
        current["merged_pr_count"] += 1
        _add_repo_context(current, row)
        current["evidence"].append(
            {
                "type": "merged_pr",
                "repo": row["repo"],
                "language": row["language"],
                "stars_today": int(row["stars_today"] or 0),
                "repo_score": score,
                "weighted_score": pr_weighted_score,
                "contributor_position": None,
                "contributor_weight": 0,
                "pr_number": pr["number"],
                "pr_title": pr["title"],
                "merged_at": pr["merged_at"],
                "url": pr["url"],
            }
        )
    ranked = []
    for item in candidates.values():
        evidence = sorted(item["evidence"], key=lambda x: x["weighted_score"], reverse=True)
        projects = list(dict.fromkeys(entry["repo"] for entry in evidence))
        languages = sorted(item["languages"])
        project_count = len({entry["repo"] for entry in evidence})
        language_count = len(languages)
        breadth_score = round(min(45, project_count * 11.5 + language_count * 7.25 + math.log10(item["stars_today"] + 10) * 3), 2)
        ecosystem_score = _ecosystem_score(set(languages), language_counts, item["stars_today"])
        role_fit = _role_fit(set(languages))
        profile = item.get("profile")
        human_confidence = float(_profile_value(profile, "classification_confidence", 0.0) or 0.0)
        profile_strength = _profile_strength(profile)
        best_contributor_weight = max((entry["contributor_weight"] for entry in evidence), default=0)
        confidence_score = _evidence_confidence_score(
            project_count,
            language_count,
            item["impact_score"],
            human_confidence,
            best_contributor_weight,
            profile_strength,
            item["merged_pr_count"],
        )
        confidence = _confidence_label(confidence_score)
        recruiting_score = round(
            item["impact_score"] * 0.68
            + breadth_score * 1.25
            + ecosystem_score * 0.8
            + item["pr_score"] * 0.18
            + profile_strength
            + confidence_score * 0.35,
            2,
        )
        ranked.append(
            {
                "handle": item["handle"],
                "name": _profile_value(profile, "name", "") or "",
                "profile_type": _profile_value(profile, "profile_type", "") or "",
                "human_confidence": human_confidence,
                "human_filter_reason": _profile_value(profile, "classification_reason", "No profile filter evidence stored."),
                "recruiting_score": recruiting_score,
                "impact_score": round(item["impact_score"], 2),
                "raw_impact_score": round(item["raw_impact_score"], 2),
                "pr_score": round(item["pr_score"], 2),
                "merged_pr_count": item["merged_pr_count"],
                "breadth_score": breadth_score,
                "ecosystem_score": ecosystem_score,
                "scarcity_score": ecosystem_score,
                "profile_strength": profile_strength,
                "confidence_score": confidence_score,
                "best_contributor_weight": best_contributor_weight,
                "confidence": confidence,
                "role_fit": role_fit,
                "seniority_signal": _seniority_signal(project_count, item["stars_today"], set(languages)),
                "project_count": project_count,
                "language_count": language_count,
                "stars_today_total": item["stars_today"],
                "projects": projects,
                "languages": languages,
                "evidence": evidence,
                "reason": (
                    f"{project_count} trending project signal(s), {item['stars_today']} stars today across "
                    f"{', '.join(languages)}. Best evidence: {', '.join(projects)}."
                ),
                "contact_strategy": _contact_strategy(confidence, role_fit),
            }
        )
    return sorted(ranked, key=lambda x: x["recruiting_score"], reverse=True)


def technology_trends(rows: list[sqlite3.Row]) -> list[dict]:
    grouped: dict[str, dict] = defaultdict(lambda: {"repos": 0, "stars_today": 0, "stars": 0, "forks": 0, "top_projects": []})
    for row in rows:
        bucket = grouped[row["language"]]
        bucket["repos"] += 1
        bucket["stars_today"] += int(row["stars_today"] or 0)
        bucket["stars"] += int(row["stars"] or 0)
        bucket["forks"] += int(row["forks"] or 0)
        bucket["top_projects"].append(row["repo"])
    trends = []
    for language, data in grouped.items():
        adoption_score = round(data["stars_today"] * 2 + math.log10(data["stars"] + 10) * 25 + data["repos"] * 12, 2)
        trends.append(
            {
                "language": language,
                "repos": data["repos"],
                "stars_today": data["stars_today"],
                "total_stars": data["stars"],
                "forks": data["forks"],
                "adoption_score": adoption_score,
                "top_projects": data["top_projects"],
            }
        )
    return sorted(trends, key=lambda x: x["adoption_score"], reverse=True)


def repository_rankings(rows: list[sqlite3.Row]) -> list[dict]:
    return [
        {
            "repo": row["repo"],
            "language": row["language"],
            "url": row["url"],
            "description": row["description"],
            "stars": row["stars"],
            "forks": row["forks"],
            "stars_today": row["stars_today"],
            "score": momentum_score(row),
        }
        for row in sorted(rows, key=momentum_score, reverse=True)
    ]
