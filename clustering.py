"""
clustering.py — Semantic clustering use case
============================================

Application layer: takes the full embedding matrix for a project, runs
HDBSCAN clustering, then asks the LLM to propose a category label for each
cluster.  All results are stored as ``Cluster`` entities with status=pending
for analyst review.

Why HDBSCAN?
------------
The SRD explicitly requires "exploratory clustering that tolerates uneven
thematic densities and allows outlier detection."  HDBSCAN:
  - Automatically determines the number of clusters (no k parameter)
  - Assigns low-confidence points as noise (label -1) rather than forcing them
  - Handles clusters of very different sizes and densities
  - Produces a coherence score (DBCV) for each cluster

Dependencies
------------
    pip install hdbscan scikit-learn numpy
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from thematic.domain.entities import Category, Cluster, ModelRun, ModelTier, new_id
from thematic.domain.protocols import (
    ClusterRepository,
    EmbeddingService,
    LLMService,
    ModelRunRepository,
    SegmentRepository,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClusteringConfig:
    """
    Parameters for one HDBSCAN clustering run.

    Attributes
    ----------
    min_cluster_size:
        Minimum number of segments to form a cluster.  Smaller = more clusters,
        more noise points.  Good starting point: 5–10 for interview corpora.
    min_samples:
        Controls cluster density.  Lower = more permissive.  Usually 1–3.
    metric:
        Distance metric.  ``"euclidean"`` works well with L2-normalised embeddings.
    label_top_k:
        Number of representative excerpts sent to the LLM for label proposals.
    request_llm_labels:
        When True, call the LLM to propose a category label for each cluster.
    """

    min_cluster_size: int = 5
    min_samples: int = 1
    metric: str = "euclidean"
    label_top_k: int = 8
    request_llm_labels: bool = True


class RunClusteringUseCase:
    """
    Embed → cluster → (optionally) LLM-label → persist clusters.

    Every cluster starts as ``is_reviewed=False`` and requires analyst
    confirmation before it can be promoted to a Category.

    Parameters
    ----------
    embedding_service:  Source of all segment embeddings.
    segment_repo:       Fetches segment text for LLM context.
    cluster_repo:       Persists the resulting clusters.
    run_repo:           Persists the ModelRun for audit.
    llm_service:        LLM adapter for label proposals (optional).
    config:             HDBSCAN parameters.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        segment_repo: SegmentRepository,
        cluster_repo: ClusterRepository,
        run_repo: ModelRunRepository,
        llm_service: LLMService | None = None,
        config: ClusteringConfig | None = None,
    ) -> None:
        self._embedder = embedding_service
        self._segment_repo = segment_repo
        self._cluster_repo = cluster_repo
        self._run_repo = run_repo
        self._llm = llm_service
        self._config = config or ClusteringConfig()

    def execute(
        self,
        project_id: str,
        existing_category_labels: list[str] | None = None,
    ) -> list[Cluster]:
        """
        Run the full clustering pipeline for *project_id*.

        Parameters
        ----------
        project_id:
            The project whose segments will be clustered.
        existing_category_labels:
            Passed to the LLM so it can avoid proposing duplicate labels.

        Returns
        -------
        list[Cluster]
            Pending clusters, ordered by coherence score descending.
            Noise points (HDBSCAN label -1) are not returned.
        """
        # 1. Fetch all embeddings.
        logger.info("Fetching embeddings for project '%s' …", project_id)
        embedding_pairs = self._embedder.get_all_embeddings(project_id)

        if len(embedding_pairs) < self._config.min_cluster_size * 2:
            logger.warning(
                "Only %d embeddings found — need at least %d for meaningful clustering.",
                len(embedding_pairs),
                self._config.min_cluster_size * 2,
            )
            return []

        segment_ids = [p[0] for p in embedding_pairs]
        vectors = [p[1] for p in embedding_pairs]

        # 2. Run HDBSCAN.
        logger.info("Running HDBSCAN on %d segments …", len(vectors))
        labels, scores = self._run_hdbscan(vectors)

        # 3. Group segment IDs by cluster label.
        clusters_map: dict[int, list[str]] = {}
        score_map: dict[int, float] = {}
        for seg_id, label, score in zip(segment_ids, labels, scores):
            if label == -1:
                continue  # noise point — skip
            clusters_map.setdefault(label, []).append(seg_id)
            score_map[label] = float(score)

        if not clusters_map:
            logger.info("No clusters found (all points classified as noise).")
            return []

        logger.info("Found %d cluster(s) + noise.", len(clusters_map))

        # 4. Create a ModelRun record (even without LLM — records the embedding config).
        run = ModelRun.create(
            project_id=project_id,
            model_name=self._llm.model_name if self._llm else "hdbscan_only",
            model_tier=ModelTier.LOCAL_FAST if self._llm else ModelTier.LOCAL_FAST,
            task="clustering",
            prompt_hash="",
            min_cluster_size=self._config.min_cluster_size,
            min_samples=self._config.min_samples,
            metric=self._config.metric,
            n_segments=len(segment_ids),
            n_clusters=len(clusters_map),
        )
        self._run_repo.save(run)

        # 5. For each cluster, build the Cluster entity.
        existing_cats = existing_category_labels or []
        result_clusters: list[Cluster] = []

        for cluster_label, seg_ids in clusters_map.items():
            # Fetch representative excerpt texts for LLM labelling.
            excerpts = self._get_representative_excerpts(
                seg_ids, top_k=self._config.label_top_k
            )

            # Propose a label via LLM (if configured).
            proposed_label = f"cluster_{cluster_label}"
            if self._config.request_llm_labels and self._llm and excerpts:
                try:
                    proposal = self._llm.propose_cluster_label(
                        excerpts=excerpts,
                        existing_categories=existing_cats,
                    )
                    if proposal.get("label"):
                        proposed_label = str(proposal["label"])
                        existing_cats.append(proposed_label)
                        logger.info(
                            "Cluster %d → '%s' (confidence %.0f%%)",
                            cluster_label, proposed_label,
                            float(proposal.get("confidence", 0)) * 100,
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("LLM label proposal failed for cluster %d: %s", cluster_label, exc)

            cluster = Cluster.create(
                project_id=project_id,
                run_id=run.id,
                label=proposed_label,
                segment_ids=seg_ids,
                coherence_score=score_map.get(cluster_label, 0.0),
            )
            result_clusters.append(cluster)

        # 6. Persist all clusters.
        self._cluster_repo.save_batch(result_clusters)
        logger.info("Saved %d cluster(s) for analyst review.", len(result_clusters))

        return sorted(result_clusters, key=lambda c: c.coherence_score, reverse=True)

    # ── private ───────────────────────────────────────────────────────────────

    def _run_hdbscan(
        self, vectors: list[list[float]]
    ) -> tuple[list[int], list[float]]:
        """Run HDBSCAN and return (labels, per-point_scores)."""
        try:
            import numpy as np  # noqa: PLC0415
            import hdbscan  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "hdbscan and numpy are required for clustering.\n"
                "Install: pip install hdbscan numpy"
            ) from exc

        X = np.array(vectors, dtype="float32")
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=self._config.min_cluster_size,
            min_samples=self._config.min_samples,
            metric=self._config.metric,
            gen_min_span_tree=False,
        )
        clusterer.fit(X)
        labels = clusterer.labels_.tolist()
        # probabilities gives per-point cluster membership strength [0, 1]
        scores = clusterer.probabilities_.tolist()
        return labels, scores

    def _get_representative_excerpts(
        self, segment_ids: list[str], top_k: int
    ) -> list[str]:
        """Fetch the text of up to *top_k* segments from a cluster."""
        texts = []
        for seg_id in segment_ids[:top_k]:
            seg = self._segment_repo.get(seg_id)
            if seg and seg.text:
                texts.append(seg.text[:300])  # truncate very long turns
        return texts
