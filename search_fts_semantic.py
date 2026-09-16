"""Select candidates with FTS5, then rank them by semantic similarity."""

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import cast

import chromadb
from chromadb.api.types import Embeddable, EmbeddingFunction
from chromadb.errors import ChromaError
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction


def search(
    database: Path,
    chroma_path: Path,
    fts_query: str,
    semantic_query: str,
    collection_name: str = "tmux-key-bindings",
    results: int = 5,
) -> list[tuple[str, str, float]]:
    """Return (key, description, distance) for the closest FTS5 candidates."""
    if not semantic_query.strip():
        raise ValueError("Enter a nonempty semantic query.")
    if results < 1:
        raise ValueError("The number of results must be positive.")

    with closing(
        sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        candidates = connection.execute(
            """
            SELECT key FROM main.key_bindings_fts
            WHERE key_bindings_fts MATCH ?
            ORDER BY rowid
            """,
            (fts_query,),
        ).fetchall()

    # An empty candidate set means no results, not an unrestricted vector search.
    if not candidates:
        return []
    if not (chroma_path / "chroma.sqlite3").is_file():
        raise ValueError("Chroma database not found. Run create_embeddings.py first.")

    embedding_function = DefaultEmbeddingFunction()
    client = chromadb.PersistentClient(path=str(chroma_path))
    # Chroma's parameter allows text or images; this collection uses text only.
    collection = client.get_collection(
        name=collection_name,
        embedding_function=cast(EmbeddingFunction[Embeddable], embedding_function),
    )
    # Use the same case-sensitive IDs as create_embeddings.py.
    candidate_ids = [f"tmux:{key}" for (key,) in candidates]
    present = collection.get(ids=candidate_ids, include=[])["ids"]
    if set(present) != set(candidate_ids):
        raise ValueError(
            "Some FTS5 candidates are missing from Chroma. "
            "Refresh the matching indexes with create_fts.py and create_embeddings.py."
        )

    # All FTS matches are eligible: no BM25 cutoff or score combination here.
    # Restrict Chroma BEFORE retrieval, rather than filtering its global top hits.
    # The result limit applies only to the final semantic ranking.
    matches = collection.query(
        ids=candidate_ids,
        query_embeddings=embedding_function([semantic_query]),
        n_results=min(results, len(candidate_ids)),
        include=["documents", "metadatas", "distances"],
    )
    documents = matches["documents"]
    metadatas = matches["metadatas"]
    distances = matches["distances"]
    if documents is None or metadatas is None or distances is None:
        raise ValueError("Chroma did not return the requested result fields.")
    # One query produces one inner list of matches, ordered by distance.
    return [
        (str(metadata["key"]), document, distance)
        for metadata, document, distance in zip(
            metadatas[0], documents[0], distances[0], strict=True
        )
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fts_query", help="FTS5 expression selecting eligible descriptions")
    parser.add_argument("semantic_query", help="Natural-language query for ranking")
    parser.add_argument(
        "--database", type=Path, default=Path("tmux_key_bindings.sqlite3")
    )
    parser.add_argument("--chroma", type=Path, default=Path("data/chroma"))
    parser.add_argument("--collection", default="tmux-key-bindings")
    parser.add_argument("--results", type=int, default=5, help="Maximum results (default: 5)")
    args = parser.parse_args()
    try:
        rows = search(
            args.database, args.chroma, args.fts_query, args.semantic_query,
            args.collection, args.results,
        )
    except (sqlite3.Error, ChromaError, ValueError) as error:
        parser.exit(1, f"Search failed: {error}\n")
    if not rows:
        print("No FTS5 candidates found.")
        return
    print("Distance\tKey\tDescription")
    for key, description, distance in rows:
        print(f"{distance:.6f}\t{key}\t{description}")


if __name__ == "__main__":
    main()
