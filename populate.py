"""Populate SQLite with the default key bindings from the tmux manual."""

import argparse
import json
from pathlib import Path
import sqlite3


DATA_PATH = Path(__file__).parent / "data" / "tmux_key_bindings.json"


def populate(database: Path) -> int:
    """Insert or update the bundled bindings in a single transaction."""
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    connection = sqlite3.connect(database)
    try:
        with connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS key_bindings (
                    id INTEGER PRIMARY KEY,
                    key TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL,
                    prefix TEXT NOT NULL,
                    tmux_version TEXT NOT NULL,
                    source TEXT NOT NULL
                )
            """)
            connection.executemany(
                """
                INSERT INTO key_bindings
                    (key, description, prefix, tmux_version, source)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    description = excluded.description,
                    prefix = excluded.prefix,
                    tmux_version = excluded.tmux_version,
                    source = excluded.source
                """,
                [
                    (
                        binding["key"],
                        binding["description"],
                        data["prefix"],
                        data["tmux_version"],
                        data["source"],
                    )
                    for binding in data["bindings"]
                ],
            )
    finally:
        connection.close()
    return len(data["bindings"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "database",
        nargs="?",
        type=Path,
        default=Path("tmux_key_bindings.sqlite3"),
        help="SQLite file to populate (default: tmux_key_bindings.sqlite3)",
    )
    args = parser.parse_args()
    count = populate(args.database)
    print(f"Loaded {count} key binding entries into {args.database}.")


if __name__ == "__main__":
    main()
