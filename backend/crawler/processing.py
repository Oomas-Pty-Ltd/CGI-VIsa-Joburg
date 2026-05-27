"""Post-fetch content processing for crawled pages.

Runs after a page is fetched + parsed and produces the derived artifacts the
spec calls for:

  - **chunking**       — split the extracted text into bounded, overlapping
                         chunks suitable for retrieval / embedding.
  - **summarization**  — extractive: rank sentences by keyword-frequency
                         overlap and keep the top few in original order.
  - **keyword extraction** — frequency-ranked terms (the crawler's parser
                         already does a pass; we recompute here so processing
                         is self-contained and independent of the parser).
  - **dummy embeddings** — a deterministic hash-bucketed bag-of-words vector,
                         L2-normalised. Reproducible and dependency-free; a
                         real deployment swaps `embed()` for a model call.

Everything is deterministic (no external services, no randomness) so the same
input always yields the same artifacts — important for idempotent re-runs and
testable verification.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List

# Chunking: ~700-char chunks with 100-char overlap, split on sentence
# boundaries where possible so chunks don't cut mid-sentence.
_CHUNK_SIZE = 700
_CHUNK_OVERLAP = 100
_MAX_CHUNKS = 50

EMBEDDING_DIM = 64
_SUMMARY_SENTENCES = 3
_KEYWORD_LIMIT = 12

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[a-z0-9]{3,}")

# Common words we never want as keywords / never weight in summaries.
_STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "her", "was",
    "one", "our", "out", "his", "has", "him", "how", "its", "may", "new", "now",
    "see", "two", "who", "did", "yes", "this", "that", "with", "from", "your",
    "have", "will", "they", "what", "when", "which", "their", "there", "would",
    "about", "these", "other", "page", "home", "more", "than", "into", "such",
    "been", "also", "were", "here",
}


@dataclass
class ProcessingResult:
    chunks: List[str] = field(default_factory=list)
    chunk_count: int = 0
    summary: str = ""
    keywords: List[str] = field(default_factory=list)
    embedding: List[float] = field(default_factory=list)
    embedding_dim: int = EMBEDDING_DIM
    log: List[str] = field(default_factory=list)


def _tokens(text: str) -> List[str]:
    return [w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS]


def chunk_text(text: str) -> List[str]:
    """Bounded, slightly-overlapping chunks, preferring sentence boundaries."""
    text = (text or "").strip()
    if not text:
        return []
    sentences = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    if not sentences:
        sentences = [text]

    chunks: List[str] = []
    current = ""
    for sent in sentences:
        if current and len(current) + 1 + len(sent) > _CHUNK_SIZE:
            chunks.append(current)
            # Carry a short overlap tail into the next chunk for context.
            tail = current[-_CHUNK_OVERLAP:]
            current = (tail + " " + sent).strip()
        else:
            current = (current + " " + sent).strip() if current else sent
        if len(chunks) >= _MAX_CHUNKS:
            break
    if current and len(chunks) < _MAX_CHUNKS:
        chunks.append(current)
    return chunks[:_MAX_CHUNKS]


def extract_keywords(text: str, limit: int = _KEYWORD_LIMIT) -> List[str]:
    """Top terms by frequency, stopwords removed. Deterministic ordering:
    frequency desc, then alphabetical for ties."""
    freq: Dict[str, int] = {}
    for tok in _tokens(text):
        freq[tok] = freq.get(tok, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:limit]]


def summarize(text: str, keywords: List[str], max_sentences: int = _SUMMARY_SENTENCES) -> str:
    """Extractive summary: score each sentence by how many top keywords it
    contains (plus a small lead bias), keep the best, restore original order."""
    sentences = [s.strip() for s in _SENT_SPLIT.split(text or "") if s.strip()]
    if not sentences:
        return ""
    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    kw = set(keywords)
    scored = []
    for idx, sent in enumerate(sentences):
        toks = set(_tokens(sent))
        overlap = len(toks & kw)
        lead_bonus = 1.0 if idx == 0 else (0.5 if idx == 1 else 0.0)
        scored.append((overlap + lead_bonus, idx, sent))
    # Pick top-N by score (ties broken by earlier position), then re-sort by
    # original position so the summary reads in order.
    top = sorted(scored, key=lambda t: (-t[0], t[1]))[:max_sentences]
    top.sort(key=lambda t: t[1])
    return " ".join(s for _, _, s in top)


def embed(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    """Deterministic hash-bucketed bag-of-words embedding, L2-normalised.

    Each token is hashed to a bucket and contributes a signed weight; the
    vector is then normalised. Same text → same vector. This is a stand-in
    for a real embedding model (swap this one function out)."""
    vec = [0.0] * dim
    toks = _tokens(text)
    if not toks:
        return vec
    for tok in toks:
        h = hashlib.md5(tok.encode("utf-8")).digest()
        bucket = h[0] % dim
        sign = 1.0 if (h[1] & 1) else -1.0
        vec[bucket] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [round(v / norm, 6) for v in vec]
    return vec


def process_text(text: str, *, title: str = "") -> ProcessingResult:
    """Full pipeline for one page's extracted text."""
    log: List[str] = []
    body = (text or "").strip()
    if not body:
        log.append("no extracted text — processing skipped")
        return ProcessingResult(log=log, embedding=[0.0] * EMBEDDING_DIM)

    # Title gets a small boost in the embedded text so it influences the vector.
    embed_input = f"{title}\n{title}\n{body}" if title else body

    chunks = chunk_text(body)
    log.append(f"chunked into {len(chunks)} chunk(s) (size~{_CHUNK_SIZE}, overlap {_CHUNK_OVERLAP})")

    keywords = extract_keywords(body)
    log.append(f"extracted {len(keywords)} keyword(s)")

    summary = summarize(body, keywords)
    log.append(f"summarised to {len(summary)} chars")

    vector = embed(embed_input)
    log.append(f"embedded into {len(vector)}-dim vector")

    return ProcessingResult(
        chunks=chunks,
        chunk_count=len(chunks),
        summary=summary,
        keywords=keywords,
        embedding=vector,
        embedding_dim=len(vector),
        log=log,
    )
