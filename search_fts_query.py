"""Search descriptions using an unmodified FTS5 query and English stemming."""

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def search(database: Path, query: str) -> list[tuple[str, str]]:
    """Pass the query directly to MATCH, preserving FTS5 syntax."""
    with closing(
        sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        # As in search_fts.py, this index lasts only for this connection.
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
        # Binding protects the SQL statement while deliberately allowing FTS5
        # to interpret operators, phrases, prefixes, and other query syntax.
        return connection.execute(
            """
            SELECT key, description
            FROM temp.key_bindings_fts
            WHERE key_bindings_fts MATCH ?
            ORDER BY rowid
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
        help="SQLite file to search (default: tmux_key_bindings.sqlite3)",
    )
    args = parser.parse_args()
    try:
        rows = search(args.database, args.query)
    except sqlite3.Error as error:
        parser.exit(1, f"Search failed: {error}\n")
    if not rows:
        print("No matches found.")
    for key, description in rows:
        print(f"{key}\t{description}")


if __name__ == "__main__":
    main()
