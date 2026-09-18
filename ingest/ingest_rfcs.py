"""Fetch IETF RFCs (HTML edition) and index their sections into specgrep's
search database.

Only RFCs published with structured xml2rfc-style HTML (roughly 2017+) can
be parsed here, since the parser relies on `<section id="section-N">` tags
with numbered headings. Older plaintext-derived RFCs are skipped with a
message rather than mis-parsed.

Usage:
    python -m ingest.ingest_rfcs                # ingest the default starter list
    python -m ingest.ingest_rfcs --rfc 9110 8446 # ingest specific RFC numbers
"""

import argparse
import re
import time

import httpx
from bs4 import BeautifulSoup

from search.db import connect, replace_document

RFC_HTML_URL = "https://www.rfc-editor.org/rfc/rfc{num}.html"
USER_AGENT = "specgrep-ingest/0.1 (+personal project; polite crawl)"

# A curated starter batch of well-known, modern RFCs likely to have
# structured HTML. Expand with --rfc, or move to a full rfc-index.xml crawl
# once this vertical slice is proven out.
DEFAULT_RFCS = [
    9110, 9111, 9112, 9113, 9114,  # HTTP semantics / caching / 1.1 / 2 / 3
    8446,  # TLS 1.3
    8259,  # JSON
    8949,  # CBOR
    9293,  # TCP
    8484,  # DNS over HTTPS
    8555,  # ACME
    9068,  # JWT profile for OAuth access tokens
    9457,  # Problem Details for HTTP APIs
    8615,  # well-known URIs
    8288,  # Web Linking
    6749,  # OAuth 2.0 (older format — may get skipped)
    6455,  # WebSocket (older format — may get skipped)
    7519,  # JWT (older format — may get skipped)
    9000,  # QUIC transport
    9001,  # QUIC over TLS
    9002,  # QUIC loss detection and congestion control
    9218,  # Extensible Prioritization Scheme for HTTP
    9211,  # The Cache-Status HTTP Response Header Field
    9325,  # TLS recommendations
    9420,  # Messaging Layer Security (MLS) protocol
    9499,  # DNS Terminology
]


def fetch_rfc(num, client):
    url = RFC_HTML_URL.format(num=num)
    resp = client.get(url, timeout=20)
    resp.raise_for_status()
    return url, resp.text


def parse_sections(html):
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    sections = []
    for sec in soup.find_all("section", id=re.compile(r"^section-\d")):
        heading_tag = sec.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        heading = None
        if heading_tag:
            number = heading_tag.find("a", class_="section-number")
            name = heading_tag.find("a", class_="section-name")
            if number and name:
                heading = f"{number.get_text(strip=True)} {name.get_text(strip=True)}"
            else:
                heading = heading_tag.get_text(" ", strip=True)

        # Re-parse a standalone copy so decomposing nested <section> tags
        # (to get this section's own text, not its children's) doesn't
        # mutate the shared tree we're still iterating over. find_all on the
        # cloned *root* tag (not the soup) so it only matches descendants,
        # not the root section itself.
        clone = BeautifulSoup(str(sec), "lxml")
        root = clone.find("section")
        for nested in root.find_all("section"):
            nested.decompose()
        text = root.get_text(" ", strip=True)

        anchor = f"#{sec['id']}"
        heading_text = heading or sec["id"]
        # Skip pure container sections (e.g. "1. Introduction" whose only
        # content is subsections) — they'd otherwise just duplicate the
        # heading as a low-value search result.
        if text.strip() and text.strip() != heading_text.strip():
            sections.append((anchor, heading_text, text))

    return title, sections


def ingest(numbers, delay=1.0):
    conn = connect()
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        for num in numbers:
            doc_key = f"rfc{num}"
            try:
                url, html = fetch_rfc(num, client)
            except httpx.HTTPStatusError as exc:
                print(f"rfc{num}: fetch failed ({exc.response.status_code}), skipping")
                continue
            except httpx.RequestError as exc:
                print(f"rfc{num}: request error ({exc}), skipping")
                continue

            title, sections = parse_sections(html)
            if not sections:
                print(f"rfc{num}: no structured <section> tags found, skipping (likely pre-xml2rfc format)")
                continue

            replace_document(conn, doc_key, title or f"RFC {num}", url, "rfc", sections)
            print(f"rfc{num}: indexed {len(sections)} sections — {title}")
            time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rfc", type=int, nargs="*", help="Specific RFC numbers to ingest")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds to wait between requests")
    args = parser.parse_args()
    numbers = args.rfc if args.rfc else DEFAULT_RFCS
    ingest(numbers, delay=args.delay)


if __name__ == "__main__":
    main()
