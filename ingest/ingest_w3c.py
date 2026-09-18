"""Fetch WHATWG/W3C/WICG specs (Bikeshed-generated HTML) and index their
numbered sections into specgrep's search database.

Only Bikeshed-generated specs are supported here, identified by numbered
headings carrying a `data-level` attribute (WHATWG living standards and
most W3C CSS Working Group specs use Bikeshed). Specs built with other
tools (ReSpec, hand-authored HTML — e.g. WAI-ARIA) don't have that marker
and are skipped with a message; that format is a separate ingester to
write later, not handled here.

Usage:
    python -m ingest.ingest_w3c                        # ingest the default starter list
    python -m ingest.ingest_w3c --url my-key https://example.org/spec/
"""

import argparse
import time

import httpx
from bs4 import BeautifulSoup

from search.db import connect, replace_document

USER_AGENT = "specgrep-ingest/0.1 (+personal project; polite crawl)"
HEADING_TAGS = ["h2", "h3", "h4", "h5", "h6"]

# (doc_key, url, source) — source distinguishes the standards body, since
# WHATWG living standards and W3C Recommendations are governed separately
# even though people colloquially lump them together as "web specs".
DEFAULT_SPECS = [
    ("dom", "https://dom.spec.whatwg.org/", "whatwg"),
    ("fetch", "https://fetch.spec.whatwg.org/", "whatwg"),
    ("url", "https://url.spec.whatwg.org/", "whatwg"),
    ("streams", "https://streams.spec.whatwg.org/", "whatwg"),
    ("encoding", "https://encoding.spec.whatwg.org/", "whatwg"),
    ("css-color-4", "https://www.w3.org/TR/css-color-4/", "w3c"),
    ("css-flexbox-1", "https://www.w3.org/TR/css-flexbox-1/", "w3c"),
    ("css-grid-1", "https://www.w3.org/TR/css-grid-1/", "w3c"),
    ("selectors-4", "https://www.w3.org/TR/selectors-4/", "w3c"),
    ("uievents", "https://www.w3.org/TR/uievents/", "w3c"),
    ("indexeddb-3", "https://www.w3.org/TR/IndexedDB-3/", "w3c"),
    ("css-position-3", "https://www.w3.org/TR/css-position-3/", "w3c"),
    ("css-values-4", "https://www.w3.org/TR/css-values-4/", "w3c"),
    ("css-sizing-3", "https://www.w3.org/TR/css-sizing-3/", "w3c"),
    ("css-cascade-5", "https://www.w3.org/TR/css-cascade-5/", "w3c"),
    ("mediaqueries-5", "https://www.w3.org/TR/mediaqueries-5/", "w3c"),
    ("css-transforms-1", "https://www.w3.org/TR/css-transforms-1/", "w3c"),
    ("intersection-observer", "https://www.w3.org/TR/intersection-observer/", "w3c"),
    ("resize-observer", "https://www.w3.org/TR/resize-observer/", "w3c"),
    ("pointerevents3", "https://www.w3.org/TR/pointerevents3/", "w3c"),
    # WICG incubations — early-stage web platform APIs, not yet W3C
    # Recommendations, but Bikeshed-generated like the specs above.
    ("file-system-access", "https://wicg.github.io/file-system-access/", "wicg"),
    ("idle-detection", "https://wicg.github.io/idle-detection/", "wicg"),
    ("background-fetch", "https://wicg.github.io/background-fetch/", "wicg"),
    ("local-font-access", "https://wicg.github.io/local-font-access/", "wicg"),
    ("web-locks", "https://w3c.github.io/web-locks/", "wicg"),
]


def fetch_spec(url, client):
    resp = client.get(url, timeout=30)
    resp.raise_for_status()
    return str(resp.url), resp.text


def heading_label(tag):
    secno = tag.find(class_="secno")
    content = tag.find(class_="content")
    if secno and content:
        return f"{secno.get_text(strip=True)} {content.get_text(' ', strip=True)}"
    return tag.get_text(" ", strip=True)


def content_between(start, stop):
    """Text of all siblings after `start` up to (not including) `stop`.
    Relies on Bikeshed's flat output where headings and their body content
    are direct siblings, not wrapped in per-section containers — so a
    heading's "own" text is simply everything before the next heading."""
    parts = []
    for sib in start.find_next_siblings():
        if sib is stop:
            break
        parts.append(sib.get_text(" ", strip=True))
    return " ".join(p for p in parts if p)


def parse_sections(html):
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    headings = [
        h for h in soup.find_all(HEADING_TAGS, attrs={"data-level": True})
        if h.get("id")
    ]
    sections = []
    for i, heading in enumerate(headings):
        next_heading = headings[i + 1] if i + 1 < len(headings) else None
        text = content_between(heading, next_heading)
        heading_text = heading_label(heading)
        anchor = f"#{heading['id']}"
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
                print(f"{doc_key}: no Bikeshed-style numbered headings found, skipping (unsupported format)")
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
    specs = [(key, url, "w3c") for key, url in args.url] if args.url else DEFAULT_SPECS
    ingest(specs, delay=args.delay)


if __name__ == "__main__":
    main()
