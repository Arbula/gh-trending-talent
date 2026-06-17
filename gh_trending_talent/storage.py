from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable


DEFAULT_DB = Path("data/gh_trending_talent.sqlite")


SCHEMA = """
CREATE TABLE IF NOT EXISTS repositories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    language TEXT NOT NULL,
    rank INTEGER NOT NULL,
    repo TEXT NOT NULL,
    url TEXT NOT NULL,
    description TEXT,
    stars INTEGER NOT NULL,
    forks INTEGER NOT NULL,
    stars_today INTEGER NOT NULL,
    contributors TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(snapshot_date, language, repo)
);

CREATE TABLE IF NOT EXISTS github_profiles (
    login TEXT PRIMARY KEY,
    profile_type TEXT,
    name TEXT,
    bio TEXT,
    company TEXT,
    blog TEXT,
    public_repos INTEGER DEFAULT 0,
    followers INTEGER DEFAULT 0,
    classification TEXT NOT NULL DEFAULT 'uncertain',
    classification_confidence REAL NOT NULL DEFAULT 0,
    classification_reason TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pull_requests (
    repo TEXT NOT NULL,
    number INTEGER NOT NULL,
    author TEXT NOT NULL,
    title TEXT,
    merged_at TEXT,
    url TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(repo, number)
);
"""


def connect(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def upsert_repositories(conn: sqlite3.Connection, rows: Iterable[dict]) -> int:
    payload = list(rows)
    conn.executemany(
        """
        INSERT INTO repositories (
            snapshot_date, language, rank, repo, url, description,
            stars, forks, stars_today, contributors
        )
        VALUES (
            :snapshot_date, :language, :rank, :repo, :url, :description,
            :stars, :forks, :stars_today, :contributors
        )
        ON CONFLICT(snapshot_date, language, repo) DO UPDATE SET
            rank=excluded.rank,
            url=excluded.url,
            description=excluded.description,
            stars=excluded.stars,
            forks=excluded.forks,
            stars_today=excluded.stars_today,
            contributors=excluded.contributors
        """,
        payload,
    )
    conn.commit()
    return len(payload)


def clear_data(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM repositories")
    conn.execute("DELETE FROM github_profiles")
    conn.execute("DELETE FROM pull_requests")
    conn.commit()


def latest_repositories(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    row = conn.execute("SELECT MAX(snapshot_date) AS snapshot_date FROM repositories").fetchone()
    if not row or not row["snapshot_date"]:
        return []
    return conn.execute(
        """
        SELECT * FROM repositories
        WHERE snapshot_date = ?
        ORDER BY stars_today DESC, rank ASC
        """,
        (row["snapshot_date"],),
    ).fetchall()


def upsert_profiles(conn: sqlite3.Connection, rows: Iterable[dict]) -> int:
    payload = list(rows)
    if not payload:
        return 0
    conn.executemany(
        """
        INSERT INTO github_profiles (
            login, profile_type, name, bio, company, blog, public_repos, followers,
            classification, classification_confidence, classification_reason
        )
        VALUES (
            :login, :profile_type, :name, :bio, :company, :blog, :public_repos, :followers,
            :classification, :classification_confidence, :classification_reason
        )
        ON CONFLICT(login) DO UPDATE SET
            profile_type=excluded.profile_type,
            name=excluded.name,
            bio=excluded.bio,
            company=excluded.company,
            blog=excluded.blog,
            public_repos=excluded.public_repos,
            followers=excluded.followers,
            classification=excluded.classification,
            classification_confidence=excluded.classification_confidence,
            classification_reason=excluded.classification_reason,
            updated_at=CURRENT_TIMESTAMP
        """,
        payload,
    )
    conn.commit()
    return len(payload)


def profiles_by_login(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    rows = conn.execute("SELECT * FROM github_profiles").fetchall()
    return {row["login"]: row for row in rows}


def upsert_pull_requests(conn: sqlite3.Connection, rows: Iterable[dict]) -> int:
    payload = list(rows)
    if not payload:
        return 0
    conn.executemany(
        """
        INSERT INTO pull_requests (repo, number, author, title, merged_at, url)
        VALUES (:repo, :number, :author, :title, :merged_at, :url)
        ON CONFLICT(repo, number) DO UPDATE SET
            author=excluded.author,
            title=excluded.title,
            merged_at=excluded.merged_at,
            url=excluded.url
        """,
        payload,
    )
    conn.commit()
    return len(payload)


def pull_requests_for_repos(conn: sqlite3.Connection, repos: Iterable[str]) -> list[sqlite3.Row]:
    repo_list = sorted(set(repos))
    if not repo_list:
        return []
    placeholders = ",".join("?" for _ in repo_list)
    return conn.execute(
        f"""
        SELECT * FROM pull_requests
        WHERE repo IN ({placeholders})
        ORDER BY merged_at DESC
        """,
        repo_list,
    ).fetchall()
