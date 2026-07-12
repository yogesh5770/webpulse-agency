"""Storage for leads + used queries, with dedup so the same business is never
processed twice.

Two backends, chosen automatically:
  - SQLite (default): a local `leads.db` file. Zero-config for local dev.
  - Postgres: used when DATABASE_URL is set (e.g. Supabase/Neon/Railway free
    tier). This is what you want on Hugging Face free Spaces, where the local
    filesystem is EPHEMERAL and resets on rebuild/sleep -- Postgres keeps your
    lead history.

The rest of the app calls the same functions regardless of backend. We keep
the SQL portable and translate the few dialect differences (placeholder style,
upsert clause) in one place.
"""
import time
from contextlib import contextmanager

import config

# Detect backend from config once.
_PG = bool(config.DATABASE_URL)

if _PG:
    import psycopg2
    import psycopg2.extras
    _PH = "%s"                      # Postgres placeholder
else:
    import sqlite3
    _PH = "?"                       # SQLite placeholder


def _sql(query: str) -> str:
    """Write all SQL with '?' placeholders; translate for Postgres."""
    return query.replace("?", _PH) if _PG else query


# Lead lifecycle:
#   new       -> just discovered, not processed
#   building  -> a worker picked it up and is generating the site
#   published -> site is live
#   contacted -> outreach message sent
#   failed    -> something went wrong (kept so we can retry / inspect)
STATUSES = ("new", "building", "published", "contacted", "failed")


@contextmanager
def _conn():
    if _PG:
        con = psycopg2.connect(config.DATABASE_URL, connect_timeout=30,
                               cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        con = sqlite3.connect(config.DB_PATH, timeout=30)
        con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def init_db() -> None:
    # SERIAL/AUTOINCREMENT differences don't matter here (no surrogate keys).
    with _conn() as con:
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                place_id     TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                category     TEXT,
                phone        TEXT,
                address      TEXT,
                lat          REAL,
                lng          REAL,
                photos_json  TEXT,
                details_json TEXT,
                status       TEXT NOT NULL DEFAULT 'new',
                site_dir     TEXT,
                live_url     TEXT,
                message      TEXT,
                error        TEXT,
                created_at   BIGINT,
                updated_at   BIGINT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_status ON leads(status)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS used_queries (
                query      TEXT PRIMARY KEY,
                created_at BIGINT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS site_files (
                place_id   TEXT NOT NULL,
                path       TEXT NOT NULL,
                content    TEXT,
                updated_at BIGINT,
                PRIMARY KEY (place_id, path)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sitefiles_pid ON site_files(place_id)")


def get_used_queries() -> list[str]:
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT query FROM used_queries")
        return [r["query"] for r in _rows(cur)]


def add_used_query(query: str) -> None:
    with _conn() as con:
        cur = con.cursor()
        cur.execute(
            _sql("INSERT INTO used_queries (query, created_at) VALUES (?, ?) "
                 "ON CONFLICT (query) DO NOTHING"),
            (query, int(time.time())),
        )


def lead_exists(place_id: str) -> bool:
    with _conn() as con:
        cur = con.cursor()
        cur.execute(_sql("SELECT 1 FROM leads WHERE place_id = ?"), (place_id,))
        return cur.fetchone() is not None


def add_lead(lead: dict) -> bool:
    """Insert a newly discovered lead. Returns False if it already exists
    (dedup), True if it was inserted. Uses ON CONFLICT so it works the same
    on both backends."""
    now = int(time.time())
    with _conn() as con:
        cur = con.cursor()
        cur.execute(
            _sql(
                """
                INSERT INTO leads
                    (place_id, name, category, phone, address, lat, lng,
                     photos_json, details_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)
                ON CONFLICT (place_id) DO NOTHING
                """
            ),
            (
                lead["place_id"], lead.get("name", ""), lead.get("category", ""),
                lead.get("phone", ""), lead.get("address", ""), lead.get("lat"),
                lead.get("lng"), lead.get("photos_json", "[]"),
                lead.get("details_json", "{}"), now, now,
            ),
        )
        # rowcount == 0 -> conflict (duplicate); == 1 -> inserted.
        return cur.rowcount == 1


def update_lead(place_id: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = int(time.time())
    cols = ", ".join(f"{k} = ?" for k in fields)
    with _conn() as con:
        cur = con.cursor()
        cur.execute(
            _sql(f"UPDATE leads SET {cols} WHERE place_id = ?"),
            (*fields.values(), place_id),
        )


def next_new_lead() -> dict | None:
    """Atomically claim the oldest 'new' lead and mark it 'building' so two
    workers never grab the same one. On Postgres we use SELECT ... FOR UPDATE
    SKIP LOCKED for true concurrency safety; SQLite is single-writer so the
    transaction is enough."""
    with _conn() as con:
        cur = con.cursor()
        if _PG:
            cur.execute(
                "SELECT * FROM leads WHERE status = 'new' "
                "ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"
            )
        else:
            cur.execute(
                "SELECT * FROM leads WHERE status = 'new' ORDER BY created_at LIMIT 1"
            )
        row = cur.fetchone()
        if row is None:
            return None
        row = dict(row)
        cur.execute(
            _sql("UPDATE leads SET status = 'building', updated_at = ? WHERE place_id = ?"),
            (int(time.time()), row["place_id"]),
        )
        return row


def get_lead(place_id: str) -> dict | None:
    with _conn() as con:
        cur = con.cursor()
        cur.execute(_sql("SELECT * FROM leads WHERE place_id = ?"), (place_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def all_leads() -> list[dict]:
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM leads ORDER BY updated_at DESC")
        return _rows(cur)


def counts_by_status() -> dict:
    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT status, COUNT(*) AS n FROM leads GROUP BY status")
        return {r["status"]: r["n"] for r in _rows(cur)}


# ---- site file storage (a "folder in the DB", one row per file) ------
# Each website's files live here so IDE edits persist across restarts (the
# host disk is ephemeral). All rows sharing a place_id ARE that site's folder.

def site_list_files(place_id: str) -> list[str]:
    with _conn() as con:
        cur = con.cursor()
        cur.execute(_sql("SELECT path FROM site_files WHERE place_id = ? ORDER BY path"), (place_id,))
        return [r["path"] for r in _rows(cur)]


def site_read_file(place_id: str, path: str) -> str | None:
    with _conn() as con:
        cur = con.cursor()
        cur.execute(_sql("SELECT content FROM site_files WHERE place_id = ? AND path = ?"),
                    (place_id, path))
        row = cur.fetchone()
        return None if row is None else (dict(row)["content"] or "")


def site_write_file(place_id: str, path: str, content: str) -> None:
    """Insert or update one file (upsert). Portable across SQLite/Postgres."""
    now = int(time.time())
    with _conn() as con:
        cur = con.cursor()
        cur.execute(
            _sql(
                "INSERT INTO site_files (place_id, path, content, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT (place_id, path) DO UPDATE SET "
                "content = excluded.content, updated_at = excluded.updated_at"
            ),
            (place_id, path, content, now),
        )


def site_delete_file(place_id: str, path: str) -> None:
    with _conn() as con:
        cur = con.cursor()
        cur.execute(_sql("DELETE FROM site_files WHERE place_id = ? AND path = ?"),
                    (place_id, path))


def site_rename_file(place_id: str, path: str, new_path: str) -> None:
    with _conn() as con:
        cur = con.cursor()
        cur.execute(_sql("UPDATE site_files SET path = ?, updated_at = ? "
                         "WHERE place_id = ? AND path = ?"),
                    (new_path, int(time.time()), place_id, path))


def site_all_files(place_id: str) -> dict:
    """Return {path: content} for a whole site (used to materialize/deploy)."""
    with _conn() as con:
        cur = con.cursor()
        cur.execute(_sql("SELECT path, content FROM site_files WHERE place_id = ?"), (place_id,))
        return {r["path"]: (r["content"] or "") for r in _rows(cur)}


def site_replace_all(place_id: str, files: dict) -> None:
    """Replace a site's entire fileset with `files` ({path: content}) in one
    transaction -- used to sync a working dir back to the DB after an edit."""
    now = int(time.time())
    with _conn() as con:
        cur = con.cursor()
        cur.execute(_sql("DELETE FROM site_files WHERE place_id = ?"), (place_id,))
        for path, content in files.items():
            cur.execute(
                _sql("INSERT INTO site_files (place_id, path, content, updated_at) "
                     "VALUES (?, ?, ?, ?)"),
                (place_id, path, content, now),
            )


def site_storage_bytes() -> int:
    """Approx total bytes stored across all site files (for the dashboard)."""
    with _conn() as con:
        cur = con.cursor()
        if _PG:
            cur.execute("SELECT COALESCE(SUM(LENGTH(content)), 0) AS n FROM site_files")
        else:
            cur.execute("SELECT COALESCE(SUM(LENGTH(content)), 0) AS n FROM site_files")
        return int(_rows(cur)[0]["n"])


def backend_name() -> str:
    """For the dashboard: which store is active."""
    return "Postgres" if _PG else "SQLite (local file)"
