"""HTML → ParsedPage.

Strips boilerplate (nav, footer, script, style), extracts title/language,
auto-derives keywords, classifies into a coarse category from URL path +
content heuristics, and returns absolute outbound links for the BFS step.

Domain-agnostic — the crawler keeps tenant-specific URL/keyword logic in
`scraper_config`, not here.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urljoin, urlparse, urldefrag

from bs4 import BeautifulSoup

# Tags whose contents we drop entirely before text extraction.
_DROP_TAGS = {
    "script", "style", "noscript", "template",
    "nav", "header", "footer", "aside",
    "form", "svg", "iframe",
}

# Conservative English stopwords. Keep short — the goal is keyword extraction
# from page text, not full NLP.
_STOPWORDS = {
    "a","an","and","are","as","at","be","by","for","from","has","have","he",
    "in","is","it","its","of","on","or","that","the","this","to","was","were",
    "will","with","you","your","yours","we","our","ours","they","their","them",
    "i","me","my","mine","not","but","if","do","does","did","so","no","yes",
    "can","could","should","would","may","might","must","also","than","then",
    "there","here","what","when","where","which","who","how","why","all","any",
    "more","most","other","some","such","only","own","same","too","very","just",
    "now","up","down","out","over","under","into","about","after","before",
    "between","through","during","while","because","one","two","three",
}

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9'-]{2,}")
_WS_RE = re.compile(r"\s+")

# URL path segments → coarse category buckets. Generic; specific buckets
# can be added per-tenant later via scraper_config if needed.
_CATEGORY_RULES = [
    ("visa",      ["visa", "evisa"]),
    ("passport",  ["passport"]),
    ("oci",       ["oci"]),
    ("consular",  ["consular", "attestation", "apostille", "notar"]),
    ("fees",      ["fee", "charges", "tariff", "price"]),
    ("contact",   ["contact", "address", "office", "reach"]),
    ("emergency", ["emergency", "urgent", "sos"]),
    ("faq",       ["faq", "frequently"]),
    ("news",      ["news", "press", "announce"]),
]


@dataclass
class ParsedPage:
    title: str
    text: str                      # cleaned, NOT truncated (upsert caps it)
    full_length: int               # original length before any caller cap
    language: str
    keywords: list[str]            # top-N by frequency
    links: list[str]               # absolute http(s) URLs, deduped, defragged
    category: str


def parse(html: str, base_url: str) -> ParsedPage:
    soup = BeautifulSoup(html, "html.parser")

    # Capture language before we strip elements that don't include <html>.
    language = _extract_language(soup)

    # Title: <title> wins, fallback to first <h1>, fallback to "".
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
    title = _WS_RE.sub(" ", title)[:200]

    # Pull links before stripping anchors live in nav/footer too.
    links = _extract_links(soup, base_url)

    # Strip noisy containers, then extract visible text.
    for tag in soup(_DROP_TAGS):
        tag.decompose()

    text = soup.get_text(separator="\n")
    # Collapse runs of whitespace, drop empty lines, strip per-line.
    lines = [_WS_RE.sub(" ", ln).strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    clean = "\n".join(lines)

    keywords = _extract_keywords(clean, limit=15)
    category = _classify(base_url, title, clean)

    return ParsedPage(
        title=title,
        text=clean,
        full_length=len(clean),
        language=language,
        keywords=keywords,
        links=links,
        category=category,
    )


def _extract_language(soup: BeautifulSoup) -> str:
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        return str(html_tag["lang"]).split("-")[0].lower()[:5] or "en"
    return "en"


def _extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Absolute http(s) URLs from <a href>. Deduped, fragment-stripped.

    Domain/pattern filtering is the runner's job; we just normalize.
    """
    seen: set[str] = set()
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        try:
            absolute = urljoin(base_url, href)
            absolute, _ = urldefrag(absolute)
        except Exception:
            continue
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        if not parsed.netloc:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append(absolute)
    return out


def _extract_keywords(text: str, limit: int) -> list[str]:
    """Top-N tokens by frequency after stopword + length filtering.

    Cheap TF — no IDF — but plenty for the keyword-scored retrieval in
    services/knowledge_service.py.
    """
    counts: Counter[str] = Counter()
    for word in _WORD_RE.findall(text.lower()):
        if len(word) < 4:
            continue
        if word in _STOPWORDS:
            continue
        counts[word] += 1
    return [w for w, _ in counts.most_common(limit)]


def _classify(url: str, title: str, text: str) -> str:
    path = urlparse(url).path.lower()
    haystack = f"{path} {title.lower()}"
    for category, needles in _CATEGORY_RULES:
        if any(n in haystack for n in needles):
            return category
    # Fallback: look at first 500 chars of text.
    head = text[:500].lower()
    for category, needles in _CATEGORY_RULES:
        if any(n in head for n in needles):
            return category
    return "general"


def filter_links(
    links: Iterable[str],
    allowed_domains: set[str],
    include_patterns: list[re.Pattern],
    exclude_patterns: list[re.Pattern],
) -> list[str]:
    """Apply per-tenant URL filters. Pure function, called by the runner.

    - Drops URLs whose host isn't in allowed_domains
    - Drops URLs matching any exclude pattern
    - If include_patterns is non-empty, drops URLs matching none of them
    """
    out: list[str] = []
    for url in links:
        host = urlparse(url).netloc
        if allowed_domains and host not in allowed_domains:
            continue
        if any(p.search(url) for p in exclude_patterns):
            continue
        if include_patterns and not any(p.search(url) for p in include_patterns):
            continue
        out.append(url)
    return out
