"""
GPT-powered cluster labeling.

Uses GPT to analyze sample emails from each cluster and generate:
- Short label (2-4 words)
- Descriptive sentence

This helps users understand what each cluster represents.
"""

import json
import logging
from typing import Optional

from virtualoffice.clustering.models import ClusterSample, ClusterLabel
from virtualoffice.utils.completion_util import generate_text

logger = logging.getLogger(__name__)


def generate_cluster_label(
    cluster_label_num: int, samples: list[ClusterSample], max_samples: int = 5
) -> ClusterLabel:
    """
    Generate a descriptive label for a cluster based on sample emails.

    Args:
        cluster_label_num: The numeric cluster label (-1 for noise)
        samples: Sample emails from the cluster
        max_samples: Maximum number of samples to include in prompt

    Returns:
        ClusterLabel with short_label and description

    Raises:
        ValueError: If samples list is empty
        Exception: If GPT API call fails
    """
    if not samples:
        raise ValueError("Cannot generate label for empty sample list")

    # Special handling for noise cluster
    if cluster_label_num == -1:
        return ClusterLabel(
            cluster_id=0,  # Will be set by caller
            cluster_label=-1,
            short_label="Noise / Unclustered",
            description="Emails that don't fit into any specific cluster pattern",
            num_emails=len(samples),
            sample_count=len(samples),
        )

    # Limit samples
    samples_to_use = samples[:max_samples]

    # Build prompt
    prompt = _build_labeling_prompt(cluster_label_num, samples_to_use)

    try:
        # Use GPT-4o-mini for cost efficiency
        response_text, tokens = generate_text(
            prompt=[{"role": "user", "content": prompt}],
            model="gpt-4o-mini",
            temperature=0.3,  # Lower temperature for more consistent labeling
        )

        # Parse JSON response
        label_data = _parse_label_response(response_text)

        logger.info(
            f"Generated label for cluster {cluster_label_num}: "
            f"'{label_data['short_label']}' (used {tokens} tokens)"
        )

        return ClusterLabel(
            cluster_id=0,  # Will be set by caller
            cluster_label=cluster_label_num,
            short_label=label_data["short_label"],
            description=label_data["description"],
            num_emails=len(samples),
            sample_count=len(samples_to_use),
        )

    except Exception as e:
        logger.error(f"Failed to generate label for cluster {cluster_label_num}: {e}")
        # Return a fallback label
        return ClusterLabel(
            cluster_id=0,
            cluster_label=cluster_label_num,
            short_label=f"Cluster {cluster_label_num}",
            description="Label generation failed - manual review needed",
            num_emails=len(samples),
            sample_count=len(samples_to_use),
        )


def _build_labeling_prompt(cluster_num: int, samples: list[ClusterSample]) -> str:
    """Build the GPT prompt for cluster labeling."""
    samples_text = []
    for i, sample in enumerate(samples, 1):
        # Truncate body to 500 chars
        body_preview = sample.truncated_body
        samples_text.append(f"Email {i}:\nSubject: {sample.subject}\nBody: {body_preview}\n")

    samples_str = "\n---\n".join(samples_text)

    prompt = f"""You are analyzing a cluster of similar emails to understand their common purpose or theme.

Here are {len(samples)} representative emails from Cluster {cluster_num}:

{samples_str}

Based on these samples, generate a label for this cluster.

Provide your response as a JSON object with exactly two fields:
1. "short_label": A concise label (2-4 words) that captures the main theme
2. "description": A clear one-sentence description of what these emails are about

Examples of good labels:
- short_label: "Project Status Updates", description: "Regular updates on project progress and milestones"
- short_label: "Meeting Requests", description: "Emails scheduling or requesting meetings with team members"
- short_label: "Bug Reports", description: "Technical issues and bug reports from users or team members"

Your response (valid JSON only):"""

    return prompt


def _parse_label_response(response_text: str) -> dict:
    """
    Parse GPT response to extract label data.

    Args:
        response_text: Raw GPT response

    Returns:
        Dict with 'short_label' and 'description'

    Raises:
        ValueError: If response cannot be parsed
    """
    try:
        # Try to parse as JSON
        data = json.loads(response_text.strip())

        if "short_label" not in data or "description" not in data:
            raise ValueError("Missing required fields in JSON response")

        # Validate and clean
        short_label = str(data["short_label"]).strip()
        description = str(data["description"]).strip()

        if not short_label or not description:
            raise ValueError("Empty label or description")

        # Enforce length limits
        if len(short_label) > 50:
            short_label = short_label[:47] + "..."

        if len(description) > 200:
            description = description[:197] + "..."

        return {"short_label": short_label, "description": description}

    except json.JSONDecodeError:
        # Try to extract from markdown code block
        if "```json" in response_text:
            try:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                json_text = response_text[json_start:json_end].strip()
                return _parse_label_response(json_text)
            except:
                pass

        # If all parsing fails, raise error
        raise ValueError(f"Could not parse label response: {response_text[:100]}")


def generate_labels_for_clusters(
    cluster_samples_map: dict[int, list[ClusterSample]]
) -> dict[int, ClusterLabel]:
    """
    Generate labels for multiple clusters in batch.

    Args:
        cluster_samples_map: Map of cluster_label -> list of samples

    Returns:
        Map of cluster_label -> ClusterLabel
    """
    labels = {}

    for cluster_num, samples in cluster_samples_map.items():
        try:
            label = generate_cluster_label(cluster_num, samples)
            labels[cluster_num] = label
        except Exception as e:
            logger.error(f"Failed to generate label for cluster {cluster_num}: {e}")
            # Add fallback label
            labels[cluster_num] = ClusterLabel(
                cluster_id=0,
                cluster_label=cluster_num,
                short_label=f"Cluster {cluster_num}",
                description="Label generation failed",
                num_emails=len(samples),
                sample_count=0,
            )

    logger.info(f"Generated labels for {len(labels)} clusters")
    return labels
