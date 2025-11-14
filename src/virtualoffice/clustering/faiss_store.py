"""
FAISS vector storage for email embeddings.

Each persona gets its own FAISS index file for isolation and efficiency.
"""

import logging
from pathlib import Path
from typing import Optional
import numpy as np
import faiss

logger = logging.getLogger(__name__)

# FAISS index directory - sibling to email_clusters.db
INDEX_DIR = Path(__file__).resolve().parents[3]  # Project root


class FaissStore:
    """
    FAISS vector storage for email embeddings.

    Each persona has a separate index file: email_embeddings_{persona_id}.faiss
    """

    def __init__(self, persona_id: int, dimension: int = 1536):
        """
        Initialize FAISS store for a persona.

        Args:
            persona_id: Persona identifier
            dimension: Embedding dimension (1536 for text-embedding-3-small)
        """
        self.persona_id = persona_id
        self.dimension = dimension
        self.index_path = INDEX_DIR / f"email_embeddings_{persona_id}.faiss"
        self.index: Optional[faiss.IndexFlatL2] = None
        self._email_ids: list[int] = []  # Track which email_id corresponds to each index position

    def create_index(self) -> None:
        """Create a new FAISS index."""
        # Use IndexFlatL2 for exact L2 distance search
        # For larger datasets (>100k), could use IndexIVFFlat or IndexHNSW
        self.index = faiss.IndexFlatL2(self.dimension)
        self._email_ids = []
        logger.info(f"Created new FAISS index for persona {self.persona_id}, dim={self.dimension}")

    def add_vectors(self, vectors: np.ndarray, email_ids: list[int]) -> None:
        """
        Add embedding vectors to the index.

        Args:
            vectors: numpy array of shape (n, dimension)
            email_ids: List of email IDs corresponding to each vector

        Raises:
            ValueError: If vectors shape doesn't match dimension or email_ids length mismatch
        """
        if self.index is None:
            self.create_index()

        # Validate input
        if vectors.ndim != 2:
            raise ValueError(f"Vectors must be 2D array, got shape {vectors.shape}")

        if vectors.shape[1] != self.dimension:
            raise ValueError(
                f"Vector dimension {vectors.shape[1]} doesn't match index dimension {self.dimension}"
            )

        if len(email_ids) != vectors.shape[0]:
            raise ValueError(
                f"Number of email_ids ({len(email_ids)}) doesn't match number of vectors ({vectors.shape[0]})"
            )

        # Convert to float32 if needed (FAISS requires float32)
        if vectors.dtype != np.float32:
            vectors = vectors.astype(np.float32)

        # Add to index
        self.index.add(vectors)
        self._email_ids.extend(email_ids)

        logger.info(
            f"Added {len(email_ids)} vectors to persona {self.persona_id} index. "
            f"Total vectors: {self.index.ntotal}"
        )

    def search(self, query_vector: np.ndarray, k: int = 5) -> tuple[list[int], list[float]]:
        """
        Search for k nearest neighbors.

        Args:
            query_vector: Query embedding vector (1D array of length dimension)
            k: Number of nearest neighbors to return

        Returns:
            Tuple of (email_ids, distances)

        Raises:
            ValueError: If index is empty or query vector dimension mismatch
        """
        if self.index is None or self.index.ntotal == 0:
            raise ValueError("Index is empty, cannot search")

        # Ensure query_vector is 2D with shape (1, dimension)
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)

        if query_vector.shape[1] != self.dimension:
            raise ValueError(
                f"Query vector dimension {query_vector.shape[1]} doesn't match index dimension {self.dimension}"
            )

        # Convert to float32
        if query_vector.dtype != np.float32:
            query_vector = query_vector.astype(np.float32)

        # Search
        k = min(k, self.index.ntotal)  # Can't request more than total vectors
        distances, indices = self.index.search(query_vector, k)

        # Map indices to email_ids
        email_ids = [self._email_ids[idx] for idx in indices[0]]
        distances_list = distances[0].tolist()

        return email_ids, distances_list

    def get_all_vectors(self) -> np.ndarray:
        """
        Get all vectors from the index.

        Returns:
            numpy array of shape (n, dimension) containing all vectors

        Raises:
            ValueError: If index is empty
        """
        if self.index is None or self.index.ntotal == 0:
            raise ValueError("Index is empty")

        # FAISS IndexFlatL2 stores vectors in a contiguous array
        # We can reconstruct them
        n = self.index.ntotal
        vectors = np.zeros((n, self.dimension), dtype=np.float32)

        for i in range(n):
            vectors[i] = self.index.reconstruct(i)

        return vectors

    def get_email_ids(self) -> list[int]:
        """Get list of email IDs in the index (in order)."""
        return self._email_ids.copy()

    def save(self) -> None:
        """Save index and metadata to disk."""
        if self.index is None:
            raise ValueError("Cannot save empty index")

        # Save FAISS index
        faiss.write_index(self.index, str(self.index_path))

        # Save email_ids mapping
        metadata_path = self.index_path.with_suffix(".ids.npy")
        np.save(metadata_path, np.array(self._email_ids, dtype=np.int32))

        logger.info(
            f"Saved FAISS index for persona {self.persona_id} to {self.index_path} "
            f"({self.index.ntotal} vectors)"
        )

    def load(self) -> bool:
        """
        Load index and metadata from disk.

        Returns:
            True if loaded successfully, False if files don't exist

        Raises:
            Exception: If files exist but loading fails
        """
        if not self.index_path.exists():
            logger.info(f"No existing index found for persona {self.persona_id}")
            return False

        metadata_path = self.index_path.with_suffix(".ids.npy")
        if not metadata_path.exists():
            raise ValueError(f"Index file exists but metadata missing: {metadata_path}")

        # Load FAISS index
        self.index = faiss.read_index(str(self.index_path))

        # Load email_ids mapping
        email_ids_array = np.load(metadata_path)
        self._email_ids = email_ids_array.tolist()

        # Validate
        if self.index.ntotal != len(self._email_ids):
            raise ValueError(
                f"Index/metadata mismatch: {self.index.ntotal} vectors but {len(self._email_ids)} email_ids"
            )

        logger.info(
            f"Loaded FAISS index for persona {self.persona_id} from {self.index_path} "
            f"({self.index.ntotal} vectors)"
        )
        return True

    def delete(self) -> None:
        """Delete index files from disk."""
        if self.index_path.exists():
            self.index_path.unlink()
            logger.info(f"Deleted FAISS index file: {self.index_path}")

        metadata_path = self.index_path.with_suffix(".ids.npy")
        if metadata_path.exists():
            metadata_path.unlink()
            logger.info(f"Deleted metadata file: {metadata_path}")

        self.index = None
        self._email_ids = []

    def size(self) -> int:
        """Get number of vectors in index."""
        if self.index is None:
            return 0
        return self.index.ntotal


# Utility functions


def create_store_for_persona(persona_id: int, dimension: int = 1536) -> FaissStore:
    """
    Create a new FAISS store for a persona.

    Args:
        persona_id: Persona identifier
        dimension: Embedding dimension

    Returns:
        FaissStore instance
    """
    store = FaissStore(persona_id, dimension)
    store.create_index()
    return store


def load_store_for_persona(persona_id: int, dimension: int = 1536) -> Optional[FaissStore]:
    """
    Load existing FAISS store for a persona.

    Args:
        persona_id: Persona identifier
        dimension: Embedding dimension

    Returns:
        FaissStore instance if found, None otherwise
    """
    store = FaissStore(persona_id, dimension)
    if store.load():
        return store
    return None


def delete_store_for_persona(persona_id: int) -> None:
    """
    Delete FAISS store files for a persona.

    Args:
        persona_id: Persona identifier
    """
    store = FaissStore(persona_id)
    store.delete()
