"""Embed augmented tmux descriptions and save them in a persistent Chroma collection."""

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import cast

import chromadb
from chromadb.api.types import Embeddable, EmbeddingFunction
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction


def create_embeddings(
    database: Path,
    chroma_path: Path,
    collection_name: str = "tmux-key-bindings-augmented",
) -> int:
    """Generate and upsert embeddings for the augmented descriptions stored in SQLite.jk"""
    with closing(
        sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("""
            SELECT id, key, description, augmented_description, prefix, tmux_version, source
            FROM key_bindings_augmented
            ORDER BY id
        """).fetchall()

    if not rows:
        return 0

    embedding_function = DefaultEmbeddingFunction()
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=cast(EmbeddingFunction[Embeddable], embedding_function),
        metadata={"embedding_model": "all-MiniLM-L6-v2"},
    )

    # Process in batches
    for start in range(0, len(rows), 128):
        batch = rows[start : start + 128]
        # descriptions = [row["description"] for row in batch]
        augmented_descriptions = [row["augmented_description"] for row in batch]

        embeddings = embedding_function(augmented_descriptions)

        collection.upsert(
            ids=[f"tmux:{row['key']}" for row in batch],
            embeddings=embeddings,
            documents=augmented_descriptions,
            metadatas=[
                {
                    "sqlite_id": row["id"],
                    "key": row["key"],
                    "prefix": row["prefix"],
                    "source": row["source"],
                }
                for row in batch
            ],
        )
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("tmux_key_bindings_augmented.sqlite3"),
        help="Populated SQLite source (default: tmux_key_bindings_augmented.sqlite3)",
    )
    parser.add_argument(
        "--chroma",
        type=Path,
        default=Path("data/chroma_augmented"),
        help="Persistent Chroma directory (default: data/chroma_augmented)",
    )
    parser.add_argument(
        "--collection",
        default="tmux-key-bindings-augmented",
        help="Chroma collection name (default: tmux-key-bindings-augmented)",
    )
    args = parser.parse_args()
    count = create_embeddings(args.database, args.chroma, args.collection)
    print(
        f"Stored {count} augmented descriptions and embeddings in {args.chroma} ({args.collection})."
    )


if __name__ == "__main__":
    main()
