"""Search with OR matching and report terms absent from the FTS5 vocabulary."""

import argparse
import re
import sqlite3
from contextlib import closing
from pathlib import Path


def normalize_terms(terms: list[str]) -> list[str]:
    """Use SQLite's own tokenizer to produce one indexed token per input term."""
    # fts5vocab contains normalized stems, not original spellings. Applying the
    # same tokenizer prevents 'selected' or 'WINDOW' being falsely called missing.
    # A separate in-memory database leaves the caller's connection untouched.
    with closing(sqlite3.connect(":memory:")) as scratch:
        scratch.execute("""
            CREATE VIRTUAL TABLE query_terms USING fts5(
                text, tokenize = 'porter unicode61'
            )
        """)
        scratch.execute("""
            CREATE VIRTUAL TABLE query_vocab USING fts5vocab(query_terms, instance)
        """)
        scratch.executemany(
            "INSERT INTO query_terms(rowid, text) VALUES (?, ?)",
            enumerate(terms, start=1),
        )
        tokens: dict[int, list[str]] = {}
        for doc, term in scratch.execute("SELECT doc, term FROM query_vocab"):
            tokens.setdefault(doc, []).append(term)
    if any(len(tokens.get(i, [])) != 1 for i in range(1, len(terms) + 1)):
        raise ValueError("Each term must tokenize to exactly one word.")
    return [tokens[i][0] for i in range(1, len(terms) + 1)]


def search(
    connection: sqlite3.Connection, terms: list[str]
) -> tuple[list[tuple[str, str, float]], set[str]]:
    """Return BM25-ranked results and original terms absent from the index."""
    if not terms:
        return [], set()
    normalized = normalize_terms(terms)
    # Quote literal input terms, escaping embedded quotes for FTS5 syntax.
    query = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
    results = connection.execute(
        """
        SELECT key, description, bm25(key_bindings_fts) AS score
        FROM main.key_bindings_fts
        WHERE key_bindings_fts MATCH ?
        ORDER BY score ASC, rowid ASC
        """,
        (query,),
    ).fetchall()
    placeholders = ", ".join("?" for _ in normalized)
    found = {
        row[0]
        for row in connection.execute(
            f"SELECT term FROM main.key_bindings_vocab WHERE term IN ({placeholders})",
            normalized,
        )
    }
    # Return original spellings so callers can explain the user's missing words.
    missing = {
        original for original, token in zip(terms, normalized, strict=True)
        if token not in found
    }
    return results, missing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Words to OR together (not FTS5 query syntax)")
    parser.add_argument(
        "--database", type=Path, default=Path("tmux_key_bindings.sqlite3")
    )
    args = parser.parse_args()
    terms = re.findall(r"[^\W_]+", args.query, flags=re.UNICODE)
    if not terms:
        parser.error("Enter at least one word to search for.")
    try:
        with closing(
            sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True)
        ) as connection:
            rows, missing = search(connection, terms)
    except (sqlite3.Error, ValueError) as error:
        parser.exit(1, f"Search failed: {error}\n")
    print(f"Missing terms: {', '.join(sorted(missing)) if missing else '(none)'}")
    if not rows:
        print("No matches found.")
        return
    print("BM25 score\tKey\tDescription")
    for key, description, score in rows:
        print(f"{score:.9g}\t{key}\t{description}")


if __name__ == "__main__":
    main()
