import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "specgrep.db"

SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS entries USING fts5(
    heading,
    text,
    doc_title UNINDEXED,
    doc_url UNINDEXED,
    anchor UNINDEXED,
    source UNINDEXED,
    doc_key UNINDEXED
);
"""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def replace_document(conn, doc_key, doc_title, doc_url, source, sections):
    """Replace all indexed sections for one document. `sections` is an
    iterable of (anchor, heading, text) tuples."""
    conn.execute("DELETE FROM entries WHERE doc_key = ?", (doc_key,))
    conn.executemany(
        """
        INSERT INTO entries (heading, text, doc_title, doc_url, anchor, source, doc_key)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (heading, text, doc_title, doc_url, anchor, source, doc_key)
            for anchor, heading, text in sections
            if text.strip()
        ],
    )
    conn.commit()


def _fts_query(raw):
    """Quote each token as its own phrase so punctuation in user input
    (hyphens, colons, parens) can't be parsed as FTS5 query syntax."""
    tokens = raw.split()
    if not tokens:
        return '""'
    return " ".join('"{}"'.format(t.replace('"', '""')) for t in tokens)


def list_sources(conn):
    rows = conn.execute("SELECT DISTINCT source FROM entries ORDER BY source").fetchall()
    return [r["source"] for r in rows]


def search(conn, query, limit=20, sources=None):
    match_expr = _fts_query(query)
    sql = """
        SELECT doc_title, doc_url, anchor, heading, source,
               snippet(entries, 1, '[', ']', ' … ', 12) AS snippet,
               bm25(entries) AS rank
        FROM entries
        WHERE entries MATCH ?
    """
    params = [match_expr]
    if sources:
        sql += f" AND source IN ({','.join('?' for _ in sources)})"
        params.extend(sources)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    return conn.execute(sql, params).fetchall()
