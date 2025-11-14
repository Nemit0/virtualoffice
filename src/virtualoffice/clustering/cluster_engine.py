"""
Main clustering engine that orchestrates the entire pipeline.

Pipeline steps:
1. Extract emails for persona from vdos.db
2. Generate embeddings via OpenAI API
3. Store embeddings in FAISS
4. Run t-SNE for dimensionality reduction to 3D
5. Run DBSCAN clustering on 3D coordinates
6. Sample 3-5 emails per cluster
7. Generate GPT labels for each cluster
8. Save all data to email_clusters.db
"""

import logging
import random
from datetime import datetime
from typing import Optional, Callable
import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.manifold import TSNE

from virtualoffice.common.db import get_connection as get_vdos_connection
from virtualoffice.clustering import db
from virtualoffice.clustering.models import (
    ClusterMetadata,
    ClusterPoint,
    ClusterSample,
    EmailData,
    PersonaIndexStatus,
)
from virtualoffice.clustering.embedding_util import (
    generate_embeddings_batch,
    prepare_email_text_for_embedding,
)
from virtualoffice.clustering.faiss_store import FaissStore
from virtualoffice.clustering.label_generator import generate_labels_for_clusters

logger = logging.getLogger(__name__)


class ClusterEngine:
    """Main engine for email clustering operations."""

    def __init__(
        self,
        embedding_model: str = "text-embedding-3-small",
        tsne_perplexity: float = 30.0,
        tsne_n_iter: int = 1000,
        dbscan_eps: float = 10.0,
        dbscan_min_samples: int = 3,
        random_seed: int = 42,
    ):
        """
        Initialize clustering engine with parameters.

        Args:
            embedding_model: OpenAI embedding model
            tsne_perplexity: t-SNE perplexity parameter
            tsne_n_iter: t-SNE iteration count
            dbscan_eps: DBSCAN epsilon (neighborhood distance, for normalized 0-100 coordinates)
            dbscan_min_samples: DBSCAN minimum samples per cluster
            random_seed: Random seed for reproducibility
        """
        self.embedding_model = embedding_model
        self.tsne_perplexity = tsne_perplexity
        self.tsne_n_iter = tsne_n_iter
        self.dbscan_eps = dbscan_eps
        self.dbscan_min_samples = dbscan_min_samples
        self.random_seed = random_seed

    def build_index(
        self, persona_id: int, progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> PersonaIndexStatus:
        """
        Build complete clustering index for a persona.

        This is the main pipeline that:
        1. Extracts emails
        2. Generates embeddings
        3. Runs t-SNE
        4. Runs DBSCAN
        5. Samples and labels clusters
        6. Saves all data

        Args:
            persona_id: Persona ID to build index for
            progress_callback: Optional callback(step_name, progress_percent)

        Returns:
            PersonaIndexStatus with indexing results

        Raises:
            ValueError: If persona has no emails or other validation errors
            Exception: If any pipeline step fails
        """
        try:
            self._report_progress(progress_callback, "Initializing", 0.0)

            # Step 1: Extract emails for persona
            self._report_progress(progress_callback, "Extracting emails", 5.0)
            emails = self._extract_emails_for_persona(persona_id)

            if not emails:
                raise ValueError(f"No emails found for persona {persona_id}")

            logger.info(f"Extracted {len(emails)} emails for persona {persona_id}")

            # Get persona name
            persona_name = self._get_persona_name(persona_id)

            # Initialize status
            status = PersonaIndexStatus(
                persona_id=persona_id,
                persona_name=persona_name,
                total_emails=len(emails),
                embedding_model=self.embedding_model,
                status="indexing",
            )
            db.save_persona_index_status(status)

            # Step 2: Generate embeddings
            self._report_progress(progress_callback, "Generating embeddings", 10.0)
            embeddings, email_ids = self._generate_embeddings(emails, progress_callback)

            # Step 3: Store in FAISS
            self._report_progress(progress_callback, "Storing embeddings", 50.0)
            faiss_store = self._store_embeddings(persona_id, embeddings, email_ids)

            # Step 4: Run t-SNE
            self._report_progress(progress_callback, "Running t-SNE dimensionality reduction", 55.0)
            coordinates_3d = self._run_tsne(embeddings)

            # Step 5: Run DBSCAN clustering
            self._report_progress(progress_callback, "Running DBSCAN clustering", 70.0)
            cluster_labels = self._run_dbscan(coordinates_3d)

            # Step 6: Create cluster points
            points = self._create_cluster_points(emails, coordinates_3d, cluster_labels)

            # Step 7: Sample emails per cluster
            self._report_progress(progress_callback, "Sampling emails from clusters", 80.0)
            cluster_samples = self._sample_clusters(emails, cluster_labels)

            # Step 8: Generate GPT labels
            self._report_progress(progress_callback, "Generating cluster labels with GPT", 85.0)
            cluster_labels_gpt = generate_labels_for_clusters(cluster_samples)

            # Step 9: Save clusters to database
            self._report_progress(progress_callback, "Saving cluster data", 90.0)
            self._save_clusters(persona_id, points, cluster_labels_gpt, coordinates_3d, cluster_labels)

            # Step 10: Save FAISS index
            self._report_progress(progress_callback, "Saving FAISS index", 95.0)
            faiss_store.save()

            # Update status to completed
            status.status = "completed"
            status.indexed_at = datetime.now()
            db.save_persona_index_status(status)

            self._report_progress(progress_callback, "Completed", 100.0)

            logger.info(
                f"Successfully built index for persona {persona_id}: "
                f"{len(emails)} emails, {len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)} clusters"
            )

            return status

        except Exception as e:
            logger.error(f"Failed to build index for persona {persona_id}: {e}")
            # Mark as failed
            status = PersonaIndexStatus(
                persona_id=persona_id,
                persona_name=self._get_persona_name(persona_id),
                total_emails=0,
                embedding_model=self.embedding_model,
                status="failed",
                error_message=str(e),
            )
            db.save_persona_index_status(status)
            raise

    def _extract_emails_for_persona(self, persona_id: int) -> list[EmailData]:
        """Extract all emails sent by a persona from vdos.db."""
        # Get persona's email address from people table
        with get_vdos_connection() as conn:
            cursor = conn.cursor()

            # Get persona email address
            cursor.execute(
                """
                SELECT email_address FROM people WHERE id = ?
            """,
                (persona_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Persona {persona_id} not found in database")

            persona_email = row[0]

            # Get all emails sent by this persona
            cursor.execute(
                """
                SELECT id, sender, subject, body, sent_at
                FROM emails
                WHERE sender = ?
                ORDER BY sent_at
            """,
                (persona_email,),
            )

            rows = cursor.fetchall()
            return [
                EmailData(
                    email_id=row[0],
                    sender=row[1],
                    subject=row[2],
                    body=row[3],
                    sent_at=datetime.fromisoformat(row[4]),
                )
                for row in rows
            ]

    def _get_persona_name(self, persona_id: int) -> str:
        """Get persona name from vdos.db."""
        with get_vdos_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM people WHERE id = ?", (persona_id,))
            row = cursor.fetchone()
            return row[0] if row else f"Persona {persona_id}"

    def _generate_embeddings(
        self, emails: list[EmailData], progress_callback: Optional[Callable]
    ) -> tuple[np.ndarray, list[int]]:
        """Generate embeddings for all emails."""
        # Prepare texts
        texts = [prepare_email_text_for_embedding(email.subject, email.body) for email in emails]

        # Generate embeddings in batches
        embeddings_list, total_tokens = generate_embeddings_batch(texts, model=self.embedding_model)

        logger.info(f"Generated {len(embeddings_list)} embeddings using {total_tokens} tokens")

        # Convert to numpy array
        embeddings = np.array(embeddings_list, dtype=np.float32)
        email_ids = [email.email_id for email in emails]

        return embeddings, email_ids

    def _store_embeddings(
        self, persona_id: int, embeddings: np.ndarray, email_ids: list[int]
    ) -> FaissStore:
        """Store embeddings in FAISS index."""
        # Create new store
        store = FaissStore(persona_id, dimension=embeddings.shape[1])
        store.create_index()

        # Add vectors
        store.add_vectors(embeddings, email_ids)

        return store

    def _run_tsne(self, embeddings: np.ndarray) -> np.ndarray:
        """Run t-SNE to reduce embeddings to 3D coordinates."""
        # Adjust perplexity if necessary
        n_samples = embeddings.shape[0]
        perplexity = min(self.tsne_perplexity, (n_samples - 1) / 3)

        tsne = TSNE(
            n_components=3,
            perplexity=perplexity,
            max_iter=self.tsne_n_iter,
            random_state=self.random_seed,
            verbose=0,
        )

        coordinates_3d = tsne.fit_transform(embeddings)

        # Normalize coordinates to 0-100 range for consistent DBSCAN eps values
        # This makes the eps slider values (0.1-10.0) more intuitive
        min_vals = coordinates_3d.min(axis=0)
        max_vals = coordinates_3d.max(axis=0)
        ranges = max_vals - min_vals

        # Avoid division by zero
        ranges[ranges == 0] = 1.0

        # Scale to 0-100 range
        coordinates_3d = ((coordinates_3d - min_vals) / ranges) * 100.0

        logger.info(
            f"t-SNE completed: {embeddings.shape} -> {coordinates_3d.shape}, "
            f"normalized to range [0, 100]"
        )

        return coordinates_3d

    def _run_dbscan(self, coordinates_3d: np.ndarray) -> np.ndarray:
        """Run DBSCAN clustering on 3D coordinates."""
        dbscan = DBSCAN(eps=self.dbscan_eps, min_samples=self.dbscan_min_samples)

        cluster_labels = dbscan.fit_predict(coordinates_3d)

        n_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
        n_noise = list(cluster_labels).count(-1)

        logger.info(f"DBSCAN completed: {n_clusters} clusters, {n_noise} noise points")

        return cluster_labels

    def _create_cluster_points(
        self, emails: list[EmailData], coordinates_3d: np.ndarray, cluster_labels: np.ndarray
    ) -> list[ClusterPoint]:
        """Create ClusterPoint objects from emails and coordinates."""
        points = []
        for i, email in enumerate(emails):
            points.append(
                ClusterPoint(
                    email_id=email.email_id,
                    x=float(coordinates_3d[i, 0]),
                    y=float(coordinates_3d[i, 1]),
                    z=float(coordinates_3d[i, 2]),
                    cluster_label=int(cluster_labels[i]),
                    subject=email.subject,
                    sender=email.sender,
                )
            )
        return points

    def _sample_clusters(
        self, emails: list[EmailData], cluster_labels: np.ndarray, samples_per_cluster: int = 5
    ) -> dict[int, list[ClusterSample]]:
        """Sample random emails from each cluster for labeling."""
        # Group emails by cluster
        cluster_emails = {}
        for i, cluster_label in enumerate(cluster_labels):
            cluster_label = int(cluster_label)
            if cluster_label not in cluster_emails:
                cluster_emails[cluster_label] = []
            cluster_emails[cluster_label].append(emails[i])

        # Sample from each cluster
        cluster_samples = {}
        for cluster_label, emails_in_cluster in cluster_emails.items():
            # Random sample (or all if fewer than samples_per_cluster)
            sample_size = min(samples_per_cluster, len(emails_in_cluster))
            sampled_emails = random.sample(emails_in_cluster, sample_size)

            cluster_samples[cluster_label] = [
                ClusterSample(email_id=email.email_id, subject=email.subject, body=email.body)
                for email in sampled_emails
            ]

        return cluster_samples

    def _save_clusters(
        self,
        persona_id: int,
        points: list[ClusterPoint],
        labels: dict[int, any],
        coordinates_3d: np.ndarray,
        cluster_labels_array: np.ndarray,
    ) -> None:
        """Save cluster metadata and points to database."""
        # Calculate centroids
        centroids = {}
        for cluster_label in set(cluster_labels_array):
            cluster_label = int(cluster_label)
            mask = cluster_labels_array == cluster_label
            centroid = coordinates_3d[mask].mean(axis=0)
            centroids[cluster_label] = centroid

        # Save clusters
        cluster_id_map = {}
        for cluster_label, label_obj in labels.items():
            num_emails = (cluster_labels_array == cluster_label).sum()
            centroid = centroids.get(cluster_label, [0, 0, 0])

            metadata = ClusterMetadata(
                cluster_id=0,  # Will be auto-assigned
                persona_id=persona_id,
                cluster_label=cluster_label,
                short_label=label_obj.short_label,
                description=label_obj.description,
                num_emails=int(num_emails),
                centroid_x=float(centroid[0]),
                centroid_y=float(centroid[1]),
                centroid_z=float(centroid[2]),
                created_at=datetime.now(),
            )

            cluster_id = db.save_cluster(metadata)
            cluster_id_map[cluster_label] = cluster_id

            # Save samples for this cluster
            samples = self._sample_clusters(
                [
                    EmailData(
                        email_id=p.email_id,
                        sender=p.sender,
                        subject=p.subject,
                        body="",  # We'll need to fetch body if needed
                        sent_at=datetime.now(),
                    )
                    for p in points
                    if p.cluster_label == cluster_label
                ],
                np.array([cluster_label] * sum(1 for p in points if p.cluster_label == cluster_label)),
            )

            if cluster_label in samples:
                db.save_cluster_samples(cluster_id, samples[cluster_label], datetime.now())

        # Save email positions
        db.save_email_positions(points, persona_id)

        logger.info(f"Saved {len(labels)} clusters and {len(points)} email positions")

    def _report_progress(
        self, callback: Optional[Callable], step: str, percent: float
    ) -> None:
        """Report progress to callback if provided."""
        if callback:
            callback(step, percent)
        logger.info(f"Progress: {step} ({percent:.1f}%)")


# Convenience functions


def build_index_for_persona(persona_id: int, progress_callback: Optional[Callable] = None) -> PersonaIndexStatus:
    """Build clustering index for a persona with default parameters."""
    engine = ClusterEngine()
    return engine.build_index(persona_id, progress_callback)


def get_visualization_data(persona_id: int) -> Optional[dict]:
    """Get complete visualization data for a persona."""
    # Check if index exists
    status = db.get_persona_index_status(persona_id)
    if not status or status.status != "completed":
        return None

    # Get clusters
    clusters = db.get_clusters_for_persona(persona_id)

    # Get points (without joining to emails - we'll use cached data)
    # This is a simplified version - in production we'd need to properly join
    # For now, return cluster metadata only
    statistics = db.get_clustering_statistics(persona_id)

    return {
        "persona_id": persona_id,
        "persona_name": status.persona_name,
        "clusters": [
            {
                "cluster_id": c.cluster_id,
                "cluster_label": c.cluster_label,
                "short_label": c.short_label,
                "description": c.description,
                "num_emails": c.num_emails,
                "centroid": [c.centroid_x, c.centroid_y, c.centroid_z],
            }
            for c in clusters
        ],
        "statistics": statistics,
        "indexed_at": status.indexed_at,
    }
