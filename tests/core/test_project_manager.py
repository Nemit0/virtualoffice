"""
Tests for ProjectManager module.

Tests project plan storage and retrieval, active project queries,
project-person assignments, multi-project scenarios, project chat room
lifecycle, and project completion detection.
"""

import json
import os
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from unittest.mock import Mock, MagicMock

import pytest

from virtualoffice.sim_manager.core.project_manager import ProjectManager
from virtualoffice.sim_manager.schemas import PersonRead
from virtualoffice.sim_manager.planner import PlanResult
from virtualoffice.sim_manager.gateways import ChatGateway


@contextmanager
def get_test_connection(db_path):
    """Get a connection to the test database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@pytest.fixture
def isolated_db(monkeypatch):
    """Create an isolated test database for each test."""
    # Create temp database
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    # Create required tables
    with get_test_connection(db_path) as conn:
        # Project plans table
        conn.execute("""
            CREATE TABLE project_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                project_summary TEXT NOT NULL,
                plan TEXT NOT NULL,
                generated_by INTEGER,
                duration_weeks INTEGER NOT NULL,
                start_week INTEGER DEFAULT 1,
                model_used TEXT,
                tokens_used INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Project assignments table
        conn.execute("""
            CREATE TABLE project_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                person_id INTEGER NOT NULL,
                UNIQUE(project_id, person_id)
            )
        """)
        
        # People table (for testing assignments)
        conn.execute("""
            CREATE TABLE people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                team_name TEXT,
                email_address TEXT,
                chat_handle TEXT
            )
        """)
        
        # Project chat rooms table
        conn.execute("""
            CREATE TABLE project_chat_rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                room_slug TEXT NOT NULL,
                room_name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                archived_at TIMESTAMP
            )
        """)
        
        conn.commit()

    # Patch get_connection
    import virtualoffice.common.db as db_module
    import virtualoffice.sim_manager.core.project_manager as project_manager_module

    def test_get_connection():
        return get_test_connection(db_path)

    monkeypatch.setattr(db_module, "get_connection", test_get_connection)
    monkeypatch.setattr(project_manager_module, "get_connection", test_get_connection)

    yield db_path

    # Cleanup
    try:
        time.sleep(0.05)
        if os.path.exists(db_path):
            os.remove(db_path)
    except (PermissionError, OSError):
        pass


def create_mock_person(
    person_id: int,
    name: str = "Test Worker",
    email: str = "test@example.com",
    handle: str = "test",
    role: str = "Developer",
    team_name: str = "Engineering"
) -> PersonRead:
    """Create a mock PersonRead object."""
    return PersonRead(
        id=person_id,
        name=name,
        role=role,
        timezone="UTC",
        work_hours="09:00-17:00",
        break_frequency="50/10 cadence",
        communication_style="professional",
        email_address=email,
        chat_handle=handle,
        is_department_head=False,
        skills=["Python"],
        personality=["collaborative"],
        team_name=team_name,
        objectives=[],
        metrics=[],
        persona_markdown="Test persona",
        planning_guidelines=[],
        event_playbook={},
        statuses=[]
    )


def create_test_plan_result(
    content: str = "Test project plan",
    model_used: str = "gpt-4o",
    tokens_used: int = 100
) -> PlanResult:
    """Create a test PlanResult."""
    return PlanResult(
        content=content,
        model_used=model_used,
        tokens_used=tokens_used
    )


class TestProjectManagerBasics:
    """Test basic ProjectManager functionality."""
    
    def test_initialization(self, isolated_db):
        """Test ProjectManager initializes correctly."""
        manager = ProjectManager()
        assert manager._project_plan_cache is None
    
    def test_clear_cache(self, isolated_db):
        """Test clearing the project plan cache."""
        manager = ProjectManager()
        manager._project_plan_cache = {"id": 1, "project_name": "Test"}
        
        manager.clear_cache()
        assert manager._project_plan_cache is None


class TestProjectPlanStorage:
    """Test project plan storage and retrieval."""
    
    def test_store_project_plan_basic(self, isolated_db):
        """Test storing a basic project plan."""
        manager = ProjectManager()
        plan_result = create_test_plan_result("Detailed project plan")
        
        project = manager.store_project_plan(
            project_name="Alpha Project",
            project_summary="Build new feature",
            plan_result=plan_result,
            generated_by=1,
            duration_weeks=4,
            start_week=1
        )
        
        assert project["id"] == 1
        assert project["project_name"] == "Alpha Project"
        assert project["project_summary"] == "Build new feature"
        assert project["plan"] == "Detailed project plan"
        assert project["generated_by"] == 1
        assert project["duration_weeks"] == 4
        assert project["start_week"] == 1
        assert project["model_used"] == "gpt-4o"
        assert project["tokens_used"] == 100
    
    def test_store_project_plan_with_assignments(self, isolated_db):
        """Test storing a project plan with person assignments."""
        manager = ProjectManager()
        
        # Create people in database
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (1, "Alice", "Developer", "Engineering")
            )
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (2, "Bob", "Developer", "Engineering")
            )
        
        plan_result = create_test_plan_result()
        project = manager.store_project_plan(
            project_name="Beta Project",
            project_summary="Refactor codebase",
            plan_result=plan_result,
            generated_by=1,
            duration_weeks=3,
            start_week=2,
            assigned_person_ids=[1, 2]
        )
        
        assert project["id"] == 1
        
        # Verify assignments in database
        with get_test_connection(isolated_db) as conn:
            rows = conn.execute(
                "SELECT * FROM project_assignments WHERE project_id = ?",
                (project["id"],)
            ).fetchall()
        
        assert len(rows) == 2
        person_ids = {row["person_id"] for row in rows}
        assert person_ids == {1, 2}
    
    def test_store_project_plan_caches_result(self, isolated_db):
        """Test that storing a project plan caches it."""
        manager = ProjectManager()
        plan_result = create_test_plan_result()
        
        project = manager.store_project_plan(
            project_name="Gamma Project",
            project_summary="Test caching",
            plan_result=plan_result,
            generated_by=None,
            duration_weeks=2
        )
        
        # Cache should be populated
        assert manager._project_plan_cache is not None
        assert manager._project_plan_cache["id"] == project["id"]
        assert manager._project_plan_cache["project_name"] == "Gamma Project"
    
    def test_store_multiple_projects(self, isolated_db):
        """Test storing multiple projects."""
        manager = ProjectManager()
        
        project1 = manager.store_project_plan(
            project_name="Project 1",
            project_summary="First project",
            plan_result=create_test_plan_result("Plan 1"),
            generated_by=1,
            duration_weeks=2
        )
        
        project2 = manager.store_project_plan(
            project_name="Project 2",
            project_summary="Second project",
            plan_result=create_test_plan_result("Plan 2"),
            generated_by=2,
            duration_weeks=3
        )
        
        assert project1["id"] == 1
        assert project2["id"] == 2
        assert project1["project_name"] == "Project 1"
        assert project2["project_name"] == "Project 2"


class TestProjectPlanRetrieval:
    """Test project plan retrieval."""
    
    def test_get_project_plan_by_id(self, isolated_db):
        """Test retrieving a project plan by ID."""
        manager = ProjectManager()
        
        # Store a project
        stored = manager.store_project_plan(
            project_name="Delta Project",
            project_summary="Test retrieval",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=4
        )
        
        # Retrieve by ID
        retrieved = manager.get_project_plan(stored["id"])
        
        assert retrieved is not None
        assert retrieved["id"] == stored["id"]
        assert retrieved["project_name"] == "Delta Project"
        assert retrieved["project_summary"] == "Test retrieval"
    
    def test_get_project_plan_most_recent(self, isolated_db):
        """Test retrieving the most recent project plan."""
        manager = ProjectManager()
        
        # Store multiple projects
        manager.store_project_plan(
            project_name="Old Project",
            project_summary="First",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=2
        )
        
        recent = manager.store_project_plan(
            project_name="Recent Project",
            project_summary="Latest",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=3
        )
        
        # Get most recent (no ID specified)
        retrieved = manager.get_project_plan()
        
        assert retrieved is not None
        assert retrieved["id"] == recent["id"]
        assert retrieved["project_name"] == "Recent Project"
    
    def test_get_project_plan_uses_cache(self, isolated_db):
        """Test that get_project_plan uses cache for most recent."""
        manager = ProjectManager()
        
        stored = manager.store_project_plan(
            project_name="Cached Project",
            project_summary="Test cache",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=2
        )
        
        # First call should populate cache
        retrieved1 = manager.get_project_plan()
        
        # Second call should use cache (verify by checking it's a copy)
        retrieved2 = manager.get_project_plan()
        
        assert retrieved1 == retrieved2
        assert retrieved1 is not retrieved2  # Should be a copy
    
    def test_get_project_plan_not_found(self, isolated_db):
        """Test retrieving non-existent project plan."""
        manager = ProjectManager()
        
        retrieved = manager.get_project_plan(999)
        assert retrieved is None
    
    def test_get_project_plan_empty_database(self, isolated_db):
        """Test retrieving from empty database."""
        manager = ProjectManager()
        
        retrieved = manager.get_project_plan()
        assert retrieved is None


class TestActiveProjectQueries:
    """Test active project queries."""
    
    def test_get_active_projects_for_person_with_assignment(self, isolated_db):
        """Test getting active projects for a person with specific assignment."""
        manager = ProjectManager()
        
        # Create people
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (1, "Alice", "Developer", "Engineering")
            )
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (2, "Bob", "Developer", "Engineering")
            )
        
        # Store project assigned to Alice
        manager.store_project_plan(
            project_name="Alice's Project",
            project_summary="For Alice",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=4,
            start_week=1,
            assigned_person_ids=[1]
        )
        
        # Get active projects for Alice at week 2
        projects = manager.get_active_projects_for_person(1, week=2)
        
        assert len(projects) == 1
        assert projects[0]["project_name"] == "Alice's Project"
    
    def test_get_active_projects_for_person_no_assignment(self, isolated_db):
        """Test getting projects without specific assignments (everyone works on them)."""
        manager = ProjectManager()
        
        # Create people
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (1, "Alice", "Developer", "Engineering")
            )
        
        # Store project without assignments (everyone works on it)
        manager.store_project_plan(
            project_name="Team Project",
            project_summary="For everyone",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=3,
            start_week=1
        )
        
        # Get active projects for Alice
        projects = manager.get_active_projects_for_person(1, week=2)
        
        assert len(projects) == 1
        assert projects[0]["project_name"] == "Team Project"
    
    def test_get_active_projects_respects_timeline(self, isolated_db):
        """Test that only projects active in the specified week are returned."""
        manager = ProjectManager()
        
        # Create person
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (1, "Alice", "Developer", "Engineering")
            )
        
        # Project 1: weeks 1-2
        manager.store_project_plan(
            project_name="Early Project",
            project_summary="Weeks 1-2",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=2,
            start_week=1,
            assigned_person_ids=[1]
        )
        
        # Project 2: weeks 3-5
        manager.store_project_plan(
            project_name="Later Project",
            project_summary="Weeks 3-5",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=3,
            start_week=3,
            assigned_person_ids=[1]
        )
        
        # At week 1: only Early Project
        projects_week1 = manager.get_active_projects_for_person(1, week=1)
        assert len(projects_week1) == 1
        assert projects_week1[0]["project_name"] == "Early Project"
        
        # At week 3: only Later Project
        projects_week3 = manager.get_active_projects_for_person(1, week=3)
        assert len(projects_week3) == 1
        assert projects_week3[0]["project_name"] == "Later Project"
        
        # At week 6: no projects
        projects_week6 = manager.get_active_projects_for_person(1, week=6)
        assert len(projects_week6) == 0
    
    def test_get_active_project_for_person_returns_first(self, isolated_db):
        """Test get_active_project_for_person returns first active project."""
        manager = ProjectManager()
        
        # Create person
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (1, "Alice", "Developer", "Engineering")
            )
        
        # Store multiple projects
        manager.store_project_plan(
            project_name="Project A",
            project_summary="First",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=4,
            start_week=1,
            assigned_person_ids=[1]
        )
        
        manager.store_project_plan(
            project_name="Project B",
            project_summary="Second",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=4,
            start_week=1,
            assigned_person_ids=[1]
        )
        
        # Get single active project
        project = manager.get_active_project_for_person(1, week=2)
        
        assert project is not None
        assert project["project_name"] == "Project A"  # First one
    
    def test_get_active_project_for_person_none_active(self, isolated_db):
        """Test get_active_project_for_person returns None when no active projects."""
        manager = ProjectManager()
        
        # Create person
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (1, "Alice", "Developer", "Engineering")
            )
        
        project = manager.get_active_project_for_person(1, week=1)
        assert project is None


class TestActiveProjectsWithAssignments:
    """Test getting active projects with team assignments."""
    
    def test_get_active_projects_with_assignments_basic(self, isolated_db):
        """Test getting active projects with their team members."""
        manager = ProjectManager()
        
        # Create people
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (1, "Alice", "Developer", "Engineering")
            )
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (2, "Bob", "Designer", "Design")
            )
        
        # Store project with assignments
        manager.store_project_plan(
            project_name="Team Project",
            project_summary="Collaborative work",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=3,
            start_week=1,
            assigned_person_ids=[1, 2]
        )
        
        # Get active projects with assignments
        result = manager.get_active_projects_with_assignments(week=2)
        
        assert len(result) == 1
        assert result[0]["project"]["project_name"] == "Team Project"
        assert len(result[0]["team_members"]) == 2
        
        # Check team members
        member_names = {m["name"] for m in result[0]["team_members"]}
        assert member_names == {"Alice", "Bob"}
    
    def test_get_active_projects_with_assignments_no_specific_assignments(self, isolated_db):
        """Test project without assignments includes all people."""
        manager = ProjectManager()
        
        # Create people
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (1, "Alice", "Developer", "Engineering")
            )
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (2, "Bob", "Designer", "Design")
            )
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (3, "Charlie", "Manager", "Management")
            )
        
        # Store project without assignments
        manager.store_project_plan(
            project_name="Company-wide Project",
            project_summary="Everyone participates",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=2,
            start_week=1
        )
        
        # Get active projects
        result = manager.get_active_projects_with_assignments(week=1)
        
        assert len(result) == 1
        assert len(result[0]["team_members"]) == 3
        
        member_names = {m["name"] for m in result[0]["team_members"]}
        assert member_names == {"Alice", "Bob", "Charlie"}
    
    def test_get_active_projects_with_assignments_multiple_projects(self, isolated_db):
        """Test getting multiple active projects with their teams."""
        manager = ProjectManager()
        
        # Create people
        with get_test_connection(isolated_db) as conn:
            for i in range(1, 5):
                conn.execute(
                    "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                    (i, f"Person {i}", "Developer", "Engineering")
                )
        
        # Project 1: Person 1 and 2
        manager.store_project_plan(
            project_name="Project Alpha",
            project_summary="First project",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=3,
            start_week=1,
            assigned_person_ids=[1, 2]
        )
        
        # Project 2: Person 3 and 4
        manager.store_project_plan(
            project_name="Project Beta",
            project_summary="Second project",
            plan_result=create_test_plan_result(),
            generated_by=3,
            duration_weeks=2,
            start_week=1,
            assigned_person_ids=[3, 4]
        )
        
        # Get all active projects
        result = manager.get_active_projects_with_assignments(week=2)
        
        assert len(result) == 2
        
        # Check first project
        alpha = next(r for r in result if r["project"]["project_name"] == "Project Alpha")
        assert len(alpha["team_members"]) == 2
        alpha_names = {m["name"] for m in alpha["team_members"]}
        assert alpha_names == {"Person 1", "Person 2"}
        
        # Check second project
        beta = next(r for r in result if r["project"]["project_name"] == "Project Beta")
        assert len(beta["team_members"]) == 2
        beta_names = {m["name"] for m in beta["team_members"]}
        assert beta_names == {"Person 3", "Person 4"}
    
    def test_get_active_projects_with_assignments_respects_timeline(self, isolated_db):
        """Test that only projects active in specified week are returned."""
        manager = ProjectManager()
        
        # Create people
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (1, "Alice", "Developer", "Engineering")
            )
        
        # Early project: weeks 1-2
        manager.store_project_plan(
            project_name="Early",
            project_summary="Weeks 1-2",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=2,
            start_week=1,
            assigned_person_ids=[1]
        )
        
        # Late project: weeks 4-5
        manager.store_project_plan(
            project_name="Late",
            project_summary="Weeks 4-5",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=2,
            start_week=4,
            assigned_person_ids=[1]
        )
        
        # Week 1: only Early
        result_week1 = manager.get_active_projects_with_assignments(week=1)
        assert len(result_week1) == 1
        assert result_week1[0]["project"]["project_name"] == "Early"
        
        # Week 3: none
        result_week3 = manager.get_active_projects_with_assignments(week=3)
        assert len(result_week3) == 0
        
        # Week 4: only Late
        result_week4 = manager.get_active_projects_with_assignments(week=4)
        assert len(result_week4) == 1
        assert result_week4[0]["project"]["project_name"] == "Late"


class TestMultiProjectScenarios:
    """Test multi-project scenarios."""
    
    def test_person_assigned_to_multiple_projects(self, isolated_db):
        """Test person working on multiple projects simultaneously."""
        manager = ProjectManager()
        
        # Create person
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (1, "Alice", "Developer", "Engineering")
            )
        
        # Project 1
        manager.store_project_plan(
            project_name="Project 1",
            project_summary="First",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=4,
            start_week=1,
            assigned_person_ids=[1]
        )
        
        # Project 2 (overlapping timeline)
        manager.store_project_plan(
            project_name="Project 2",
            project_summary="Second",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=3,
            start_week=2,
            assigned_person_ids=[1]
        )
        
        # At week 3, Alice should have both projects
        projects = manager.get_active_projects_for_person(1, week=3)
        
        assert len(projects) == 2
        project_names = {p["project_name"] for p in projects}
        assert project_names == {"Project 1", "Project 2"}
    
    def test_overlapping_projects_different_teams(self, isolated_db):
        """Test multiple overlapping projects with different teams."""
        manager = ProjectManager()
        
        # Create people
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (1, "Alice", "Developer", "Team A")
            )
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (2, "Bob", "Developer", "Team B")
            )
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (3, "Charlie", "Developer", "Team A")
            )
        
        # Project for Team A
        manager.store_project_plan(
            project_name="Team A Project",
            project_summary="For Team A",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=3,
            start_week=1,
            assigned_person_ids=[1, 3]
        )
        
        # Project for Team B
        manager.store_project_plan(
            project_name="Team B Project",
            project_summary="For Team B",
            plan_result=create_test_plan_result(),
            generated_by=2,
            duration_weeks=3,
            start_week=1,
            assigned_person_ids=[2]
        )
        
        # Alice should only see Team A project
        alice_projects = manager.get_active_projects_for_person(1, week=2)
        assert len(alice_projects) == 1
        assert alice_projects[0]["project_name"] == "Team A Project"
        
        # Bob should only see Team B project
        bob_projects = manager.get_active_projects_for_person(2, week=2)
        assert len(bob_projects) == 1
        assert bob_projects[0]["project_name"] == "Team B Project"
    
    def test_sequential_projects(self, isolated_db):
        """Test sequential projects (one after another)."""
        manager = ProjectManager()
        
        # Create person
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (1, "Alice", "Developer", "Engineering")
            )
        
        # Project 1: weeks 1-2
        manager.store_project_plan(
            project_name="Phase 1",
            project_summary="First phase",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=2,
            start_week=1,
            assigned_person_ids=[1]
        )
        
        # Project 2: weeks 3-4 (starts after Project 1 ends)
        manager.store_project_plan(
            project_name="Phase 2",
            project_summary="Second phase",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=2,
            start_week=3,
            assigned_person_ids=[1]
        )
        
        # Week 1: only Phase 1
        week1_projects = manager.get_active_projects_for_person(1, week=1)
        assert len(week1_projects) == 1
        assert week1_projects[0]["project_name"] == "Phase 1"
        
        # Week 3: only Phase 2
        week3_projects = manager.get_active_projects_for_person(1, week=3)
        assert len(week3_projects) == 1
        assert week3_projects[0]["project_name"] == "Phase 2"
    
    def test_mixed_assigned_and_unassigned_projects(self, isolated_db):
        """Test person with both assigned and unassigned projects."""
        manager = ProjectManager()
        
        # Create people
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (1, "Alice", "Developer", "Engineering")
            )
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (2, "Bob", "Developer", "Engineering")
            )
        
        # Assigned project (only Alice)
        manager.store_project_plan(
            project_name="Alice's Project",
            project_summary="Specific to Alice",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=3,
            start_week=1,
            assigned_person_ids=[1]
        )
        
        # Unassigned project (everyone)
        manager.store_project_plan(
            project_name="Team Project",
            project_summary="For everyone",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=3,
            start_week=1
        )
        
        # Alice should see both projects
        alice_projects = manager.get_active_projects_for_person(1, week=2)
        assert len(alice_projects) == 2
        project_names = {p["project_name"] for p in alice_projects}
        assert project_names == {"Alice's Project", "Team Project"}
        
        # Bob should only see the team project
        bob_projects = manager.get_active_projects_for_person(2, week=2)
        assert len(bob_projects) == 1
        assert bob_projects[0]["project_name"] == "Team Project"


class TestProjectChatRoomLifecycle:
    """Test project chat room lifecycle management."""
    
    def test_create_project_chat_room(self, isolated_db):
        """Test creating a project chat room."""
        manager = ProjectManager()
        
        # Create mock chat gateway
        mock_chat_gateway = Mock(spec=ChatGateway)
        mock_chat_gateway.create_room.return_value = {
            'slug': 'project-1-alpha-project',
            'name': 'Alpha Project Team'
        }
        
        # Create team members
        alice = create_mock_person(1, "Alice", "alice@test.com", "alice")
        bob = create_mock_person(2, "Bob", "bob@test.com", "bob")
        team_members = [alice, bob]
        
        # Create chat room
        room_slug = manager.create_project_chat_room(
            project_id=1,
            project_name="Alpha Project",
            team_members=team_members,
            chat_gateway=mock_chat_gateway
        )
        
        assert room_slug == "project-1-alpha-project"
        
        # Verify chat gateway was called correctly
        mock_chat_gateway.create_room.assert_called_once()
        call_kwargs = mock_chat_gateway.create_room.call_args[1]
        assert call_kwargs['name'] == "Alpha Project Team"
        assert call_kwargs['slug'] == "project-1-alpha-project"
        assert set(call_kwargs['participants']) == {"alice", "bob"}
        
        # Verify database entry
        with get_test_connection(isolated_db) as conn:
            row = conn.execute(
                "SELECT * FROM project_chat_rooms WHERE project_id = ?",
                (1,)
            ).fetchone()
        
        assert row is not None
        assert row["room_slug"] == "project-1-alpha-project"
        assert row["room_name"] == "Alpha Project Team"
        assert row["is_active"] == 1
    
    def test_get_active_project_chat_room(self, isolated_db):
        """Test retrieving active project chat room."""
        manager = ProjectManager()
        
        # Create chat room
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                """INSERT INTO project_chat_rooms(project_id, room_slug, room_name, is_active)
                   VALUES (?, ?, ?, ?)""",
                (1, "project-1-test", "Test Room", 1)
            )
        
        # Get active room
        room_slug = manager.get_active_project_chat_room(1)
        
        assert room_slug == "project-1-test"
    
    def test_get_active_project_chat_room_none_exists(self, isolated_db):
        """Test getting active chat room when none exists."""
        manager = ProjectManager()
        
        room_slug = manager.get_active_project_chat_room(999)
        assert room_slug is None
    
    def test_get_active_project_chat_room_only_archived(self, isolated_db):
        """Test getting active room when only archived rooms exist."""
        manager = ProjectManager()
        
        # Create archived room
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                """INSERT INTO project_chat_rooms(project_id, room_slug, room_name, is_active)
                   VALUES (?, ?, ?, ?)""",
                (1, "project-1-archived", "Archived Room", 0)
            )
        
        room_slug = manager.get_active_project_chat_room(1)
        assert room_slug is None
    
    def test_archive_project_chat_room(self, isolated_db):
        """Test archiving a project chat room."""
        manager = ProjectManager()
        
        # Create active room
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                """INSERT INTO project_chat_rooms(project_id, room_slug, room_name, is_active)
                   VALUES (?, ?, ?, ?)""",
                (1, "project-1-test", "Test Room", 1)
            )
        
        # Archive the room
        result = manager.archive_project_chat_room(1)
        
        assert result is True
        
        # Verify room is archived
        with get_test_connection(isolated_db) as conn:
            row = conn.execute(
                "SELECT * FROM project_chat_rooms WHERE project_id = ?",
                (1,)
            ).fetchone()
        
        assert row["is_active"] == 0
        assert row["archived_at"] is not None
    
    def test_archive_project_chat_room_none_exists(self, isolated_db):
        """Test archiving when no active room exists."""
        manager = ProjectManager()
        
        result = manager.archive_project_chat_room(999)
        assert result is False
    
    def test_archive_project_chat_room_already_archived(self, isolated_db):
        """Test archiving an already archived room."""
        manager = ProjectManager()
        
        # Create archived room
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                """INSERT INTO project_chat_rooms(project_id, room_slug, room_name, is_active)
                   VALUES (?, ?, ?, ?)""",
                (1, "project-1-test", "Test Room", 0)
            )
        
        result = manager.archive_project_chat_room(1)
        assert result is False
    
    def test_multiple_chat_rooms_returns_most_recent(self, isolated_db):
        """Test that get_active_project_chat_room returns most recent active room."""
        manager = ProjectManager()
        
        # Create multiple active rooms (shouldn't happen in practice, but test it)
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                """INSERT INTO project_chat_rooms(project_id, room_slug, room_name, is_active, created_at)
                   VALUES (?, ?, ?, ?, datetime('now', '-2 hours'))""",
                (1, "project-1-old", "Old Room", 1)
            )
            conn.execute(
                """INSERT INTO project_chat_rooms(project_id, room_slug, room_name, is_active, created_at)
                   VALUES (?, ?, ?, ?, datetime('now'))""",
                (1, "project-1-new", "New Room", 1)
            )
        
        room_slug = manager.get_active_project_chat_room(1)
        assert room_slug == "project-1-new"


class TestProjectCompletionDetection:
    """Test project completion detection."""
    
    def test_is_project_complete_before_end(self, isolated_db):
        """Test project is not complete before its end week."""
        manager = ProjectManager()
        
        # Create project: weeks 1-3
        project = manager.store_project_plan(
            project_name="Test Project",
            project_summary="Test",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=3,
            start_week=1
        )
        
        # Check at week 2 (during project)
        is_complete = manager.is_project_complete(project["id"], current_week=2)
        assert is_complete is False
    
    def test_is_project_complete_at_end(self, isolated_db):
        """Test project is not complete at its end week."""
        manager = ProjectManager()
        
        # Create project: weeks 1-3
        project = manager.store_project_plan(
            project_name="Test Project",
            project_summary="Test",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=3,
            start_week=1
        )
        
        # Check at week 3 (end week)
        is_complete = manager.is_project_complete(project["id"], current_week=3)
        assert is_complete is False
    
    def test_is_project_complete_after_end(self, isolated_db):
        """Test project is complete after its end week."""
        manager = ProjectManager()
        
        # Create project: weeks 1-3 (ends at week 3)
        project = manager.store_project_plan(
            project_name="Test Project",
            project_summary="Test",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=3,
            start_week=1
        )
        
        # Check at week 4 (after end)
        is_complete = manager.is_project_complete(project["id"], current_week=4)
        assert is_complete is True
    
    def test_is_project_complete_project_not_found(self, isolated_db):
        """Test is_project_complete returns False for non-existent project."""
        manager = ProjectManager()
        
        is_complete = manager.is_project_complete(999, current_week=5)
        assert is_complete is False
    
    def test_is_project_complete_various_durations(self, isolated_db):
        """Test completion detection with various project durations."""
        manager = ProjectManager()
        
        # 1-week project starting at week 2
        project1 = manager.store_project_plan(
            project_name="Short Project",
            project_summary="1 week",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=1,
            start_week=2
        )
        
        # 5-week project starting at week 1
        project2 = manager.store_project_plan(
            project_name="Long Project",
            project_summary="5 weeks",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=5,
            start_week=1
        )
        
        # Week 2: Short project active, Long project active
        assert manager.is_project_complete(project1["id"], 2) is False
        assert manager.is_project_complete(project2["id"], 2) is False
        
        # Week 3: Short project complete, Long project active
        assert manager.is_project_complete(project1["id"], 3) is True
        assert manager.is_project_complete(project2["id"], 3) is False
        
        # Week 6: Both complete
        assert manager.is_project_complete(project1["id"], 6) is True
        assert manager.is_project_complete(project2["id"], 6) is True


class TestProjectManagerEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_store_project_with_empty_assignment_list(self, isolated_db):
        """Test storing project with empty assignment list."""
        manager = ProjectManager()
        
        project = manager.store_project_plan(
            project_name="Test",
            project_summary="Test",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=2,
            assigned_person_ids=[]
        )
        
        assert project is not None
        
        # Verify no assignments created
        with get_test_connection(isolated_db) as conn:
            rows = conn.execute(
                "SELECT * FROM project_assignments WHERE project_id = ?",
                (project["id"],)
            ).fetchall()
        assert len(rows) == 0
    
    def test_store_project_with_duplicate_assignments(self, isolated_db):
        """Test storing project with duplicate person IDs in assignments."""
        manager = ProjectManager()
        
        # Create person
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (1, "Alice", "Developer", "Engineering")
            )
        
        # Store with duplicate IDs
        project = manager.store_project_plan(
            project_name="Test",
            project_summary="Test",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=2,
            assigned_person_ids=[1, 1, 1]  # Duplicates
        )
        
        # Verify only one assignment created (due to UNIQUE constraint)
        with get_test_connection(isolated_db) as conn:
            rows = conn.execute(
                "SELECT * FROM project_assignments WHERE project_id = ?",
                (project["id"],)
            ).fetchall()
        assert len(rows) == 1
    
    def test_get_active_projects_week_zero(self, isolated_db):
        """Test getting active projects at week 0."""
        manager = ProjectManager()
        
        # Create person
        with get_test_connection(isolated_db) as conn:
            conn.execute(
                "INSERT INTO people(id, name, role, team_name) VALUES (?, ?, ?, ?)",
                (1, "Alice", "Developer", "Engineering")
            )
        
        # Project starting at week 1
        manager.store_project_plan(
            project_name="Test",
            project_summary="Test",
            plan_result=create_test_plan_result(),
            generated_by=1,
            duration_weeks=2,
            start_week=1,
            assigned_person_ids=[1]
        )
        
        # Week 0 should return no projects
        projects = manager.get_active_projects_for_person(1, week=0)
        assert len(projects) == 0
    
    def test_create_chat_room_with_special_characters_in_name(self, isolated_db):
        """Test creating chat room with special characters in project name."""
        manager = ProjectManager()
        
        mock_chat_gateway = Mock(spec=ChatGateway)
        mock_chat_gateway.create_room.return_value = {
            'slug': 'project-1-test-project',
            'name': 'Test & Project! Team'
        }
        
        alice = create_mock_person(1, "Alice", "alice@test.com", "alice")
        
        room_slug = manager.create_project_chat_room(
            project_id=1,
            project_name="Test & Project!",
            team_members=[alice],
            chat_gateway=mock_chat_gateway
        )
        
        # Should handle special characters
        assert room_slug is not None
        
        # Verify slug generation handles special characters
        call_kwargs = mock_chat_gateway.create_room.call_args[1]
        assert "test" in call_kwargs['slug'].lower()
        assert "project" in call_kwargs['slug'].lower()
    
    def test_row_to_project_plan_missing_start_week(self, isolated_db):
        """Test _row_to_project_plan handles missing start_week gracefully."""
        manager = ProjectManager()
        
        # Insert project without start_week (simulating old schema)
        with get_test_connection(isolated_db) as conn:
            # Temporarily drop and recreate table without start_week
            conn.execute("DROP TABLE project_plans")
            conn.execute("""
                CREATE TABLE project_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_name TEXT NOT NULL,
                    project_summary TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    generated_by INTEGER,
                    duration_weeks INTEGER NOT NULL,
                    model_used TEXT,
                    tokens_used INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute(
                """INSERT INTO project_plans(project_name, project_summary, plan, 
                   generated_by, duration_weeks, model_used, tokens_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("Old Project", "Test", "Plan", 1, 2, "gpt-4o", 100)
            )
        
        # Get project (should default start_week to 1)
        project = manager.get_project_plan(1)
        
        assert project is not None
        assert project["start_week"] == 1  # Default value


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
