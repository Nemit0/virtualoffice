"""
ProjectManager module for Virtual Department Operations Simulator.

This module handles project plan management, team assignments, multi-project
coordination, and project chat room lifecycle.

Extracted from SimulationEngine as part of the engine refactoring project.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from virtualoffice.common.db import get_connection
from virtualoffice.sim_manager.schemas import PersonRead
from virtualoffice.sim_manager.gateways import ChatGateway
from virtualoffice.sim_manager.planner import PlanResult

logger = logging.getLogger(__name__)


class ProjectManager:
    """
    Manages project plans, assignments, and multi-project coordination.

    Responsibilities:
    - Project plan storage and retrieval
    - Active project queries with timeline awareness
    - Project-person assignment management
    - Multi-project scenario support
    - Project chat room lifecycle management
    - Project completion detection
    """

    def __init__(self):
        """Initialize the ProjectManager."""
        self._project_plan_cache: dict[str, Any] | None = None

    def get_project_plan(self, project_id: int | None = None) -> dict[str, Any] | None:
        """
        Get a project plan by ID, or the most recent plan if no ID provided.

        Args:
            project_id: Optional project ID. If None, returns most recent plan.

        Returns:
            Project plan dictionary or None if not found.
        """
        # Check cache for most recent plan (when project_id is None)
        if project_id is None and self._project_plan_cache is not None:
            return self._project_plan_cache.copy()

        with get_connection() as conn:
            if project_id is not None:
                row = conn.execute("SELECT * FROM project_plans WHERE id = ?", (project_id,)).fetchone()
            else:
                row = conn.execute("SELECT * FROM project_plans ORDER BY id DESC LIMIT 1").fetchone()

        if not row:
            return None

        plan = self._row_to_project_plan(row)

        # Cache if this is the most recent plan
        if project_id is None:
            self._project_plan_cache = plan

        return plan

    def get_active_projects_for_person(self, person_id: int, week: int) -> list[dict[str, Any]]:
        """
        Get ALL active projects for a person at a given week.

        Args:
            person_id: ID of the person
            week: Week number (1-indexed)

        Returns:
            List of project plan dictionaries
        """
        with get_connection() as conn:
            # Get assigned projects
            rows = conn.execute(
                """
                SELECT pp.* FROM project_plans pp
                INNER JOIN project_assignments pa ON pp.id = pa.project_id
                WHERE pa.person_id = ? AND pp.start_week <= ? AND (pp.start_week + pp.duration_weeks - 1) >= ?
                ORDER BY pp.start_week ASC
                """,
                (person_id, week, week),
            ).fetchall()

            assigned_ids = {row["id"] for row in rows}

            # Get projects without assignments (everyone works on them)
            unassigned_rows = conn.execute(
                """
                SELECT pp.* FROM project_plans pp
                WHERE pp.id NOT IN (SELECT DISTINCT project_id FROM project_assignments)
                AND pp.start_week <= ? AND (pp.start_week + pp.duration_weeks - 1) >= ?
                ORDER BY pp.start_week ASC
                """,
                (week, week),
            ).fetchall()

            all_rows = list(rows) + [r for r in unassigned_rows if r["id"] not in assigned_ids]
            return [self._row_to_project_plan(row) for row in all_rows]

    def get_active_project_for_person(self, person_id: int, week: int) -> dict[str, Any] | None:
        """
        Get the first active project for a person at a given week.

        This is a convenience method that returns the first project from
        get_active_projects_for_person(), maintaining backward compatibility.

        Args:
            person_id: ID of the person
            week: Week number (1-indexed)

        Returns:
            First active project plan dictionary or None if no active projects
        """
        projects = self.get_active_projects_for_person(person_id, week)
        return projects[0] if projects else None

    def get_active_projects_with_assignments(self, week: int) -> list[dict[str, Any]]:
        """
        Get all projects active at the given week with their team assignments.

        Args:
            week: Week number (1-indexed)

        Returns:
            List of dictionaries with 'project' and 'team_members' keys
        """
        with get_connection() as conn:
            # Get all projects active in the current week
            project_rows = conn.execute(
                """
                SELECT * FROM project_plans
                WHERE start_week <= ? AND (start_week + duration_weeks - 1) >= ?
                ORDER BY start_week ASC
                """,
                (week, week),
            ).fetchall()

            result = []
            for proj_row in project_rows:
                project = self._row_to_project_plan(proj_row)

                # Get assigned people for this project
                assignment_rows = conn.execute(
                    """
                    SELECT p.id, p.name, p.role, p.team_name
                    FROM people p
                    INNER JOIN project_assignments pa ON p.id = pa.person_id
                    WHERE pa.project_id = ?
                    ORDER BY p.team_name, p.name
                    """,
                    (project["id"],),
                ).fetchall()

                team_members = [
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "role": row["role"],
                        "team_name": row["team_name"],
                    }
                    for row in assignment_rows
                ]

                # If no specific assignments, project is for everyone
                if not team_members:
                    all_people_rows = conn.execute(
                        "SELECT id, name, role, team_name FROM people ORDER BY team_name, name"
                    ).fetchall()
                    team_members = [
                        {
                            "id": row["id"],
                            "name": row["name"],
                            "role": row["role"],
                            "team_name": row["team_name"],
                        }
                        for row in all_people_rows
                    ]

                result.append(
                    {
                        "project": project,
                        "team_members": team_members,
                    }
                )

            return result

    def store_project_plan(
        self,
        project_name: str,
        project_summary: str,
        plan_result: PlanResult,
        generated_by: int | None,
        duration_weeks: int,
        start_week: int = 1,
        assigned_person_ids: Sequence[int] | None = None,
    ) -> dict[str, Any]:
        """
        Store a new project plan in the database.

        Args:
            project_name: Name of the project
            project_summary: Brief summary of the project
            plan_result: PlanResult containing the plan content and metadata
            generated_by: ID of the person who generated the plan (or None)
            duration_weeks: Duration of the project in weeks
            start_week: Week when the project starts (default: 1)
            assigned_person_ids: Optional list of person IDs assigned to this project

        Returns:
            Stored project plan dictionary
        """
        with get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO project_plans(
                    project_name, project_summary, plan, generated_by,
                    duration_weeks, start_week, model_used, tokens_used
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project_name,
                    project_summary,
                    plan_result.content,
                    generated_by,
                    duration_weeks,
                    start_week,
                    plan_result.model_used,
                    plan_result.tokens_used,
                ),
            )
            project_id = cursor.lastrowid

            # Store project assignments if provided
            if assigned_person_ids:
                for person_id in assigned_person_ids:
                    conn.execute(
                        "INSERT OR IGNORE INTO project_assignments(project_id, person_id) VALUES (?, ?)",
                        (project_id, person_id),
                    )

            row = conn.execute("SELECT * FROM project_plans WHERE id = ?", (project_id,)).fetchone()

        plan = self._row_to_project_plan(row)
        self._project_plan_cache = plan
        return plan

    def create_project_chat_room(
        self, project_id: int, project_name: str, team_members: list[PersonRead], chat_gateway: ChatGateway
    ) -> str:
        """
        Create a group chat room for a project and return the room slug.

        Args:
            project_id: ID of the project
            project_name: Name of the project
            team_members: List of PersonRead objects for team members
            chat_gateway: ChatGateway instance for creating the room

        Returns:
            Room slug for the created chat room
        """
        room_name = f"{project_name} Team"
        room_slug = f"project-{project_id}-{project_name.lower().replace(' ', '-')}"

        # Get chat handles for all team members
        participant_handles = [member.chat_handle for member in team_members]

        # Create the room via chat gateway
        _ = chat_gateway.create_room(name=room_name, participants=participant_handles, slug=room_slug)

        # Store project-room mapping in database
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO project_chat_rooms (project_id, room_slug, room_name, is_active)
                VALUES (?, ?, ?, 1)
                """,
                (project_id, room_slug, room_name),
            )

        logger.info(f"Created project chat room '{room_slug}' for project {project_id}")
        return room_slug

    def get_active_project_chat_room(self, project_id: int) -> str | None:
        """
        Get the active chat room slug for a project, if any.

        Args:
            project_id: ID of the project

        Returns:
            Room slug or None if no active room exists
        """
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT room_slug FROM project_chat_rooms
                WHERE project_id = ? AND is_active = 1
                ORDER BY created_at DESC LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            return row["room_slug"] if row else None

    def archive_project_chat_room(self, project_id: int) -> bool:
        """
        Archive the chat room for a completed project.

        Args:
            project_id: ID of the project

        Returns:
            True if a room was archived, False otherwise
        """
        with get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE project_chat_rooms
                SET is_active = 0, archived_at = CURRENT_TIMESTAMP
                WHERE project_id = ? AND is_active = 1
                """,
                (project_id,),
            )
            archived = cursor.rowcount > 0

        if archived:
            logger.info(f"Archived project chat room for project {project_id}")

        return archived

    def is_project_complete(self, project_id: int, current_week: int) -> bool:
        """
        Check if a project is complete based on its timeline.

        Args:
            project_id: ID of the project
            current_week: Current week number (1-indexed)

        Returns:
            True if the project's end week is before the current week
        """
        project = self.get_project_plan(project_id)
        if not project:
            return False

        end_week = project["start_week"] + project["duration_weeks"] - 1
        return current_week > end_week

    def clear_cache(self) -> None:
        """Clear the project plan cache."""
        self._project_plan_cache = None

    def _row_to_project_plan(self, row) -> dict[str, Any]:
        """
        Convert a database row to a project plan dictionary.

        Args:
            row: Database row from project_plans table

        Returns:
            Project plan dictionary
        """
        # Get start_week with fallback to 1 for older records
        start_week = 1
        try:
            start_week = row["start_week"]
        except (KeyError, IndexError):
            pass

        return {
            "id": row["id"],
            "project_name": row["project_name"],
            "project_summary": row["project_summary"],
            "plan": row["plan"],
            "generated_by": row["generated_by"],
            "duration_weeks": row["duration_weeks"],
            "start_week": start_week,
            "model_used": row["model_used"],
            "tokens_used": row["tokens_used"],
            "created_at": row["created_at"],
        }
