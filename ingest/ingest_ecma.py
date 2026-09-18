"""Fetch TC39/ECMA specs (ecmarkup-generated HTML) and index their clauses
into specgrep's search database.

ecmarkup wraps each clause/annex in a custom <emu-clause>/<emu-annex>
element, nested like RFC's <section> tags, with the clause number and
title combined in a single <h1><span class="secnum">N.N</span> Title</h1>.

Usage:
    python -m ingest.ingest_ecma                        # ingest the default starter list
    python -m ingest.ingest_ecma --url my-key https://example.org/spec/
"""

import argparse
import time

import httpx
from bs4 import BeautifulSoup

from search.db import connect, replace_document

USER_AGENT = "specgrep-ingest/0.1 (+personal project; polite crawl)"
CLAUSE_TAGS = ["emu-clause", "emu-annex"]

DEFAULT_SPECS = [
    ("ecma262", "https://tc39.es/ecma262/", "ecma"),
    ("ecma402", "https://tc39.es/ecma402/", "ecma"),
]


def fetch_spec(url, client):
    resp = client.get(url, timeout=60)
    resp.raise_for_status()
    return str(resp.url), resp.text


def parse_sections(html):
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    sections = []
    for clause in soup.find_all(CLAUSE_TAGS, id=True):
        heading_tag = clause.find("h1")
        heading_text = heading_tag.get_text(" ", strip=True) if heading_tag else clause["id"]

        # Re-parse a standalone copy so decomposing nested clauses (to get
        # this clause's own text, not its children's) doesn't mutate the
        # shared tree. Scope find_all to the cloned root tag itself, not
        # the whole clone, so the root isn't matched and decomposed too.
        clone = BeautifulSoup(str(clause), "lxml")
        root = clone.find(clause.name)
        for nested in root.find_all(CLAUSE_TAGS):
            nested.decompose()
        text = root.get_text(" ", strip=True)

        anchor = f"#{clause['id']}"
        if text.strip() and text.strip() != heading_text.strip():
            sections.append((anchor, heading_text, text))

    return title, sections


def ingest(specs, delay=1.0):
    conn = connect()
    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
        for doc_key, url, source in specs:
            try:
                final_url, html = fetch_spec(url, client)
            except httpx.HTTPStatusError as exc:
                print(f"{doc_key}: fetch failed ({exc.response.status_code}), skipping")
                continue
            except httpx.RequestError as exc:
                print(f"{doc_key}: request error ({exc}), skipping")
                continue

            title, sections = parse_sections(html)
            if not sections:
                print(f"{doc_key}: no <emu-clause>/<emu-annex> tags found, skipping (unsupported format)")
                continue

            replace_document(conn, doc_key, title or doc_key, final_url, source, sections)
            print(f"{doc_key}: indexed {len(sections)} sections — {title}")
            time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url", nargs=2, action="append", metavar=("DOC_KEY", "URL"),
        help="Ingest one specific spec by key and URL (repeatable)",
    )
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds to wait between requests")
    args = parser.parse_args()
    specs = [(key, url, "ecma") for key, url in args.url] if args.url else DEFAULT_SPECS
    ingest(specs, delay=args.delay)


if __name__ == "__main__":
    main()
