# SpecGrep

Full-text search across IETF RFCs, WHATWG/W3C/WICG specs, and ECMA-262/402 — type a keyword, jump straight to the matching section on the official spec page.

SpecGrep pre-indexes the sections of these documents and lets you search across all of them (or filter to just one source) with instant, ranked results and highlighted snippets.

## Sources

| Tag | What it is |
|---|---|
| `rfc` | IETF RFCs — HTTP, TLS, TCP, DNS, OAuth, JWT, QUIC, etc. |
| `ecma` | ECMA-262 (JavaScript) and ECMA-402 (`Intl`) |
| `w3c` | W3C Recommendations — CSS, IndexedDB, UI Events, etc. |
| `whatwg` | WHATWG living standards — DOM, Fetch, URL, Streams, Encoding |
| `wicg` | WICG incubations — early-stage web platform APIs |

## How it works

- **Ingest** ([ingest/](ingest/)) — scrapers fetch each spec's HTML and parse it into `(anchor, heading, text)` sections, keyed by a `doc_key` so re-running an ingester replaces that document's old sections rather than duplicating them.
- **Search** ([search/db.py](search/db.py)) — sections are stored in a SQLite FTS5 virtual table, queried with BM25 ranking and snippet highlighting.
- **Web app** ([app.py](app.py)) — a small Flask app: takes a query and source filter, runs the search, renders results.

## Local development

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Populate the local search index (each is independent and safe to re-run)
python -m ingest.ingest_rfcs
python -m ingest.ingest_ecma
python -m ingest.ingest_w3c

python app.py   # http://localhost:5000
```

Each ingester also takes specific targets instead of its default list — see `python -m ingest.<name> --help`.
