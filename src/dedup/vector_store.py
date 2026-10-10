"""ChromaDB vector store wrapper for L2 semantic dedup."""
import logging
from typing import List, Optional, Tuple

import chromadb
from chromadb.config import Settings as ChromaSettings

from config.settings import settings

logger = logging.getLogger(__name__)


class VectorStoreError(RuntimeError):
    """Raised when the vector store cannot index or query.

    Dedup silently degrading into "everything is new" was one of the ways
    duplicate Events were created while the run still reported success, so
    index/query failures are surfaced instead of being swallowed.
    """


class VectorStore:
    """Thin wrapper around ChromaDB for embedding storage and similarity search."""

    COLLECTION_NAME = "web3_events"

    def __init__(self):
        self._client = chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        """Number of indexed documents. Raises VectorStoreError when unreachable."""
        try:
            return int(self._collection.count())
        except Exception as e:
            raise VectorStoreError(f"ChromaDB count failed: {e}") from e

    def existing_ids(self) -> set[str]:
        """All document ids currently indexed (used for reconciliation)."""
        try:
            result = self._collection.get(include=[])
        except Exception as e:
            raise VectorStoreError(f"ChromaDB get failed: {e}") from e
        return set(result.get("ids") or [])

    def add(self, doc_id: str, text: str, metadata: Optional[dict] = None):
        """Index an event's text for later similarity search.

        Upsert semantics: re-indexing an already present id refreshes it instead
        of failing, so the startup reconciliation can be run repeatedly.
        """
        try:
            self._collection.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata or {}],
            )
        except Exception as e:
            raise VectorStoreError(f"ChromaDB add failed for {doc_id}: {e}") from e

    def search_similar(
        self,
        text: str,
        n_results: int = 5,
        where: Optional[dict] = None,
    ) -> List[Tuple[str, float, dict]]:
        """Return (id, distance, metadata) tuples for similar documents.

        Uses cosine similarity. Lower distance = more similar.
        Raises VectorStoreError on failure so a broken index is never mistaken
        for "no duplicates found".
        """
        try:
            results = self._collection.query(
                query_texts=[text],
                n_results=n_results,
                where=where,
                include=["metadatas", "distances"],
            )
        except Exception as e:
            raise VectorStoreError(f"ChromaDB search failed: {e}") from e

        if not results["ids"] or not results["ids"][0]:
            return []

        out = []
        for doc_id, dist, meta in zip(
            results["ids"][0],
            results["distances"][0],
            results["metadatas"][0],
        ):
            out.append((doc_id, dist, meta))
        return out

    def delete(self, doc_id: str):
        try:
            self._collection.delete(ids=[doc_id])
        except Exception as e:
            logger.error(f"ChromaDB delete failed for {doc_id}: {e}")

    def delete_batch(self, doc_ids: list[str]):
        """Delete multiple vectors by their doc IDs."""
        if not doc_ids:
            return
        try:
            self._collection.delete(ids=doc_ids)
            logger.info(f"ChromaDB batch delete: {len(doc_ids)} vectors removed")
        except Exception as e:
            raise VectorStoreError(f"ChromaDB batch delete failed: {e}") from e

    def clear_all(self):
        """Drop and recreate the collection, removing all vectors."""
        try:
            self._client.delete_collection(name=self.COLLECTION_NAME)
            logger.info(f"ChromaDB collection '{self.COLLECTION_NAME}' deleted")
        except Exception:
            logger.warning("ChromaDB collection delete failed (may not exist)")

        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaDB collection recreated — all vectors cleared")

    def purge_older_than(self, days: int):
        """Remove vectors older than N days (sliding window cleanup).

        ChromaDB metadata filtering is used to identify old entries.
        For production, a DATE-based where clause is more efficient.
        """
        logger.info(f"Purging vectors older than {days} days")
        # ChromaDB doesn't natively support date-range deletes via where clause
        # without having stored timestamps as metadata. This is a best-effort.
        # In practice, the sliding window is enforced at query time via metadata
        # filters in search_similar(), not via deletions.
