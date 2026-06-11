#!/usr/bin/env python3
"""Scan a frontier research watchlist and save ranked hits to the research inbox."""

from __future__ import annotations

import argparse
import datetime as dt
import html.parser
import json
import sqlite3
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from research_common import DEFAULT_ROOT, USER_AGENT, connect, read_json, read_web, sha256_text, slug, utc_now, write_json
from praxis.paths import kg_dir, research_dir, watchlists_dir


ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
S2_BULK_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
ATOM = {"a": "http://www.w3.org/2005/Atom"}


@dataclass
class Hit:
    source_type: str
    title: str
    url: str
    canonical_ref: str = ""
    published_at: str = ""
    updated_at: str = ""
    authors: str = ""
    abstract: str = ""
    venue: str = ""
    categories: str = ""
    score: float = 0.0
    rank_reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def id_basis(self) -> str:
        return self.canonical_ref or self.url or self.title


class LinkExtractor(html.parser.HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self._href = urllib.parse.urljoin(self.base_url, href)
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            text = " ".join(part.strip() for part in self._text if part.strip())
            self.links.append((self._href, text))
            self._href = None
            self._text = []


def get_text(element: ET.Element, path: str) -> str:
    found = element.find(path, ATOM)
    return " ".join((found.text or "").split()) if found is not None else ""


def arxiv_search(query: str, max_results: int) -> list[Hit]:
    params = urllib.parse.urlencode(
        {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    url = f"{ARXIV_ENDPOINT}?{params}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())

    hits: list[Hit] = []
    for entry in root.findall("a:entry", ATOM):
        arxiv_url = get_text(entry, "a:id")
        arxiv_id = arxiv_url.rsplit("/", 1)[-1]
        title = get_text(entry, "a:title")
        authors = ", ".join(get_text(author, "a:name") for author in entry.findall("a:author", ATOM))
        categories = ", ".join(cat.attrib.get("term", "") for cat in entry.findall("a:category", ATOM))
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        hits.append(
            Hit(
                source_type="arxiv",
                title=title,
                url=arxiv_url,
                canonical_ref=arxiv_id,
                published_at=get_text(entry, "a:published")[:10],
                updated_at=get_text(entry, "a:updated")[:10],
                authors=authors,
                abstract=get_text(entry, "a:summary"),
                categories=categories,
                metadata={"query": query, "pdf_url": pdf_url},
            )
        )
    return hits


def semantic_scholar_search(query: str, max_results: int, year: str | None) -> list[Hit]:
    params = {
        "query": query,
        "fields": "title,url,abstract,authors,year,publicationDate,citationCount,venue,openAccessPdf,externalIds",
        "limit": str(max_results),
    }
    if year:
        params["year"] = year
    url = f"{S2_BULK_ENDPOINT}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))

    hits: list[Hit] = []
    for item in payload.get("data", []) or []:
        authors = ", ".join(author.get("name", "") for author in item.get("authors", [])[:8])
        external = item.get("externalIds") or {}
        arxiv_id = external.get("ArXiv")
        paper_id = item.get("paperId", "")
        canonical = f"arxiv:{arxiv_id}" if arxiv_id else f"s2:{paper_id}"
        paper_url = item.get("url") or (f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else "")
        hits.append(
            Hit(
                source_type="semantic_scholar",
                title=item.get("title") or "",
                url=paper_url,
                canonical_ref=canonical,
                published_at=item.get("publicationDate") or str(item.get("year") or ""),
                authors=authors,
                abstract=item.get("abstract") or "",
                venue=item.get("venue") or "",
                metadata={
                    "query": query,
                    "paper_id": paper_id,
                    "citation_count": item.get("citationCount"),
                    "open_access_pdf": item.get("openAccessPdf"),
                    "external_ids": external,
                },
            )
        )
    return hits


def blog_scan(url: str, max_results: int) -> list[Hit]:
    raw_text, metadata = read_web(url)
    # Re-fetch raw HTML for links; read_web intentionally strips HTML for captures.
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw_html = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    parser = LinkExtractor(url)
    parser.feed(raw_html)

    hits: list[Hit] = []
    seen: set[str] = set()
    for href, text in parser.links:
        if len(hits) >= max_results:
            break
        if href in seen:
            continue
        seen.add(href)
        lowered = f"{href} {text}".lower()
        if not text or len(text) < 12:
            continue
        if any(skip in lowered for skip in ("privacy", "terms", "login", "signup", "cookie", "subscribe")):
            continue
        hits.append(
            Hit(
                source_type="blog",
                title=text[:180],
                url=href,
                canonical_ref=href,
                abstract=f"Discovered from {url}.",
                metadata={"source_index": url, "source_metadata": metadata, "index_excerpt_hash": sha256_text(raw_text)[:12]},
            )
        )
    return hits


def relevance_score(hit: Hit, ranking: dict[str, Any]) -> Hit:
    haystack = " ".join([hit.title, hit.abstract, hit.venue, hit.categories]).lower()
    score = 0.0
    reasons: list[str] = []

    for term in ranking.get("boost_terms", []):
        if term.lower() in haystack:
            score += 3.0
            reasons.append(f"boost:{term}")

    for term in ranking.get("must_include_any", []):
        if term.lower() in haystack:
            score += 1.0
            reasons.append(f"match:{term}")

    for venue in ranking.get("known_venues", []):
        if venue.lower() in haystack:
            score += 2.0
            reasons.append(f"venue:{venue}")

    if hit.source_type == "semantic_scholar":
        citations = hit.metadata.get("citation_count")
        if isinstance(citations, int):
            if citations >= 100:
                score += 3
                reasons.append("citations>=100")
            elif citations >= 20:
                score += 1.5
                reasons.append("citations>=20")

    if hit.published_at:
        try:
            published = dt.date.fromisoformat(hit.published_at[:10])
            age_days = (dt.date.today() - published).days
            if age_days <= 90:
                score += 2
                reasons.append("recent<=90d")
            elif age_days <= 365:
                score += 1
                reasons.append("recent<=1y")
        except ValueError:
            pass

    if hit.source_type == "arxiv":
        score += 1
        reasons.append("primary:arxiv")
    elif hit.source_type == "semantic_scholar":
        score += 0.75
        reasons.append("scholarly-index")
    elif hit.source_type == "blog":
        score += 0.25
        reasons.append("engineering-blog")

    hit.score = score
    hit.rank_reasons = reasons
    return hit


def passes_filter(hit: Hit, ranking: dict[str, Any], min_score: float) -> bool:
    haystack = " ".join([hit.title, hit.abstract, hit.venue, hit.categories]).lower()
    must = ranking.get("must_include_any", [])
    if must and not any(term.lower() in haystack for term in must):
        return False
    return hit.score >= min_score


def dedupe_hits(hits: list[Hit]) -> list[Hit]:
    deduped: dict[str, Hit] = {}
    for hit in hits:
        key = (hit.canonical_ref or hit.url or hit.title).lower()
        if key not in deduped or hit.score > deduped[key].score:
            deduped[key] = hit
    return sorted(deduped.values(), key=lambda h: (-h.score, h.published_at, h.title))


def make_hit_id(run_id: str, index: int, hit: Hit) -> str:
    return f"hit:{slug(run_id)}:{index:03d}:{sha256_text(hit.id_basis)[:10]}"


def scan_source(source: dict[str, Any], *, dry_run: bool) -> tuple[list[Hit], int]:
    source_type = source["type"]
    max_results = int(source.get("max_results", 8))
    query_count = 0
    hits: list[Hit] = []

    if source_type == "arxiv":
        for idx, query in enumerate(source.get("queries", [])):
            query_count += 1
            if dry_run:
                continue
            hits.extend(arxiv_search(query, max_results))
            if idx < len(source.get("queries", [])) - 1:
                time.sleep(float(source.get("delay_seconds", 3)))
    elif source_type == "semantic_scholar":
        for query in source.get("queries", []):
            query_count += 1
            if dry_run:
                continue
            hits.extend(semantic_scholar_search(query, max_results, source.get("year")))
    elif source_type == "blog":
        for url in source.get("urls", []):
            query_count += 1
            if dry_run:
                continue
            try:
                hits.extend(blog_scan(url, max_results))
            except Exception as exc:
                hits.append(
                    Hit(
                        source_type="blog_error",
                        title=f"Scan failed: {url}",
                        url=url,
                        abstract=str(exc),
                        score=-1,
                        rank_reasons=["error"],
                    )
                )
    else:
        raise ValueError(f"Unsupported watchlist source type: {source_type}")

    return hits, query_count


def hit_to_dict(hit: Hit, hit_id: str = "") -> dict[str, Any]:
    return {
        "id": hit_id,
        "source_type": hit.source_type,
        "title": hit.title,
        "url": hit.url,
        "canonical_ref": hit.canonical_ref,
        "published_at": hit.published_at,
        "updated_at": hit.updated_at,
        "authors": hit.authors,
        "abstract": hit.abstract,
        "venue": hit.venue,
        "categories": hit.categories,
        "score": hit.score,
        "rank_reasons": hit.rank_reasons,
        "metadata": hit.metadata,
    }


def save_run(connection: sqlite3.Connection, run_id: str, watchlist_name: str, query_count: int, hits: list[Hit], report_path: Path, metadata: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO watchlist_runs(id, watchlist_name, completed_at, status, query_count, hit_count, report_path, metadata_json)
        VALUES (?, ?, ?, 'completed', ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          completed_at=excluded.completed_at,
          status=excluded.status,
          query_count=excluded.query_count,
          hit_count=excluded.hit_count,
          report_path=excluded.report_path,
          metadata_json=excluded.metadata_json
        """,
        (run_id, watchlist_name, utc_now(), query_count, len(hits), str(report_path), json.dumps(metadata, sort_keys=True)),
    )

    for idx, hit in enumerate(hits, 1):
        hit_id = make_hit_id(run_id, idx, hit)
        connection.execute(
            """
            INSERT INTO research_hits(
              id, run_id, watchlist_name, source_type, title, url, canonical_ref,
              published_at, updated_at, authors, abstract, venue, categories,
              score, rank_reasons, status, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                hit_id,
                run_id,
                watchlist_name,
                hit.source_type,
                hit.title,
                hit.url,
                hit.canonical_ref,
                hit.published_at,
                hit.updated_at,
                hit.authors,
                hit.abstract,
                hit.venue,
                hit.categories,
                hit.score,
                ", ".join(hit.rank_reasons),
                json.dumps(hit.metadata, sort_keys=True),
            ),
        )


def resolve_watchlist(root: Path, value: str) -> Path:
    path = Path(value)
    if path.exists():
        return path
    candidate = watchlists_dir(root) / f"{value}.json"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Watchlist not found: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("watchlist", help="Watchlist name or JSON path")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Praxis root")
    parser.add_argument("--limit", type=int, default=25, help="Maximum ranked hits to save")
    parser.add_argument("--min-score", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true", help="Validate config without network calls")
    parser.add_argument("--include-low-score", action="store_true", help="Do not filter by score/must-match")
    args = parser.parse_args()

    root = Path(args.root)
    watchlist_path = resolve_watchlist(root, args.watchlist)
    watchlist = read_json(watchlist_path)
    watchlist_name = watchlist["name"]
    run_id = f"run:{watchlist_name}:{dt.datetime.now(dt.UTC).strftime('%Y%m%dT%H%M%SZ')}"
    report_path = research_dir(root) / "inbox" / f"{slug(run_id)}.json"

    all_hits: list[Hit] = []
    query_count = 0
    for source in watchlist.get("sources", []):
        source_hits, source_query_count = scan_source(source, dry_run=args.dry_run)
        query_count += source_query_count
        all_hits.extend(source_hits)

    ranking = watchlist.get("ranking", {})
    scored = [relevance_score(hit, ranking) for hit in all_hits]
    if not args.include_low_score:
        scored = [hit for hit in scored if passes_filter(hit, ranking, args.min_score)]
    ranked = dedupe_hits(scored)[: args.limit]

    report = {
        "id": run_id,
        "watchlist": watchlist_name,
        "watchlist_path": str(watchlist_path),
        "created_at": utc_now(),
        "dry_run": args.dry_run,
        "query_count": query_count,
        "hit_count": len(ranked),
        "hits": [hit_to_dict(hit, make_hit_id(run_id, idx, hit)) for idx, hit in enumerate(ranked, 1)],
    }
    write_json(report_path, report)

    if not args.dry_run:
        with connect(kg_dir(root) / "skill_graph.sqlite") as connection:
            save_run(
                connection,
                run_id,
                watchlist_name,
                query_count,
                ranked,
                report_path,
                {"watchlist_path": str(watchlist_path)},
            )

    print(f"Watchlist: {watchlist_name}")
    print(f"Queries: {query_count}")
    print(f"Hits: {len(ranked)}")
    print(f"Report: {report_path}")
    if ranked:
        print("\nTop hits:")
        for idx, hit in enumerate(ranked[:10], 1):
            print(f"{idx}. [{hit.score:.1f}] {hit.title}")
            print(f"   id: {make_hit_id(run_id, idx, hit)}")
            print(f"   {hit.url or hit.canonical_ref}")
            if hit.rank_reasons:
                print(f"   reasons: {', '.join(hit.rank_reasons[:6])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
