"""
API request/response schemas for the clustering server.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# Request schemas


class BuildIndexRequest(BaseModel):
    """Request to build clustering index for a persona."""

    dbscan_eps: float = Field(default=10.0, description="DBSCAN epsilon (distance threshold)")
    dbscan_min_samples: int = Field(default=3, description="DBSCAN minimum samples per cluster")
    tsne_perplexity: float = Field(default=30.0, description="t-SNE perplexity parameter")


class OptimizeRequest(BaseModel):
    """Request to auto-optimize clustering parameters."""

    guideline: Optional[str] = Field(default=None, description="Natural language guideline for clustering (e.g., 'Group by intent', 'Organize by project')")


# Response schemas


class PersonaInfo(BaseModel):
    """Basic persona information with indexing status."""

    persona_id: int
    persona_name: str
    total_emails: int
    status: str  # 'indexing', 'completed', 'failed', 'not_indexed'
    indexed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class IndexingStatusResponse(BaseModel):
    """Current status of an indexing operation."""

    persona_id: int
    status: str
    current_step: str
    progress_percent: float
    total_emails: int
    processed_emails: int = 0
    error_message: Optional[str] = None


class ClusterInfo(BaseModel):
    """Cluster metadata for visualization."""

    cluster_id: int
    cluster_label: int
    short_label: Optional[str]
    description: Optional[str]
    num_emails: int
    centroid: list[float]  # [x, y, z]
    color: Optional[str] = None  # Hex color for visualization


class PointInfo(BaseModel):
    """3D point representing an email."""

    email_id: int
    x: float
    y: float
    z: float
    cluster_label: int
    subject: str
    sender: str


class StatisticsInfo(BaseModel):
    """Clustering statistics."""

    total_emails: int
    num_clusters: int
    noise_points: int
    avg_cluster_size: float


class VisualizationDataResponse(BaseModel):
    """Complete visualization data for a persona."""

    persona_id: int
    persona_name: str
    points: list[PointInfo]
    clusters: list[ClusterInfo]
    statistics: StatisticsInfo
    indexed_at: datetime


class EmailDetailResponse(BaseModel):
    """Detailed email information for modal display."""

    email_id: int
    sender: str
    recipients_to: list[str]
    recipients_cc: list[str] = Field(default_factory=list)
    recipients_bcc: list[str] = Field(default_factory=list)
    subject: str
    body: str
    sent_at: datetime
    thread_id: Optional[str] = None
    cluster_label: Optional[int] = None
    cluster_name: Optional[str] = None


class ClusterDetailResponse(BaseModel):
    """Detailed information about a specific cluster."""

    cluster_id: int
    cluster_label: int
    short_label: Optional[str]
    description: Optional[str]
    num_emails: int
    centroid: list[float]
    sample_emails: list[dict]  # Sample emails for preview


class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    detail: Optional[str] = None


class SuccessResponse(BaseModel):
    """Generic success response."""

    success: bool
    message: str
