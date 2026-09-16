"""Embed tmux descriptions and save them in a persistent Chroma collection."""

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
    collection_name: str = "tmux-key-bindings",
) -> int:
    """Generate and upsert embeddings for the descriptions stored in SQLite."""
    with closing(
        sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("""
            SELECT id, key, description, prefix, tmux_version, source
            FROM key_bindings
            ORDER BY id
        """).fetchall()

    if not rows:
        return 0

    # Chroma's default model is all-MiniLM-L6-v2, running locally via ONNX.
    # The model files are downloaded and cached on the first use if needed.
    embedding_function = DefaultEmbeddingFunction()
    client = chromadb.PersistentClient(path=str(chroma_path))
    # Chroma types this parameter as accepting documents OR images, but its
    # default embedding function accepts only documents. This collection is
    # text-only, so cast at the API boundary to bridge that typing mismatch.
    # cast does not change the function or add image support at runtime.
    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=cast(EmbeddingFunction[Embeddable], embedding_function),
        metadata={"embedding_model": "all-MiniLM-L6-v2"},
    )

    # Batching limits how many descriptions are embedded and written at once.
    for start in range(0, len(rows), 128):
        batch = rows[start : start + 128]
        documents = [row["description"] for row in batch]

        # This converts each original description into a numeric vector.
        # Do not stem the text: the model works with the original language.
        embeddings = embedding_function(documents)

        # Store both the vectors and original text. The key is a stable ID
        # within this dataset; metadata connects results back to SQLite.
        # Upsert inserts new IDs and updates existing IDs without duplicates.
        collection.upsert(
            ids=[f"tmux:{row['key']}" for row in batch],
            embeddings=embeddings,
            documents=documents,
            metadatas=[
                {
                    "sqlite_id": row["id"],
                    "key": row["key"],
                    "prefix": row["prefix"],
                    "tmux_version": row["tmux_version"],
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
        default=Path("tmux_key_bindings.sqlite3"),
        help="Populated SQLite source (default: tmux_key_bindings.sqlite3)",
    )
    parser.add_argument(
        "--chroma",
        type=Path,
        default=Path("data/chroma"),
        help="Persistent Chroma directory (default: data/chroma)",
    )
    parser.add_argument(
        "--collection",
        default="tmux-key-bindings",
        help="Chroma collection name (default: tmux-key-bindings)",
    )
    args = parser.parse_args()
    count = create_embeddings(args.database, args.chroma, args.collection)
    print(f"Stored {count} descriptions and embeddings in {args.chroma} ({args.collection}).")


if __name__ == "__main__":
    main()
