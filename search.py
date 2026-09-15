"""Search tmux key binding descriptions using SQL LIKE."""

import argparse
from contextlib import closing
from pathlib import Path
import sqlite3


def search(database: Path, query: str) -> list[tuple[str, str]]:
    """Return keys and descriptions containing the given LIKE pattern."""
    with closing(
        sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        pattern = f"%{query}%"
        rows = connection.execute(
            """
            SELECT key, description
            FROM key_bindings
            WHERE description LIKE ?
            """,
            (pattern,),
        ).fetchall()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Text to match in descriptions")
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
        parser.exit(1, f"Search failed: {error}. Populate the database first with populate.py.\n")
    if not rows:
        print("No matches found.")
    for key, description in rows:
        print(f"{key}\t{description}")


if __name__ == "__main__":
    main()
