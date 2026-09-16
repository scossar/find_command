"""Combine FTS5 term substitutions and semantic rankings with RRF."""

import argparse
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from chromadb.errors import ChromaError

from search_bm25 import search as search_bm25
from search_chroma import search as search_chroma

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "with",
}


# Exact whole-word replacements, looked up case-insensitively.
# Values replace the original FTS terms; they do not expand the query with synonyms.
SUBSTITUTIONS = {
    "close": "kill",
    "bigger": "resize",
    "smaller": "resize",
    "2": "two",
    "go": "move",
}


@dataclass
class Result:
    key: str
    description: str
    score: float = 0.0
    fts_rank: int | None = None
    semantic_rank: int | None = None


def fts_query(query: str) -> str:
    """Remove stop words, substitute terms, then OR-join them for FTS5."""
    words = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
    if not words:
        raise ValueError("Enter at least one word to search for.")
    # Match stop words case-insensitively, preserving the remaining words.
    # Filtering affects the FTS query only, not the index or semantic query.
    words = [word for word in words if word.casefold() not in STOP_WORDS]
    # Apply substitutions only here, after stop-word filtering and before
    # FTS5 tokenization/stemming. Unmapped words retain their original spelling.
    words = [SUBSTITUTIONS.get(word.casefold(), word) for word in words]
    # Quote terms so user-supplied words cannot become FTS operators.
    return " OR ".join(f'"{word}"' for word in words)


def fuse(
    lexical: list[tuple[str, str, float]],
    semantic: list[tuple[str, str, float]],
    k: int = 60,
) -> list[Result]:
    """Fuse ranked lists by key; use positions, not the original scores."""
    if k < 0:
        raise ValueError("RRF k must be nonnegative.")
    combined: dict[str, Result] = {}
    for rank, (key, description, _) in enumerate(lexical, start=1):
        result = combined.setdefault(key, Result(key, description))
        result.fts_rank = rank
        result.score += 1 / (k + rank)
    for rank, (key, description, _) in enumerate(semantic, start=1):
        result = combined.setdefault(key, Result(key, description))
        result.semantic_rank = rank
        result.score += 1 / (k + rank)
    # Missing from a list means zero contribution. Higher fused scores win.
    # Case-sensitive key ordering makes exact score ties deterministic.
    return sorted(combined.values(), key=lambda result: (-result.score, result.key))


def search(
    database: Path,
    chroma_path: Path,
    query: str,
    collection_name: str = "tmux-key-bindings",
    results: int = 5,
    candidates: int = 20,
    k: int = 60,
) -> list[Result]:
    """Retrieve independently, fuse their top candidates, then limit output."""
    if results < 1 or candidates < 1:
        raise ValueError("Results and candidates must be positive.")
    if k < 0:
        raise ValueError("RRF k must be nonnegative.")
    lexical_query = fts_query(query)
    # MATCH cannot accept an empty expression. If every word was excluded,
    # skip lexical retrieval and let the semantic list contribute on its own.
    lexical = search_bm25(database, lexical_query)[:candidates] if lexical_query else []
    # The original query goes to the embedding model, without OR rewriting.
    # Semantic retrieval runs even when FTS5 returns no matches.
    semantic = search_chroma(chroma_path, query, collection_name, candidates)
    return fuse(lexical, semantic, k)[:results]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Text to search with both retrieval methods")
    parser.add_argument(
        "--database", type=Path, default=Path("tmux_key_bindings.sqlite3")
    )
    parser.add_argument("--chroma", type=Path, default=Path("data/chroma"))
    parser.add_argument("--collection", default="tmux-key-bindings")
    parser.add_argument(
        "--results", type=int, default=5, help="Final results (default: 5)"
    )
    parser.add_argument(
        "--candidates",
        type=int,
        default=20,
        help="Maximum entries from each ranked list to fuse (default: 20)",
    )
    parser.add_argument("--k", type=int, default=60, help="RRF constant (default: 60)")
    args = parser.parse_args()
    try:
        rows = search(
            args.database,
            args.chroma,
            args.query,
            args.collection,
            args.results,
            args.candidates,
            args.k,
        )
    except (sqlite3.Error, ChromaError, ValueError) as error:
        parser.exit(1, f"Search failed: {error}\n")
    lexical_query = fts_query(args.query)
    print(f"FTS5 query: {lexical_query or '(skipped: all terms are stop words)'}")
    if not rows:
        print("No results found.")
        return
    print("RRF score\tFTS rank\tSemantic rank\tKey\tDescription")
    for row in rows:
        print(
            f"{row.score:.9g}\t{row.fts_rank or '-'}\t"
            f"{row.semantic_rank or '-'}\t{row.key}\t{row.description}"
        )


if __name__ == "__main__":
    main()
