"""
Clustering Server - FastAPI application for email clustering operations.

Endpoints:
- POST /clustering/index/{persona_id} - Build index for persona
- GET /clustering/personas - List all personas with status
- GET /clustering/{persona_id}/data - Get visualization data
- GET /clustering/{persona_id}/email/{email_id} - Get email details
- GET /clustering/{persona_id}/cluster/{cluster_id} - Get cluster details
- GET /clustering/{persona_id}/status - Get indexing status
- DELETE /clustering/{persona_id}/index - Clear index
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware

from virtualoffice.common.db import get_connection as get_vdos_connection
from virtualoffice.clustering import db
from virtualoffice.clustering.cluster_engine import ClusterEngine
from virtualoffice.clustering.faiss_store import delete_store_for_persona
from virtualoffice.servers.clustering.schemas import (
    BuildIndexRequest,
    ClusterDetailResponse,
    ClusterInfo,
    EmailDetailResponse,
    ErrorResponse,
    IndexingStatusResponse,
    OptimizeRequest,
    PersonaInfo,
    PointInfo,
    StatisticsInfo,
    SuccessResponse,
    VisualizationDataResponse,
)

app = FastAPI(title="VDOS Clustering Server", version="0.1.0")

# Enable CORS for web dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)

# Track ongoing indexing operations
_indexing_status: dict[int, IndexingStatusResponse] = {}


@app.on_event("startup")
def initialize() -> None:
    """Initialize database on startup."""
    db.init_database()
    logger.info("Clustering server initialized")


@app.get("/")
def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "VDOS Clustering Server", "version": "0.1.0"}


# ============================================================================
# Persona Management
# ============================================================================


@app.get("/clustering/personas", response_model=list[PersonaInfo])
def list_personas():
    """
    List all personas with their indexing status.

    Returns personas from vdos.db with their clustering index status.
    """
    try:
        # Get all personas from vdos.db
        with get_vdos_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, name, email_address FROM people ORDER BY name
            """
            )
            personas = cursor.fetchall()

        # Get indexing statuses
        index_statuses = {s.persona_id: s for s in db.get_all_persona_index_statuses()}

        # Build response
        result = []
        for persona_id, persona_name, email_address in personas:
            if persona_id in index_statuses:
                s = index_statuses[persona_id]
                result.append(
                    PersonaInfo(
                        persona_id=persona_id,
                        persona_name=persona_name,
                        total_emails=s.total_emails,
                        status=s.status,
                        indexed_at=s.indexed_at,
                        error_message=s.error_message,
                    )
                )
            else:
                # Count emails for this persona
                with get_vdos_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM emails WHERE sender = ?", (email_address,))
                    email_count = cursor.fetchone()[0]

                result.append(
                    PersonaInfo(
                        persona_id=persona_id,
                        persona_name=persona_name,
                        total_emails=email_count,
                        status="not_indexed",
                        indexed_at=None,
                    )
                )

        return result

    except Exception as e:
        logger.error(f"Failed to list personas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Indexing Operations
# ============================================================================


def _progress_callback(persona_id: int, step: str, percent: float):
    """Update indexing progress."""
    if persona_id in _indexing_status:
        _indexing_status[persona_id].current_step = step
        _indexing_status[persona_id].progress_percent = percent


async def _build_index_background(persona_id: int, dbscan_eps: float = 2.0,
                                   dbscan_min_samples: int = 3, tsne_perplexity: float = 30.0):
    """Background task to build index."""
    try:
        # Initialize status
        _indexing_status[persona_id] = IndexingStatusResponse(
            persona_id=persona_id,
            status="indexing",
            current_step="Initializing",
            progress_percent=0.0,
            total_emails=0,
        )

        # Create engine with custom parameters
        engine = ClusterEngine(
            dbscan_eps=dbscan_eps,
            dbscan_min_samples=dbscan_min_samples,
            tsne_perplexity=tsne_perplexity
        )

        # Run in executor to avoid blocking async loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, engine.build_index, persona_id, lambda s, p: _progress_callback(persona_id, s, p)
        )

        # Update final status
        _indexing_status[persona_id].status = "completed"
        _indexing_status[persona_id].current_step = "Completed"
        _indexing_status[persona_id].progress_percent = 100.0
        _indexing_status[persona_id].total_emails = result.total_emails

        logger.info(f"Successfully built index for persona {persona_id}")

    except Exception as e:
        logger.error(f"Failed to build index for persona {persona_id}: {e}")
        if persona_id in _indexing_status:
            _indexing_status[persona_id].status = "failed"
            _indexing_status[persona_id].error_message = str(e)


@app.post("/clustering/index/{persona_id}", response_model=SuccessResponse)
async def build_index(persona_id: int, background_tasks: BackgroundTasks,
                      params: BuildIndexRequest = BuildIndexRequest()):
    """
    Build clustering index for a persona.

    This is an async operation that runs in the background.
    Use GET /clustering/{persona_id}/status to poll for progress.
    """
    try:
        # Check if already indexing
        if persona_id in _indexing_status and _indexing_status[persona_id].status == "indexing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Indexing already in progress for persona {persona_id}",
            )

        # Check if persona exists
        with get_vdos_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM people WHERE id = ?", (persona_id,))
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=f"Persona {persona_id} not found"
                )

        # Delete existing index if present (to avoid foreign key conflicts when re-indexing)
        try:
            db.delete_persona_index(persona_id)
            delete_store_for_persona(persona_id)
            logger.info(f"Cleared existing index for persona {persona_id} before re-indexing")
        except Exception as e:
            logger.warning(f"Could not clear existing index for persona {persona_id}: {e}")

        # Start background task with parameters
        background_tasks.add_task(
            _build_index_background,
            persona_id,
            params.dbscan_eps,
            params.dbscan_min_samples,
            params.tsne_perplexity
        )

        return SuccessResponse(
            success=True, message=f"Indexing started for persona {persona_id}. Check /clustering/{persona_id}/status for progress."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start indexing for persona {persona_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clustering/optimize/{persona_id}", response_model=SuccessResponse)
async def optimize_clustering_parameters(
    persona_id: int,
    background_tasks: BackgroundTasks,
    params: OptimizeRequest = OptimizeRequest()
):
    """
    Auto-optimize clustering parameters for a persona using GPT evaluation.

    Tests multiple parameter configurations and uses GPT to evaluate which
    clustering produces the most coherent, meaningful clusters.

    Optionally provide a natural language guideline for clustering.
    """
    from virtualoffice.clustering.auto_optimizer import optimize_parameters

    try:
        # Check if already optimizing
        if persona_id in _indexing_status and _indexing_status[persona_id].status == "indexing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Operation already in progress for persona {persona_id}",
            )

        # Check if persona exists
        with get_vdos_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM people WHERE id = ?", (persona_id,))
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=f"Persona {persona_id} not found"
                )

        # Delete existing index
        try:
            db.delete_persona_index(persona_id)
            delete_store_for_persona(persona_id)
        except Exception as e:
            logger.warning(f"Could not clear existing index for persona {persona_id}: {e}")

        guideline = params.guideline

        # Start optimization in background
        async def _optimize_background():
            try:
                step_text = "Starting parameter optimization"
                if guideline:
                    step_text = f"Starting parameter optimization (Goal: {guideline})"

                _indexing_status[persona_id] = IndexingStatusResponse(
                    persona_id=persona_id,
                    status="indexing",
                    current_step=step_text,
                    progress_percent=0.0,
                    total_emails=0,
                )

                def progress_callback(step, percent, config):
                    if persona_id in _indexing_status:
                        _indexing_status[persona_id].current_step = f"{step} ({config})"
                        _indexing_status[persona_id].progress_percent = percent

                # Run optimization with guideline
                loop = asyncio.get_event_loop()
                best_config, best_quality = await loop.run_in_executor(
                    None, optimize_parameters, persona_id, progress_callback, guideline
                )

                # Update status with total emails from result
                _indexing_status[persona_id].status = "completed"
                _indexing_status[persona_id].current_step = (
                    f"Optimization complete! Best: {best_config} (score: {best_quality.overall_score:.1f}/10)"
                )
                _indexing_status[persona_id].progress_percent = 100.0
                _indexing_status[persona_id].total_emails = best_quality.total_emails

                logger.info(f"Optimization complete for persona {persona_id}: {best_config}")

            except Exception as e:
                logger.error(f"Failed to optimize persona {persona_id}: {e}")
                if persona_id in _indexing_status:
                    _indexing_status[persona_id].status = "failed"
                    _indexing_status[persona_id].error_message = str(e)

        background_tasks.add_task(_optimize_background)

        return SuccessResponse(
            success=True,
            message=f"Parameter optimization started for persona {persona_id}. This may take several minutes. Check /clustering/{persona_id}/status for progress."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start optimization for persona {persona_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/clustering/{persona_id}/status", response_model=IndexingStatusResponse)
def get_indexing_status(persona_id: int):
    """Get current indexing status for a persona."""
    # Check ongoing operation
    if persona_id in _indexing_status:
        return _indexing_status[persona_id]

    # Check database status
    status_obj = db.get_persona_index_status(persona_id)
    if status_obj:
        return IndexingStatusResponse(
            persona_id=persona_id,
            status=status_obj.status,
            current_step="Completed" if status_obj.status == "completed" else "Unknown",
            progress_percent=100.0 if status_obj.status == "completed" else 0.0,
            total_emails=status_obj.total_emails,
            error_message=status_obj.error_message,
        )

    # Not indexed
    return IndexingStatusResponse(
        persona_id=persona_id,
        status="not_indexed",
        current_step="Not started",
        progress_percent=0.0,
        total_emails=0,
    )


@app.delete("/clustering/{persona_id}/index", response_model=SuccessResponse)
def clear_index(persona_id: int):
    """
    Clear clustering index for a persona.

    This removes all clustering data and FAISS index, allowing re-indexing.
    """
    try:
        # Check if currently indexing
        if persona_id in _indexing_status and _indexing_status[persona_id].status == "indexing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete index while indexing is in progress",
            )

        # Delete from database
        db.delete_persona_index(persona_id)

        # Delete FAISS store
        delete_store_for_persona(persona_id)

        # Clear from status cache
        if persona_id in _indexing_status:
            del _indexing_status[persona_id]

        logger.info(f"Cleared index for persona {persona_id}")

        return SuccessResponse(success=True, message=f"Index cleared for persona {persona_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear index for persona {persona_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Visualization Data
# ============================================================================


@app.get("/clustering/{persona_id}/data", response_model=VisualizationDataResponse)
def get_visualization_data(persona_id: int):
    """
    Get complete visualization data for a persona.

    Returns points, clusters, and statistics for rendering the 3D plot.
    """
    try:
        # Check if indexed
        status_obj = db.get_persona_index_status(persona_id)
        if not status_obj or status_obj.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No completed index found for persona {persona_id}",
            )

        # Get clusters
        clusters = db.get_clusters_for_persona(persona_id)

        # Get statistics
        stats = db.get_clustering_statistics(persona_id)

        # Get points - we need to query both clustering db and vdos db
        # For now, we'll get basic point data
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT ep.email_id, ep.x, ep.y, ep.z, c.cluster_label
                FROM email_positions ep
                LEFT JOIN clusters c ON ep.cluster_id = c.id
                WHERE ep.persona_id = ?
            """,
                (persona_id,),
            )
            point_rows = cursor.fetchall()

        # Get email subjects and senders from vdos.db
        email_ids = [row[0] for row in point_rows]
        email_data = {}
        if email_ids:
            with get_vdos_connection() as conn:
                cursor = conn.cursor()
                placeholders = ",".join("?" * len(email_ids))
                cursor.execute(
                    f"""
                    SELECT id, subject, sender FROM emails
                    WHERE id IN ({placeholders})
                """,
                    email_ids,
                )
                for email_id, subject, sender in cursor.fetchall():
                    email_data[email_id] = (subject, sender)

        # Build points
        points = []
        for email_id, x, y, z, cluster_label in point_rows:
            subject, sender = email_data.get(email_id, ("", ""))
            points.append(
                PointInfo(
                    email_id=email_id,
                    x=x,
                    y=y,
                    z=z,
                    cluster_label=cluster_label if cluster_label is not None else -1,
                    subject=subject,
                    sender=sender,
                )
            )

        # Assign colors to clusters (using a simple color palette)
        colors = _generate_cluster_colors(len(clusters))
        cluster_infos = []
        for i, cluster in enumerate(clusters):
            cluster_infos.append(
                ClusterInfo(
                    cluster_id=cluster.cluster_id,
                    cluster_label=cluster.cluster_label,
                    short_label=cluster.short_label,
                    description=cluster.description,
                    num_emails=cluster.num_emails,
                    centroid=[cluster.centroid_x or 0, cluster.centroid_y or 0, cluster.centroid_z or 0],
                    color=colors[i % len(colors)],
                )
            )

        return VisualizationDataResponse(
            persona_id=persona_id,
            persona_name=status_obj.persona_name,
            points=points,
            clusters=cluster_infos,
            statistics=StatisticsInfo(**stats),
            indexed_at=status_obj.indexed_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get visualization data for persona {persona_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _generate_cluster_colors(n: int) -> list[str]:
    """Generate distinct colors for clusters."""
    # Use a predefined color palette (ColorBrewer Set3)
    palette = [
        "#8dd3c7",
        "#ffffb3",
        "#bebada",
        "#fb8072",
        "#80b1d3",
        "#fdb462",
        "#b3de69",
        "#fccde5",
        "#d9d9d9",
        "#bc80bd",
        "#ccebc5",
        "#ffed6f",
    ]
    # Repeat palette if needed
    return [palette[i % len(palette)] for i in range(n)]


# ============================================================================
# Email and Cluster Details
# ============================================================================


@app.get("/clustering/{persona_id}/email/{email_id}", response_model=EmailDetailResponse)
def get_email_details(persona_id: int, email_id: int):
    """Get detailed email information for modal display."""
    try:
        # Get email from vdos.db
        with get_vdos_connection() as conn:
            cursor = conn.cursor()

            # Get email
            cursor.execute(
                """
                SELECT id, sender, subject, body, sent_at, thread_id
                FROM emails
                WHERE id = ?
            """,
                (email_id,),
            )
            email_row = cursor.fetchone()

            if not email_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=f"Email {email_id} not found"
                )

            # Get recipients
            cursor.execute(
                """
                SELECT address, kind FROM email_recipients
                WHERE email_id = ?
            """,
                (email_id,),
            )
            recipients_rows = cursor.fetchall()

        recipients_to = [addr for addr, kind in recipients_rows if kind == "to"]
        recipients_cc = [addr for addr, kind in recipients_rows if kind == "cc"]
        recipients_bcc = [addr for addr, kind in recipients_rows if kind == "bcc"]

        # Get cluster info if available
        cluster_label = None
        cluster_name = None
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT c.cluster_label, c.short_label
                FROM email_positions ep
                JOIN clusters c ON ep.cluster_id = c.id
                WHERE ep.email_id = ? AND ep.persona_id = ?
            """,
                (email_id, persona_id),
            )
            cluster_row = cursor.fetchone()
            if cluster_row:
                cluster_label, cluster_name = cluster_row

        return EmailDetailResponse(
            email_id=email_row[0],
            sender=email_row[1],
            recipients_to=recipients_to,
            recipients_cc=recipients_cc,
            recipients_bcc=recipients_bcc,
            subject=email_row[2],
            body=email_row[3],
            sent_at=datetime.fromisoformat(email_row[4]),
            thread_id=email_row[5],
            cluster_label=cluster_label,
            cluster_name=cluster_name,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get email details for email {email_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/clustering/{persona_id}/cluster/{cluster_id}", response_model=ClusterDetailResponse)
def get_cluster_details(persona_id: int, cluster_id: int):
    """Get detailed information about a specific cluster."""
    try:
        # Get cluster metadata
        cluster = db.get_cluster_by_id(cluster_id)
        if not cluster or cluster.persona_id != persona_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Cluster {cluster_id} not found"
            )

        # Get sample emails
        samples = db.get_cluster_samples(cluster_id)
        sample_dicts = [
            {"email_id": s.email_id, "subject": s.subject, "body": s.truncated_body}
            for s in samples
        ]

        return ClusterDetailResponse(
            cluster_id=cluster.cluster_id,
            cluster_label=cluster.cluster_label,
            short_label=cluster.short_label,
            description=cluster.description,
            num_emails=cluster.num_emails,
            centroid=[cluster.centroid_x or 0, cluster.centroid_y or 0, cluster.centroid_z or 0],
            sample_emails=sample_dicts,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cluster details for cluster {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8016)
