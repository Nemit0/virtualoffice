"""
Email Clustering Module

This module provides functionality for clustering emails using embeddings,
dimensionality reduction, and machine learning clustering algorithms.

Components:
- embedding_util: OpenAI embeddings wrapper
- faiss_store: FAISS vector storage
- cluster_engine: Main clustering pipeline (DBSCAN + t-SNE)
- label_generator: GPT-powered cluster labeling
- db: SQLite database for cluster metadata
- models: Pydantic models for data structures
"""

__all__ = [
    "embedding_util",
    "faiss_store",
    "cluster_engine",
    "label_generator",
    "db",
    "models",
]
