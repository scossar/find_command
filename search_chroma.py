"""Search the persisted tmux embeddings by semantic similarity."""

import argparse
from pathlib import Path
from typing import cast

import chromadb
from chromadb.api.types import Embeddable, EmbeddingFunction
from chromadb.errors import ChromaError
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction


def search(
    chroma_path: Path,
    query: str,
    collection_name: str = "tmux-key-bindings",
    results: int = 5,
) -> list[tuple[str, str, float]]:
    """Return (key, description, distance) tuples, closest first."""
    if not query.strip():
        raise ValueError("Enter a nonempty query.")
    if results < 1:
        raise ValueError("The number of results must be positive.")
    # PersistentClient otherwise creates a database when the path is wrong.
    if not (chroma_path / "chroma.sqlite3").is_file():
        raise ValueError("Chroma database not found. Run create_embeddings.py first.")

    embedding_function = DefaultEmbeddingFunction()
    client = chromadb.PersistentClient(path=str(chroma_path))
    # As in create_embeddings.py, the cast bridges Chroma's text-or-image
    # parameter type with the default model's text-only input type.
    collection = client.get_collection(
        name=collection_name,
        embedding_function=cast(EmbeddingFunction[Embeddable], embedding_function),
    )
    count = collection.count()
    if count == 0:
        return []

    # Embed the query with the same model used for the stored descriptions.
    # This is natural-language text, not SQL LIKE or FTS5 query syntax.
    query_embeddings = embedding_function([query])
    matches = collection.query(
        query_embeddings=query_embeddings,
        n_results=min(results, count),
        include=["documents", "metadatas", "distances"],
    )

    # Chroma returns one list of matches per query; we submitted just one.
    documents = matches["documents"]
    metadatas = matches["metadatas"]
    distances = matches["distances"]
    if documents is None or metadatas is None or distances is None:
        raise ValueError("Chroma did not return the requested result fields.")
    return [
        (str(metadata["key"]), document, distance)
        for metadata, document, distance in zip(
            metadatas[0], documents[0], distances[0], strict=True
        )
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Natural-language description to search for")
    parser.add_argument("--chroma", type=Path, default=Path("data/chroma"))
    parser.add_argument("--collection", default="tmux-key-bindings")
    parser.add_argument("--results", type=int, default=5, help="Maximum results (default: 5)")
    args = parser.parse_args()
    try:
        rows = search(args.chroma, args.query, args.collection, args.results)
    except (ChromaError, ValueError) as error:
        parser.exit(1, f"Search failed: {error}\n")
    if not rows:
        print("No results found.")
        return
    print("Distance\tKey\tDescription")
    for key, description, distance in rows:
        print(f"{distance:.6f}\t{key}\t{description}")


if __name__ == "__main__":
    main()
