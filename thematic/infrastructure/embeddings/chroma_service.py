"""
chroma_embedding_service.py — ChromaDB + sentence-transformers embedding service
=================================================================================

Satisfies the ``EmbeddingService`` protocol.

Uses a multilingual sentence-transformer model suitable for Spanish-heavy
qualitative material, stored in a local ChromaDB vector database.

Recommended model
-----------------
``paraphrase-multilingual-MiniLM-L12-v2``
  - 118 MB download
  - Supports 50+ languages including Spanish
  - 384-dimension embeddings
  - ~200 segments/second on CPU

For higher quality on the university server:
``paraphrase-multilingual-mpnet-base-v2``
  - 278 MB download
  - Better Spanish semantic similarity
  - 768-dimension embeddings
  - ~80 segments/second on CPU

Dependencies
------------
    pip install sentence-transformers chromadb
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
_COLLECTION_NAME = "segments"


class ChromaEmbeddingService:
    """
    Compute and retrieve dense embeddings using ChromaDB + sentence-transformers.

    Satisfies the ``EmbeddingService`` protocol.

    Parameters
    ----------
    persist_path:
        Directory where ChromaDB stores its data.  Created if absent.
    model_name:
        Sentence-transformer model identifier.
    project_id:
        When set, embeddings are tagged with this project ID for filtering.

    Example
    -------
    >>> service = ChromaEmbeddingService(persist_path=Path("./chroma_store"))
    >>> emb_id = service.embed_and_store("seg-001", "La comunidad se organizó…")
    >>> hits = service.find_similar("organización comunitaria", top_k=5)
    """

    def __init__(
        self,
        persist_path: Path | str = "./chroma_store",
        model_name: str = _DEFAULT_MODEL,
        project_id: str = "",
    ) -> None:
        self._path = Path(persist_path)
        self._model_name = model_name
        self._project_id = project_id
        self._client = None
        self._collection = None
        self._model = None

    # ── public API ────────────────────────────────────────────────────────────

    def embed_and_store(self, segment_id: str, text: str) -> str:
        """
        Compute embedding for *text* and store it keyed by *segment_id*.

        Returns the *segment_id* as the embedding ID (1:1 mapping).
        """
        coll = self._get_collection()
        model = self._get_model()

        vector = model.encode(text, normalize_embeddings=True).tolist()
        meta = {"segment_id": segment_id}
        if self._project_id:
            meta["project_id"] = self._project_id

        # Upsert so re-running ingestion is idempotent.
        coll.upsert(ids=[segment_id], embeddings=[vector], metadatas=[meta], documents=[text])
        return segment_id

    def embed_batch(self, items: list[tuple[str, str]]) -> list[str]:
        """
        Embed and store multiple (segment_id, text) pairs in one call.

        Returns list of segment_ids (used as embedding_ids) in the same order.
        """
        if not items:
            return []

        coll = self._get_collection()
        model = self._get_model()

        ids = [item[0] for item in items]
        texts = [item[1] for item in items]

        logger.info("Encoding %d segments with %s …", len(texts), self._model_name)
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()

        metadatas = [
            {"segment_id": sid, **({"project_id": self._project_id} if self._project_id else {})}
            for sid in ids
        ]

        coll.upsert(ids=ids, embeddings=vectors, metadatas=metadatas, documents=texts)
        logger.info("Stored %d embeddings.", len(ids))
        return ids

    def find_similar(
        self,
        query_text: str,
        top_k: int = 10,
        project_id: str | None = None,
    ) -> list[tuple[str, float]]:
        """
        Return (segment_id, cosine_similarity) pairs for the most similar segments.

        Parameters
        ----------
        query_text:   Text to embed and query against.
        top_k:        Number of nearest neighbours to return.
        project_id:   When set, filter results to this project.
        """
        coll = self._get_collection()
        model = self._get_model()

        query_vector = model.encode(query_text, normalize_embeddings=True).tolist()

        where = {"project_id": project_id} if project_id else None

        results = coll.query(
            query_embeddings=[query_vector],
            n_results=min(top_k, max(1, coll.count())),
            where=where,
            include=["distances", "metadatas"],
        )

        ids = results["ids"][0] if results["ids"] else []
        distances = results["distances"][0] if results["distances"] else []

        # ChromaDB returns L2 distances; convert to cosine similarity.
        return [(seg_id, round(1.0 - (d / 2.0), 4)) for seg_id, d in zip(ids, distances)]

    def get_all_embeddings(self, project_id: str) -> list[tuple[str, list[float]]]:
        """
        Return all (segment_id, vector) pairs for *project_id*.

        Used by clustering pipelines.
        """
        coll = self._get_collection()
        total = coll.count()
        if total == 0:
            return []

        where = {"project_id": project_id} if project_id else None
        results = coll.get(
            where=where,
            include=["embeddings", "metadatas"],
            limit=total,
        )

        ids = results.get("ids", [])
        embeddings = results.get("embeddings", [])
        return list(zip(ids, embeddings))

    def collection_count(self) -> int:
        """Total number of stored embeddings."""
        return self._get_collection().count()

    # ── private ───────────────────────────────────────────────────────────────

    def _get_client(self):  # type: ignore[return]
        if self._client is not None:
            return self._client
        try:
            import chromadb  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "chromadb is required for the embedding service.\n"
                "Install: pip install chromadb"
            ) from exc
        self._path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self._path))
        logger.info("ChromaDB client initialised at '%s'.", self._path)
        return self._client

    def _get_collection(self):  # type: ignore[return]
        if self._collection is not None:
            return self._collection
        client = self._get_client()
        self._collection = client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "l2"},
        )
        return self._collection

    def _get_model(self):  # type: ignore[return]
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for embeddings.\n"
                "Install: pip install sentence-transformers"
            ) from exc
        logger.info("Loading embedding model '%s' …", self._model_name)
        self._model = SentenceTransformer(self._model_name)
        return self._model
