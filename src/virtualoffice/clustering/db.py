"""
Database operations for email clustering metadata.

Uses a separate SQLite database (email_clusters.db) from the main vdos.db
to keep clustering data isolated and easily manageable.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from virtualoffice.clustering.models import (
    ClusterMetadata,
    ClusterPoint,
    ClusterSample,
    PersonaIndexStatus,
)

# Database path - sibling to vdos.db
DB_DIR = Path(__file__).resolve().parents[3]  # Goes up to project root
DB_PATH = DB_DIR / "email_clusters.db"


def init_database() -> None:
    """Initialize the email_clusters database with schema if it doesn't exist."""
    if not DB_PATH.exists():
        print(f"Creating email_clusters.db at {DB_PATH}")

    # Create direct connection to avoid recursion with get_connection()
    conn = sqlite3.connect(
        str(DB_PATH),
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False,
        timeout=30.0,
    )
    try:
        cursor = conn.cursor()

        # Persona indexing status table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS persona_indexes (
                persona_id INTEGER PRIMARY KEY,
                persona_name TEXT NOT NULL,
                total_emails INTEGER NOT NULL,
                indexed_at TEXT,
                embedding_model TEXT NOT NULL,
                status TEXT CHECK(status IN ('indexing', 'completed', 'failed')) NOT NULL,
                error_message TEXT
            )
        """
        )

        # Cluster metadata table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS clusters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                persona_id INTEGER NOT NULL,
                cluster_label INTEGER NOT NULL,
                short_label TEXT,
                description TEXT,
                num_emails INTEGER NOT NULL,
                centroid_x REAL,
                centroid_y REAL,
                centroid_z REAL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(persona_id) REFERENCES persona_indexes(persona_id),
                UNIQUE(persona_id, cluster_label)
            )
        """
        )

        # Email positions in 3D space with cluster assignments
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS email_positions (
                email_id INTEGER NOT NULL,
                persona_id INTEGER NOT NULL,
                cluster_id INTEGER,
                x REAL NOT NULL,
                y REAL NOT NULL,
                z REAL NOT NULL,
                embedding_index INTEGER NOT NULL,
                FOREIGN KEY(cluster_id) REFERENCES clusters(id),
                PRIMARY KEY(email_id, persona_id)
            )
        """
        )

        # Sample emails for cluster labeling
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cluster_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cluster_id INTEGER NOT NULL,
                email_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                sampled_at TEXT NOT NULL,
                FOREIGN KEY(cluster_id) REFERENCES clusters(id)
            )
        """
        )

        # Create indexes for performance
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_email_positions_persona
            ON email_positions(persona_id)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_email_positions_cluster
            ON email_positions(cluster_id)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_clusters_persona
            ON clusters(persona_id)
        """
        )

        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_connection():
    """Get database connection with proper configuration."""
    init_database()  # Ensure database exists

    conn = sqlite3.connect(
        str(DB_PATH),
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False,
        timeout=30.0,
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")

    try:
        yield conn
    finally:
        conn.close()


# ============================================================================
# Persona Index Operations
# ============================================================================


def save_persona_index_status(status: PersonaIndexStatus) -> None:
    """Save or update persona indexing status."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO persona_indexes
            (persona_id, persona_name, total_emails, indexed_at, embedding_model, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(persona_id) DO UPDATE SET
                persona_name = excluded.persona_name,
                total_emails = excluded.total_emails,
                indexed_at = excluded.indexed_at,
                embedding_model = excluded.embedding_model,
                status = excluded.status,
                error_message = excluded.error_message
        """,
            (
                status.persona_id,
                status.persona_name,
                status.total_emails,
                status.indexed_at.isoformat() if status.indexed_at else None,
                status.embedding_model,
                status.status,
                status.error_message,
            ),
        )
        conn.commit()


def get_persona_index_status(persona_id: int) -> Optional[PersonaIndexStatus]:
    """Get persona indexing status."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT persona_id, persona_name, total_emails, indexed_at, embedding_model, status, error_message
            FROM persona_indexes
            WHERE persona_id = ?
        """,
            (persona_id,),
        )
        row = cursor.fetchone()
        if row:
            return PersonaIndexStatus(
                persona_id=row[0],
                persona_name=row[1],
                total_emails=row[2],
                indexed_at=datetime.fromisoformat(row[3]) if row[3] else None,
                embedding_model=row[4],
                status=row[5],
                error_message=row[6],
            )
        return None


def get_all_persona_index_statuses() -> list[PersonaIndexStatus]:
    """Get all persona indexing statuses."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT persona_id, persona_name, total_emails, indexed_at, embedding_model, status, error_message
            FROM persona_indexes
            ORDER BY persona_name
        """
        )
        rows = cursor.fetchall()
        return [
            PersonaIndexStatus(
                persona_id=row[0],
                persona_name=row[1],
                total_emails=row[2],
                indexed_at=datetime.fromisoformat(row[3]) if row[3] else None,
                embedding_model=row[4],
                status=row[5],
                error_message=row[6],
            )
            for row in rows
        ]


def delete_persona_index(persona_id: int) -> None:
    """Delete all data for a persona (for re-indexing)."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Delete in correct order to respect foreign key constraints
        # 1. Delete email positions (references clusters)
        cursor.execute("DELETE FROM email_positions WHERE persona_id = ?", (persona_id,))

        # 2. Delete cluster samples (references clusters)
        cursor.execute("""
            DELETE FROM cluster_samples
            WHERE cluster_id IN (SELECT id FROM clusters WHERE persona_id = ?)
        """, (persona_id,))

        # 3. Delete clusters (references persona_indexes)
        cursor.execute("DELETE FROM clusters WHERE persona_id = ?", (persona_id,))

        # 4. Finally delete persona index status
        cursor.execute("DELETE FROM persona_indexes WHERE persona_id = ?", (persona_id,))

        conn.commit()


# ============================================================================
# Cluster Operations
# ============================================================================


def save_cluster(metadata: ClusterMetadata) -> int:
    """Save cluster metadata and return cluster ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO clusters
            (persona_id, cluster_label, short_label, description, num_emails,
             centroid_x, centroid_y, centroid_z, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(persona_id, cluster_label) DO UPDATE SET
                short_label = excluded.short_label,
                description = excluded.description,
                num_emails = excluded.num_emails,
                centroid_x = excluded.centroid_x,
                centroid_y = excluded.centroid_y,
                centroid_z = excluded.centroid_z,
                created_at = excluded.created_at
        """,
            (
                metadata.persona_id,
                metadata.cluster_label,
                metadata.short_label,
                metadata.description,
                metadata.num_emails,
                metadata.centroid_x,
                metadata.centroid_y,
                metadata.centroid_z,
                metadata.created_at.isoformat(),
            ),
        )

        # Query for the ID since lastrowid doesn't work reliably with ON CONFLICT
        cursor.execute(
            "SELECT id FROM clusters WHERE persona_id = ? AND cluster_label = ?",
            (metadata.persona_id, metadata.cluster_label)
        )
        cluster_id = cursor.fetchone()[0]

        conn.commit()
        return cluster_id


def get_clusters_for_persona(persona_id: int) -> list[ClusterMetadata]:
    """Get all clusters for a persona."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, persona_id, cluster_label, short_label, description, num_emails,
                   centroid_x, centroid_y, centroid_z, created_at
            FROM clusters
            WHERE persona_id = ?
            ORDER BY cluster_label
        """,
            (persona_id,),
        )
        rows = cursor.fetchall()
        return [
            ClusterMetadata(
                cluster_id=row[0],
                persona_id=row[1],
                cluster_label=row[2],
                short_label=row[3],
                description=row[4],
                num_emails=row[5],
                centroid_x=row[6],
                centroid_y=row[7],
                centroid_z=row[8],
                created_at=datetime.fromisoformat(row[9]),
            )
            for row in rows
        ]


def get_cluster_by_id(cluster_id: int) -> Optional[ClusterMetadata]:
    """Get cluster by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, persona_id, cluster_label, short_label, description, num_emails,
                   centroid_x, centroid_y, centroid_z, created_at
            FROM clusters
            WHERE id = ?
        """,
            (cluster_id,),
        )
        row = cursor.fetchone()
        if row:
            return ClusterMetadata(
                cluster_id=row[0],
                persona_id=row[1],
                cluster_label=row[2],
                short_label=row[3],
                description=row[4],
                num_emails=row[5],
                centroid_x=row[6],
                centroid_y=row[7],
                centroid_z=row[8],
                created_at=datetime.fromisoformat(row[9]),
            )
        return None


# ============================================================================
# Email Position Operations
# ============================================================================


def save_email_positions(points: list[ClusterPoint], persona_id: int) -> None:
    """Bulk save email positions."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Get cluster IDs mapping
        cursor.execute(
            """
            SELECT cluster_label, id FROM clusters WHERE persona_id = ?
        """,
            (persona_id,),
        )
        cluster_id_map = {label: cid for label, cid in cursor.fetchall()}

        # Insert positions
        data = [
            (
                point.email_id,
                persona_id,
                cluster_id_map.get(point.cluster_label),
                point.x,
                point.y,
                point.z,
                idx,  # embedding_index
            )
            for idx, point in enumerate(points)
        ]

        cursor.executemany(
            """
            INSERT OR REPLACE INTO email_positions
            (email_id, persona_id, cluster_id, x, y, z, embedding_index)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            data,
        )
        conn.commit()


def get_email_positions_for_persona(persona_id: int) -> list[ClusterPoint]:
    """Get all email positions for a persona."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ep.email_id, ep.x, ep.y, ep.z, c.cluster_label,
                   e.subject, e.sender
            FROM email_positions ep
            LEFT JOIN clusters c ON ep.cluster_id = c.id
            LEFT JOIN emails e ON ep.email_id = e.id
            WHERE ep.persona_id = ?
        """,
            (persona_id,),
        )
        rows = cursor.fetchall()
        # Note: This joins with the main vdos.db emails table
        # We'll need to handle this carefully
        return [
            ClusterPoint(
                email_id=row[0],
                x=row[1],
                y=row[2],
                z=row[3],
                cluster_label=row[4] if row[4] is not None else -1,
                subject=row[5] or "",
                sender=row[6] or "",
            )
            for row in rows
        ]


# ============================================================================
# Cluster Sample Operations
# ============================================================================


def save_cluster_samples(
    cluster_id: int, samples: list[ClusterSample], sampled_at: datetime
) -> None:
    """Save cluster sample emails."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Delete existing samples for this cluster
        cursor.execute("DELETE FROM cluster_samples WHERE cluster_id = ?", (cluster_id,))

        # Insert new samples
        data = [
            (cluster_id, sample.email_id, sample.subject, sample.body, sampled_at.isoformat())
            for sample in samples
        ]

        cursor.executemany(
            """
            INSERT INTO cluster_samples
            (cluster_id, email_id, subject, body, sampled_at)
            VALUES (?, ?, ?, ?, ?)
        """,
            data,
        )
        conn.commit()


def get_cluster_samples(cluster_id: int) -> list[ClusterSample]:
    """Get sample emails for a cluster."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT email_id, subject, body
            FROM cluster_samples
            WHERE cluster_id = ?
        """,
            (cluster_id,),
        )
        rows = cursor.fetchall()
        return [ClusterSample(email_id=row[0], subject=row[1], body=row[2]) for row in rows]


# ============================================================================
# Statistics
# ============================================================================


def get_clustering_statistics(persona_id: int) -> dict:
    """Get clustering statistics for a persona."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Total emails
        cursor.execute(
            """
            SELECT COUNT(*) FROM email_positions WHERE persona_id = ?
        """,
            (persona_id,),
        )
        total_emails = cursor.fetchone()[0]

        # Number of clusters (excluding noise)
        cursor.execute(
            """
            SELECT COUNT(*) FROM clusters WHERE persona_id = ? AND cluster_label >= 0
        """,
            (persona_id,),
        )
        num_clusters = cursor.fetchone()[0]

        # Noise points
        cursor.execute(
            """
            SELECT COUNT(*) FROM clusters WHERE persona_id = ? AND cluster_label = -1
        """,
            (persona_id,),
        )
        noise_points = cursor.fetchone()[0]

        # Average cluster size
        cursor.execute(
            """
            SELECT AVG(num_emails) FROM clusters WHERE persona_id = ? AND cluster_label >= 0
        """,
            (persona_id,),
        )
        avg_cluster_size = cursor.fetchone()[0] or 0

        return {
            "total_emails": total_emails,
            "num_clusters": num_clusters,
            "noise_points": noise_points,
            "avg_cluster_size": round(avg_cluster_size, 1),
        }
