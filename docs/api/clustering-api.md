# Clustering Server API Reference

**Service:** VDOS Clustering Server  
**Base URL:** `http://127.0.0.1:8016`  
**Content-Type:** `application/json`

The Clustering Server provides email clustering and visualization APIs for each persona. It reads email data from the main `vdos.db` database and writes clustering metadata to its own `email_clusters.db` file.

---

## Overview

### Core Capabilities

- Build an embedding + clustering index for a persona's emails
- Retrieve high-level status for all personas
- Fetch 3D visualization data for rendering cluster scatter plots
- Drill into individual emails and cluster summaries
- Optimize clustering parameters for better separation

### Data Sources

- **Input:** `emails` and `email_recipients` tables in `vdos.db`
- **Output:** clustering tables managed by `virtualoffice.clustering.db` (e.g. `clusters`, `email_positions`)

---

## Persona Management

### List Personas

```http
GET /clustering/personas
```

Returns all personas from `vdos.db` with their clustering index status.

**Response Model:** `PersonaInfo[]`

```json
[
  {
    "persona_id": 1,
    "persona_name": "김유진",
    "total_emails": 145,
    "status": "indexed",
    "indexed_at": "2025-11-18T10:15:23",
    "error_message": null
  },
  {
    "persona_id": 2,
    "persona_name": "박민우",
    "total_emails": 0,
    "status": "not_indexed",
    "indexed_at": null,
    "error_message": null
  }
]
```

---

## Index Management

### Build Index for Persona

```http
POST /clustering/index/{persona_id}
Content-Type: application/json
```

**Request Body:** `BuildIndexRequest`

```json
{
  "embedding_model": "text-embedding-3-small",
  "tsne_perplexity": 30.0,
  "tsne_n_iter": 1000,
  "dbscan_eps": 10.0,
  "dbscan_min_samples": 3
}
```

All fields are optional; sensible defaults are used when omitted.

**Behavior:**
- Starts an asynchronous background task that runs the full pipeline:
  1. Load persona emails from `vdos.db`
  2. Generate embeddings via OpenAI
  3. Run t-SNE (3D)
  4. Run DBSCAN
  5. Sample representative emails per cluster
  6. Generate GPT labels for each cluster
- Tracks progress in `_indexing_status` and the clustering DB.

**Response Model:** `SuccessResponse`

```json
{
  "success": true,
  "message": "Indexing started for persona 1"
}
```

### Get Indexing Status

```http
GET /clustering/{persona_id}/status
```

Returns an `IndexingStatusResponse` for the persona.

```json
{
  "persona_id": 1,
  "status": "completed",
  "progress": 100.0,
  "message": "Indexing completed successfully",
  "started_at": "2025-11-18T10:10:00",
  "finished_at": "2025-11-18T10:15:23",
  "total_emails": 145,
  "cluster_count": 8,
  "error_message": null
}
```

### Clear Persona Index

```http
DELETE /clustering/{persona_id}/index
```

Deletes clustering data and FAISS index for the persona.

**Response Model:** `SuccessResponse`

---

## Visualization Data

### Get 3D Visualization Data

```http
GET /clustering/{persona_id}/data
```

Returns 3D coordinates and cluster metadata for plotting.

**Response Model:** `VisualizationDataResponse`

```json
{
  "persona_id": 1,
  "points": [
    {
      "email_id": 101,
      "x": 12.3,
      "y": 45.6,
      "z": 78.9,
      "cluster_id": 3,
      "cluster_label": "프로젝트 킥오프 및 일정 조율",
      "color": "#1f78b4"
    }
  ],
  "clusters": [
    {
      "cluster_id": 3,
      "cluster_label": "프로젝트 킥오프 및 일정 조율",
      "short_label": "킥오프/일정",
      "size": 24
    }
  ],
  "statistics": {
    "total_emails": 145,
    "cluster_count": 8,
    "noise_count": 5
  }
}
```

---

## Email and Cluster Details

### Get Email Details

```http
GET /clustering/{persona_id}/email/{email_id}
```

Returns detailed information for a single email.

**Response Model:** `EmailDetailResponse`

```json
{
  "email_id": 101,
  "sender": "dev.1@blogsim.dev",
  "recipients_to": ["designer.1@blogsim.dev"],
  "recipients_cc": [],
  "recipients_bcc": [],
  "subject": "Authentication module ready for review",
  "body": "...",
  "sent_at": "2025-10-18T04:30:15.123456",
  "thread_id": "auth-thread-1",
  "cluster_label": "프로젝트 인증 기능",
  "cluster_name": "인증/보안"
}
```

### Get Cluster Details

```http
GET /clustering/{persona_id}/cluster/{cluster_id}
```

Returns metadata and sample emails for a cluster.

**Response Model:** `ClusterDetailResponse`

```json
{
  "cluster_id": 3,
  "cluster_label": "프로젝트 킥오프 및 일정 조율",
  "short_label": "킥오프/일정",
  "description": "킥오프 미팅, 일정 협의, 마일스톤 관련 이메일 묶음",
  "num_emails": 24,
  "centroid": [10.2, 35.4, 72.1],
  "sample_emails": [
    {
      "email_id": 101,
      "subject": "프로젝트 킥오프 미팅 일정 조율",
      "body": "..."
    }
  ]
}
```

---

## Optimization

### Optimize Clustering Parameters

```http
POST /clustering/optimize
Content-Type: application/json
```

**Request Body:** `OptimizeRequest`

```json
{
  "persona_id": 1,
  "min_clusters": 5,
  "max_clusters": 12,
  "target_avg_cluster_size": 20
}
```

Runs a parameter search (e.g. varying `dbscan_eps`) and returns suggested parameters for building a better index. Use the returned values when calling `POST /clustering/index/{persona_id}`.

---

## Health Check

```http
GET /
```

Returns a simple JSON payload confirming the service is running:

```json
{
  "status": "ok",
  "service": "VDOS Clustering Server",
  "version": "0.1.0"
}
```

