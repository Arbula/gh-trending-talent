from __future__ import annotations

import json
import math
import os
import re
from typing import Callable, Iterable

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


API_ROOT = "https://api.github.com"
BOT_TERMS = ("[bot]", "bot", "dependabot", "renovate", "github-actions", "semantic-release")
ORG_LIKE_TERMS = ("labs", "team", "foundation", "collective", "community", "official", "opensource", "open-source")


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "GH Trending Talent academic prototype",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_repo_contributors(repo: str, limit: int = 10) -> list[str]:
    url = f"{API_ROOT}/repos/{repo}/contributors"
    response = httpx.get(url, headers=_headers(), params={"per_page": limit}, timeout=20)
    response.raise_for_status()
    contributors = response.json()
    return [item["login"] for item in contributors[:limit] if item.get("login")]


def fetch_user_profile(login: str) -> dict:
    response = httpx.get(f"{API_ROOT}/users/{login}", headers=_headers(), timeout=20)
    response.raise_for_status()
    data = response.json()
    return {
        "login": data.get("login") or login,
        "profile_type": data.get("type") or "",
        "name": data.get("name") or "",
        "bio": data.get("bio") or "",
        "company": data.get("company") or "",
        "blog": data.get("blog") or "",
        "public_repos": int(data.get("public_repos") or 0),
        "followers": int(data.get("followers") or 0),
    }


def fetch_repo_pull_requests(repo: str, limit: int = 20) -> list[dict]:
    response = httpx.get(
        f"{API_ROOT}/repos/{repo}/pulls",
        headers=_headers(),
        params={"state": "closed", "sort": "updated", "direction": "desc", "per_page": min(limit * 2, 100)},
        timeout=20,
    )
    response.raise_for_status()
    rows = []
    for item in response.json():
        if not item.get("merged_at") or not item.get("user") or not item["user"].get("login"):
            continue
        rows.append(
            {
                "repo": repo,
                "number": int(item["number"]),
                "author": item["user"]["login"],
                "title": item.get("title") or "",
                "merged_at": item.get("merged_at") or "",
                "url": item.get("html_url") or "",
            }
        )
        if len(rows) >= limit:
            break
    return rows


def rule_classify_profile(profile: dict) -> dict:
    login = (profile.get("login") or "").lower()
    name = (profile.get("name") or "").lower()
    bio = (profile.get("bio") or "").lower()
    profile_type = profile.get("profile_type") or ""
    text = " ".join([login, name, bio])

    if profile_type == "Organization":
        return _classification("organization", 1.0, "GitHub API profile type is Organization.")
    if any(term in login for term in BOT_TERMS) or re.search(r"(^|[-_])bot($|[-_])", login):
        return _classification("bot", 0.98, "Login matches bot or automation naming pattern.")
    if any(term in text for term in ("automation", "ci", "release bot", "deploy")):
        return _classification("bot", 0.85, "Profile text suggests automation or CI account.")
    if any(term in text for term in ORG_LIKE_TERMS) and not profile.get("name"):
        return _classification("uncertain", 0.45, "User account has organization-like naming and weak personal metadata.")
    if profile_type == "User":
        confidence, reason = _human_confidence(profile, text)
        return _classification("human", confidence, reason)
    return _classification("uncertain", 0.3, "Profile type is missing or not recognized.")


def _human_confidence(profile: dict, text: str) -> tuple[float, str]:
    name = (profile.get("name") or "").strip()
    bio = (profile.get("bio") or "").strip()
    company = (profile.get("company") or "").strip()
    blog = (profile.get("blog") or "").strip()
    followers = int(profile.get("followers") or 0)
    public_repos = int(profile.get("public_repos") or 0)

    name_score = 0.12 if len(name.split()) >= 2 else 0.07 if name else 0
    bio_score = min(0.14, math.log1p(len(bio)) / math.log(180) * 0.14) if bio else 0
    company_score = 0.04 if company else 0
    blog_score = 0.04 if blog else 0
    follower_score = min(0.12, math.log10(followers + 1) / 5 * 0.12)
    repo_score = min(0.08, math.log10(public_repos + 1) / 3 * 0.08)
    org_like_penalty = 0.12 if any(term in text for term in ORG_LIKE_TERMS) else 0

    confidence = (
        0.52
        + name_score
        + bio_score
        + company_score
        + blog_score
        + follower_score
        + repo_score
        - org_like_penalty
    )
    confidence = max(0.45, min(0.98, confidence))

    parts = [
        "GitHub API profile type is User",
        f"name={name_score:.2f}",
        f"bio={bio_score:.2f}",
        f"followers={follower_score:.2f}",
        f"repos={repo_score:.2f}",
    ]
    if company_score:
        parts.append("company=0.04")
    if blog_score:
        parts.append("blog=0.04")
    if org_like_penalty:
        parts.append("org-like-name-penalty=-0.12")
    return confidence, "; ".join(parts) + "."


def ai_classify_profile(profile: dict) -> dict | None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from groq import Groq
    except Exception:
        return None

    prompt = {
        "task": "Classify whether this GitHub account is an individual human engineer, organization/team account, bot/automation account, or uncertain.",
        "rules": [
            "Be conservative.",
            "If evidence is weak, return uncertain.",
            "Return JSON only with classification, confidence, reason.",
        ],
        "allowed_classifications": ["human", "organization", "bot", "uncertain"],
        "profile": {
            key: profile.get(key)
            for key in ["login", "profile_type", "name", "bio", "company", "blog", "public_repos", "followers"]
        },
    }
    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant"),
            messages=[{"role": "user", "content": json.dumps(prompt)}],
            temperature=0,
            max_tokens=220,
        )
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        classification = parsed.get("classification")
        if classification not in {"human", "organization", "bot", "uncertain"}:
            return None
        return _classification(
            classification,
            float(parsed.get("confidence") or 0.5),
            f"AI review: {parsed.get('reason') or 'No reason returned.'}",
        )
    except Exception:
        return None


def classify_profile(profile: dict, use_ai: bool = False) -> dict:
    rule_result = rule_classify_profile(profile)
    if use_ai and rule_result["classification"] == "uncertain":
        ai_result = ai_classify_profile(profile)
        if ai_result:
            return ai_result
    return rule_result


def enrich_rows_with_github(
    rows: list[dict],
    max_contributors: int = 10,
    max_pull_requests: int = 0,
    use_ai: bool = False,
    progress: Callable[[str], None] | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    profiles: dict[str, dict] = {}
    pull_requests: list[dict] = []
    total = len(rows)
    for index, row in enumerate(rows, start=1):
        if progress:
            progress(f"github repo {index}/{total}: {row['repo']}")
        logins = _safe_fetch_contributors(row["repo"], max_contributors)
        if logins:
            row["contributors"] = ", ".join(logins)
        if max_pull_requests > 0:
            repo_prs = _safe_fetch_pull_requests(row["repo"], max_pull_requests)
            pull_requests.extend(repo_prs)
            logins.extend([pr["author"] for pr in repo_prs])
        for login in _contributors_from_row(row):
            logins.append(login)
        for login in sorted(set(logins)):
            if login in profiles:
                continue
            profile = _safe_fetch_profile(login)
            if not profile:
                continue
            profile.update(classify_profile(profile, use_ai=use_ai))
            profiles[profile["login"]] = profile
        if progress:
            progress(
                f"github repo {index}/{total}: {row['repo']} done "
                f"contributors={len(_contributors_from_row(row))} prs={len([pr for pr in pull_requests if pr['repo'] == row['repo']])} "
                f"profiles_cached={len(profiles)}"
            )
    return rows, list(profiles.values()), pull_requests


def classify_known_logins(logins: Iterable[str], use_ai: bool = False) -> list[dict]:
    profiles = []
    for login in sorted(set(logins)):
        profile = _safe_fetch_profile(login)
        if not profile:
            continue
        profile.update(classify_profile(profile, use_ai=use_ai))
        profiles.append(profile)
    return profiles


def _contributors_from_row(row: dict) -> list[str]:
    return [name.strip() for name in (row.get("contributors") or "").split(",") if name.strip()]


def _safe_fetch_contributors(repo: str, limit: int) -> list[str]:
    try:
        return fetch_repo_contributors(repo, limit=limit)
    except Exception:
        return []


def _safe_fetch_profile(login: str) -> dict | None:
    try:
        return fetch_user_profile(login)
    except Exception:
        return None


def _safe_fetch_pull_requests(repo: str, limit: int) -> list[dict]:
    try:
        return fetch_repo_pull_requests(repo, limit=limit)
    except Exception:
        return []


def _classification(classification: str, confidence: float, reason: str) -> dict:
    return {
        "classification": classification,
        "classification_confidence": round(max(0, min(1, confidence)), 2),
        "classification_reason": reason,
    }
