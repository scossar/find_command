"""Create and populate a persistent FTS5 table from key_bindings."""

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def create_fts(database: Path) -> int:
    """Create the FTS table if needed and refresh its contents atomically."""
    # mode=rw allows writes but requires an existing database file.
    # ruff: ignore[SIM117]  the nesting is intentional here.
    with closing(
        sqlite3.connect(database.resolve().as_uri() + "?mode=rw", uri=True)
    ) as connection:
        with connection:
            # Explicitly begin so table creation is also part of the transaction.
            # The context manager commits on success or rolls back on failure.
            connection.execute("BEGIN")
            # main stores the table in the database file; temp would make it
            # disappear when this connection closes.
            connection.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS main.key_bindings_fts USING fts5(
                    key UNINDEXED,
                    description,
                    tokenize = 'porter unicode61'
                )
            """)
            # Refresh the separate searchable copy, including removing entries
            # that no longer exist in the source. Repeated runs won't duplicate rows.
            connection.execute("DELETE FROM main.key_bindings_fts")
            connection.execute("""
                INSERT INTO main.key_bindings_fts (rowid, key, description)
                SELECT id, key, description FROM main.key_bindings
            """)
            count = connection.execute(
                "SELECT COUNT(*) FROM main.key_bindings_fts"
            ).fetchone()[0]
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "database",
        nargs="?",
        type=Path,
        default=Path("tmux_key_bindings.sqlite3"),
        help="Existing SQLite file (default: tmux_key_bindings.sqlite3)",
    )
    args = parser.parse_args()
    try:
        count = create_fts(args.database)
    except sqlite3.Error as error:
        parser.exit(1, f"FTS setup failed: {error}\n")
    print(
        f"Loaded {count} entries into persistent key_bindings_fts in {args.database}."
    )


if __name__ == "__main__":
    main()
