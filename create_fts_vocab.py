"""Create a persistent vocabulary table for the existing FTS5 index."""

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def create_fts_vocab(database: Path) -> int:
    """Create the vocabulary view if needed and return its term count."""
    with closing(
        sqlite3.connect(database.resolve().as_uri() + "?mode=rw", uri=True)
    ) as connection:
        with connection:
            connection.execute("BEGIN")
            connection.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS main.key_bindings_vocab
                USING fts5vocab(key_bindings_fts, row)
            """)
            # Reading also checks that the underlying FTS5 table exists.
            count = connection.execute(
                "SELECT COUNT(*) FROM main.key_bindings_vocab"
            ).fetchone()[0]
    # fts5vocab reads the index directly: no copying or separate refresh needed.
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "database", nargs="?", type=Path,
        default=Path("tmux_key_bindings.sqlite3"),
        help="Existing SQLite database (default: tmux_key_bindings.sqlite3)",
    )
    args = parser.parse_args()
    try:
        count = create_fts_vocab(args.database)
    except sqlite3.Error as error:
        parser.exit(1, f"Vocabulary setup failed: {error}\nRun create_fts.py first.\n")
    print(f"key_bindings_vocab exposes {count} indexed terms in {args.database}.")


if __name__ == "__main__":
    main()
