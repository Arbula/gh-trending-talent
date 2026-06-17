from __future__ import annotations

from datetime import date


def sample_repositories() -> list[dict]:
    today = date.today().isoformat()
    return [
        {
            "snapshot_date": today,
            "language": "Python",
            "rank": 1,
            "repo": "fastapi/fastapi",
            "url": "https://github.com/fastapi/fastapi",
            "description": "High performance web framework for building APIs with Python.",
            "stars": 82600,
            "forks": 7200,
            "stars_today": 184,
            "contributors": "alex-open, tiangolo, Kludex, Mause",
        },
        {
            "snapshot_date": today,
            "language": "TypeScript",
            "rank": 2,
            "repo": "vercel/next.js",
            "url": "https://github.com/vercel/next.js",
            "description": "The React framework for production.",
            "stars": 129100,
            "forks": 28200,
            "stars_today": 241,
            "contributors": "alex-open, ijjk, timneutkens, leerob",
        },
        {
            "snapshot_date": today,
            "language": "Rust",
            "rank": 3,
            "repo": "astral-sh/uv",
            "url": "https://github.com/astral-sh/uv",
            "description": "An extremely fast Python package and project manager, written in Rust.",
            "stars": 55200,
            "forks": 1600,
            "stars_today": 519,
            "contributors": "mira-systems, charliermarsh, konstin, zanieb",
        },
        {
            "snapshot_date": today,
            "language": "Go",
            "rank": 4,
            "repo": "ollama/ollama",
            "url": "https://github.com/ollama/ollama",
            "description": "Get up and running with large language models locally.",
            "stars": 148000,
            "forks": 12100,
            "stars_today": 730,
            "contributors": "mira-systems, jmorganca, dhiltgen, mattwball",
        },
        {
            "snapshot_date": today,
            "language": "JavaScript",
            "rank": 5,
            "repo": "modelcontextprotocol/inspector",
            "url": "https://github.com/modelcontextprotocol/inspector",
            "description": "Visual testing tool for Model Context Protocol servers.",
            "stars": 9100,
            "forks": 760,
            "stars_today": 316,
            "contributors": "alex-open, dsp, joshuataylor, hannesrudolph",
        },
    ]


def sample_profiles() -> list[dict]:
    return [
        {
            "login": "alex-open",
            "profile_type": "User",
            "name": "Alex Chen",
            "bio": "Full-stack engineer building API platforms and web products.",
            "company": "Independent",
            "blog": "https://example.com/alex",
            "public_repos": 58,
            "followers": 1400,
            "classification": "human",
            "classification_confidence": 0.96,
            "classification_reason": "Sample individual profile with human name and product engineering bio.",
        },
        {
            "login": "mira-systems",
            "profile_type": "User",
            "name": "Mira Patel",
            "bio": "Systems engineer focused on local inference, Rust runtimes, and Go services.",
            "company": "Independent",
            "blog": "https://example.com/mira",
            "public_repos": 74,
            "followers": 2100,
            "classification": "human",
            "classification_confidence": 0.96,
            "classification_reason": "Sample individual profile with systems engineering signals.",
        },
    ]
