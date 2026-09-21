"""Small versioned-SQL migration runner for Postgres (ADR-0012, Option 3).

Migrations are plain `.sql` files in `migrations/`, named `NNNN_description.sql`. Applied
versions are tracked in a `schema_migrations` table this runner creates itself (not by a
migration file, so it exists before migration 0001 ever runs).

ADR-0012 names three properties the runner must have "or it is worse than a real tool":

- **Deterministic ordering** — by the numeric version prefix, parsed as an int, not by
  filename string comparison or directory-listing order.
- **A Postgres advisory lock** — held for the connection's session, non-blocking: a second
  runner started while one is already applying migrations fails immediately rather than
  silently racing it.
- **A checksum per applied migration** — a SHA-256 of the file's bytes, recorded alongside
  its version. If a migration file changes after being applied, the next run refuses to
  continue rather than silently reapplying or silently skipping it.

Each migration runs in its own transaction (`conn.transaction()`), so Postgres's
transactional DDL means a migration that fails partway leaves no trace — the schema is
exactly as it was before that migration started, and every earlier migration in the same run
stays applied and committed.

The trigger for replacing this with a real tool (Alembic etc.) is the first migration that
needs a Python data backfill, branching, or a down-migration — anything beyond ordered
forward-only SQL.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"

# Arbitrary fixed key, unique to this project's migration lock — two processes calling
# run_migrations() concurrently contend on the same key regardless of which directory or
# database they point at.
ADVISORY_LOCK_KEY = 0x64616331  # ASCII 'dac1'

_VERSION_RE = re.compile(r"^(\d+)_.+\.sql$")


@dataclass(frozen=True)
class Migration:
    version: str
    path: Path
    checksum: str

    @property
    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")


def discover_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """All migrations in `directory`, ordered by numeric version prefix.

    Ordering is by the parsed integer, not the filename string or whatever order the
    filesystem happens to hand back from a directory listing — `2_x.sql` sorts before
    `10_y.sql` here even though it would not under a plain string sort.
    """
    migrations = []
    for path in directory.glob("*.sql"):
        match = _VERSION_RE.match(path.name)
        if not match:
            raise ValueError(f"migration file {path.name!r} doesn't match NNNN_description.sql")
        migrations.append(
            Migration(
                version=match.group(1),
                path=path,
                checksum=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    versions = [m.version for m in migrations]
    if len(set(versions)) != len(versions):
        raise ValueError(f"duplicate migration version among {sorted(versions)}")
    return sorted(migrations, key=lambda m: int(m.version))


def _ensure_migrations_table(conn: psycopg.Connection) -> None:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     text PRIMARY KEY,
                checksum    text NOT NULL,
                applied_at  timestamptz NOT NULL DEFAULT now()
            )
            """
        )


def _applied_versions(conn: psycopg.Connection) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT version, checksum FROM schema_migrations")
        return dict(cur.fetchall())


def _connect(conninfo: str | dict) -> psycopg.Connection:
    if isinstance(conninfo, dict):
        return psycopg.connect(**conninfo, autocommit=True)
    return psycopg.connect(conninfo, autocommit=True)


def run_migrations(conninfo: str | dict, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every not-yet-applied migration in `directory`, in version order.

    `conninfo` is either a psycopg conninfo string or a dict of `psycopg.connect` keyword
    arguments; this function opens and closes its own connection so it can hold a session-
    level advisory lock for its own lifetime.

    Returns the versions applied by this call, oldest first (empty if already up to date).

    Raises `RuntimeError` if:
    - another runner already holds the advisory lock (non-blocking — this call fails
      immediately rather than waiting), or
    - an already-applied migration's file no longer matches its recorded checksum (the
      version is named in the message; nothing is reapplied or skipped).

    A migration whose SQL fails partway is rolled back by Postgres's transactional DDL and
    the exception propagates from here as-is: the schema is left exactly as it was before
    that migration, and this function stops there without attempting later ones.
    """
    conn = _connect(conninfo)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (ADVISORY_LOCK_KEY,))
            (got_lock,) = cur.fetchone()
        if not got_lock:
            raise RuntimeError(
                "another migration runner already holds the advisory lock "
                f"({ADVISORY_LOCK_KEY:#x}) — refusing to run concurrently"
            )

        try:
            _ensure_migrations_table(conn)
            applied = _applied_versions(conn)
            migrations = discover_migrations(directory)

            for m in migrations:
                if m.version in applied and applied[m.version] != m.checksum:
                    raise RuntimeError(
                        f"migration {m.version} ({m.path.name}) has changed since it was "
                        f"applied — recorded checksum {applied[m.version]}, file now hashes "
                        f"to {m.checksum}. Refusing to continue: edit a new migration "
                        "instead of changing one that has already run."
                    )

            newly_applied: list[str] = []
            for m in migrations:
                if m.version in applied:
                    continue
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute(m.sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                        (m.version, m.checksum),
                    )
                newly_applied.append(m.version)
            return newly_applied
        finally:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_KEY,))
    finally:
        conn.close()
