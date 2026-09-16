"""Search the persistent FTS5 table and rank matches with BM25."""

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def search(database: Path, query: str) -> list[tuple[str, str, float]]:
    """Return (key, description, score) tuples, best matches first."""
    with closing(
        sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        # MATCH chooses the candidates; BM25 ranks only those matches.
        # SQLite negates BM25 scores, so lower (more negative) is better.
        # rowid provides a stable ordering when scores are equal.
        return connection.execute(
            """
            SELECT key, description, bm25(key_bindings_fts) AS score
            FROM main.key_bindings_fts
            WHERE key_bindings_fts MATCH ?
            ORDER BY score ASC, rowid ASC
            """,
            (query,),
        ).fetchall()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="FTS5 query, including any operators or quotes")
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("tmux_key_bindings.sqlite3"),
        help="SQLite file with persistent FTS5 table (default: tmux_key_bindings.sqlite3)",
    )
    args = parser.parse_args()
    try:
        rows = search(args.database, args.query)
    except sqlite3.Error as error:
        parser.exit(1, f"Search failed: {error}\n")
    if not rows:
        print("No matches found.")
        return
    print("BM25 score\tKey\tDescription")
    for key, description, score in rows:
        # General formatting preserves very small scores using scientific notation.
        print(f"{score:.9g}\t{key}\t{description}")


if __name__ == "__main__":
    main()
