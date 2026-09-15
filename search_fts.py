"""Demonstrate FTS5 search with English stemming and AND matching."""

import argparse
import re
import sqlite3
from contextlib import closing
from pathlib import Path


def search(database: Path, query: str) -> list[tuple[str, str]]:
    """Match every query word against stemmed description tokens."""
    # Treat input as words, not FTS query syntax. Punctuation separates words.
    words = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
    if not words:
        raise ValueError("Enter at least one word to search for.")

    # Quoting keeps words such as OR and NOT from becoming FTS operators.
    # SQL parameter binding alone does not escape FTS's own query language.
    match_query = " AND ".join(f'"{word}"' for word in words)
    print(match_query)

    with closing(
        sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        # A temporary index keeps this demonstration self-contained. It is
        # rebuilt each run and disappears when the connection closes.
        # unicode61 splits text into tokens; porter stems English word forms
        # in both descriptions and queries (for example, selected -> select).
        connection.execute("""
            CREATE VIRTUAL TABLE temp.key_bindings_fts USING fts5(
                key UNINDEXED,
                description,
                tokenize = 'porter unicode61'
            )
        """)
        connection.execute("""
            INSERT INTO temp.key_bindings_fts (rowid, key, description)
            SELECT id, key, description FROM main.key_bindings
        """)
        return connection.execute(
            """
            SELECT key, description
            FROM temp.key_bindings_fts
            WHERE key_bindings_fts MATCH ?
            ORDER BY rowid
            """,
            (match_query,),
        ).fetchall()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Words that must all match in a description")
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("tmux_key_bindings.sqlite3"),
        help="SQLite file to search (default: tmux_key_bindings.sqlite3)",
    )
    args = parser.parse_args()
    try:
        rows = search(args.database, args.query)
    except (sqlite3.Error, ValueError) as error:
        parser.exit(1, f"Search failed: {error}\n")
    if not rows:
        print("No matches found.")
    for key, description in rows:
        print(f"{key}\t{description}")


if __name__ == "__main__":
    main()
