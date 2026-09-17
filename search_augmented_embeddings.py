"""Search the augmented embeddings by semantic similarity"""

import argparse
from pathlib import Path
from typing import cast

import chromadb
from chromadb.api.types import Embeddable, EmbeddingFunction
from chromadb.errors import ChromaError
from chromadb.utils import embedding_functions
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction


def search(
    chroma_path: Path,
    query: str,
    collection_name: str = "tmux-key-bindings-augmented",
    results: int = 5,
) -> list[tuple[str, str, float]]:
    """Return (key, augmented description, distance) tuples, closes first."""
    if not query.strip():
        raise ValueError("Enter a nonempty query")
    if results < 1:
        raise ValueError("The number of results must be positive.")
    if not (chroma_path / "chroma.sqlite3").is_file():
        raise ValueError(
            "Chroma database not found. Run create_augmented_embeddings.py first."
        )

    embedding_function = DefaultEmbeddingFunction()
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_collection(
        name=collection_name,
        embedding_function=cast(EmbeddingFunction[Embeddable], embedding_function),
    )

    count = collection.count()
    if count == 0:
        return []

    query_embeddings = embedding_function([query])
    matches = collection.query(
        query_embeddings=query_embeddings,
        n_results=min(results, count),
        include=["documents", "metadatas", "distances"],
    )

    documents = matches["documents"]
    metadatas = matches["metadatas"]
    distances = matches["distances"]
    if documents is None or metadatas is None or distances is None:
        raise ValueError("Chroma did not return the requested fields.")
    return [
        (str(metadata["key"]), document, distance)
        for metadata, document, distance in zip(
            metadatas[0], documents[0], distances[0], strict=True
        )
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Natural language description to search for")
    parser.add_argument("--chroma", type=Path, default=Path("data/chroma_augmented"))
    parser.add_argument("--collection", default="tmux-key-bindings-augmented")
    parser.add_argument(
        "--results", type=int, default=5, help="Maximum results (default: 5)"
    )
    args = parser.parse_args()
    try:
        rows = search(args.chroma, args.query, args.collection, args.results)
    except (ChromaError, ValueError) as error:
        parser.exit(1, f"Search failed: {error}\n")
    if not rows:
        print("No results found")
        return
    print("Distance\tKey\tDescription")
    for key, description, distance in rows:
        print(f"{distance:.6f}\t{key}\t{description}")


if __name__ == "__main__":
    main()
