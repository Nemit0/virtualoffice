"""
Tests for ContextBuilder class.

Tests context aggregation for different prompt types and locales.
"""

import pytest
from virtualoffice.sim_manager.prompts import ContextBuilder
from virtualoffice.sim_manager.schemas import PersonRead


@pytest.fixture
def sample_worker():
    """Create a sample worker persona."""
    return PersonRead(
        id=1,
        name="Alice Developer",
        role="Senior Developer",
        email_address="alice@example.dev",
        chat_handle="alice_dev",
        timezone="America/New_York",
        persona_markdown="Experienced full-stack developer with focus on Python and React.",
        work_hours="09:00-17:00",
        break_frequency="25/5,90/lunch/60",
        communication_style="Direct and collaborative",
        skills=["Python", "React", "API Design"],
        personality=["Detail-oriented", "Team player"],
    )


@pytest.fixture
def sample_team():
    """Create a sample team."""
    return [
        PersonRead(
            id=1,
            name="Alice Developer",
            role="Senior Developer",
            email_address="alice@example.dev",
            chat_handle="alice_dev",
            timezone="America/New_York",
            work_hours="09:00-17:00",
            break_frequency="25/5",
            communication_style="Direct",
            skills=["Python"],
            personality=["Detail-oriented"],
            persona_markdown="Developer persona",
        ),
        PersonRead(
            id=2,
            name="Bob Designer",
            role="UI/UX Designer",
            email_address="bob@example.dev",
            chat_handle="bob_design",
            timezone="America/New_York",
            work_hours="09:00-17:00",
            break_frequency="25/5",
            communication_style="Visual",
            skills=["Design"],
            personality=["Creative"],
            persona_markdown="Designer persona",
        ),
        PersonRead(
            id=3,
            name="Charlie Manager",
            role="Project Manager",
            email_address="charlie@example.dev",
            chat_handle="charlie_pm",
            timezone="America/New_York",
            work_hours="09:00-17:00",
            break_frequency="25/5",
            communication_style="Organized",
            skills=["Management"],
            personality=["Leader"],
            persona_markdown="Manager persona",
        ),
    ]


class TestContextBuilderInitialization:
    """Test ContextBuilder initialization."""
    
    def test_init_default_locale(self):
        """Test initialization with default locale."""
        builder = ContextBuilder()
        assert builder.locale == "en"
    
    def test_init_english_locale(self):
        """Test initialization with English locale."""
        builder = ContextBuilder(locale="en")
        assert builder.locale == "en"
    
    def test_init_korean_locale(self):
        """Test initialization with Korean locale."""
        builder = ContextBuilder(locale="ko")
        assert builder.locale == "ko"
    
    def test_init_normalizes_locale(self):
        """Test that locale is normalized to lowercase."""
        builder = ContextBuilder(locale="EN")
        assert builder.locale == "en"


class TestPlanningContextBuilding:
    """Test building planning context."""
    
    def test_build_planning_context_basic(self, sample_worker, sample_team):
        """Test basic planning context building."""
        builder = ContextBuilder(locale="en")
        
        context = builder.build_planning_context(
            worker=sample_worker,
            tick=100,
            reason="start_of_hour",
            project_plan="Build mobile app MVP",
            daily_plan="Focus on API integration",
            team=sample_team,
        )
        
        assert context["worker_name"] == "Alice Developer"
        assert context["worker_role"] == "Senior Developer"
        assert context["worker_email"] == "alice@example.dev"
        assert context["worker_chat_handle"] == "alice_dev"
        assert context["tick"] == 100
        assert context["context_reason"] == "start_of_hour"
        assert context["project_plan"] == "Build mobile app MVP"
        assert context["daily_plan"] == "Focus on API integration"
        assert context["locale"] == "en"
    
    def test_build_planning_context_with_persona(self, sample_worker, sample_team):
        """Test that persona markdown is included."""
        builder = ContextBuilder(locale="en")
        
        context = builder.build_planning_context(
            worker=sample_worker,
            tick=100,
            reason="start_of_hour",
            project_plan="Build mobile app",
            daily_plan="API work",
            team=sample_team,
        )
        
        assert "persona_markdown" in context
        assert "Python and React" in context["persona_markdown"]
    
    def test_build_planning_context_without_persona(self, sample_team):
        """Test context building when worker has no persona markdown."""
        worker = PersonRead(
            id=1,
            name="Alice",
            role="Developer",
            email_address="alice@example.dev",
            chat_handle="alice",
            timezone="UTC",
            work_hours="09:00-17:00",
            break_frequency="25/5",
            communication_style="Direct",
            skills=["Coding"],
            personality=["Focused"],
            persona_markdown="",  # Empty persona
        )
        
        builder = ContextBuilder(locale="en")
        context = builder.build_planning_context(
            worker=worker,
            tick=100,
            reason="start_of_hour",
            project_plan="Build app",
            daily_plan="Work",
            team=sample_team,
        )
        
        assert "persona_markdown" in context
        assert "Developer" in context["persona_markdown"]
    
    def test_build_planning_context_with_team_roster(self, sample_worker, sample_team):
        """Test that team roster is formatted correctly."""
        builder = ContextBuilder(locale="en")
        
        context = builder.build_planning_context(
            worker=sample_worker,
            tick=100,
            reason="start_of_hour",
            project_plan="Build app",
            daily_plan="Work",
            team=sample_team,
        )
        
        assert "team_roster" in context
        roster = context["team_roster"]
        assert "YOUR TEAM ROSTER" in roster
        assert "Bob Designer" in roster
        assert "bob@example.dev" in roster
        assert "Charlie Manager" in roster
        # Worker should not be in teammates list (but shown as YOU)
        assert "YOU: Alice Developer" in roster
    
    def test_build_planning_context_with_recent_emails(self, sample_worker, sample_team):
        """Test including recent emails for threading."""
        builder = ContextBuilder(locale="en")
        
        recent_emails = [
            {
                "email_id": "email-1",
                "from": "bob@example.dev",
                "subject": "API design review",
            },
            {
                "email_id": "email-2",
                "from": "charlie@example.dev",
                "subject": "Sprint planning",
            },
        ]
        
        context = builder.build_planning_context(
            worker=sample_worker,
            tick=100,
            reason="start_of_hour",
            project_plan="Build app",
            daily_plan="Work",
            team=sample_team,
            recent_emails=recent_emails,
        )
        
        assert "recent_emails" in context
        emails_text = context["recent_emails"]
        assert "email-1" in emails_text
        assert "API design review" in emails_text
        assert "email-2" in emails_text
    
    def test_build_planning_context_without_recent_emails(self, sample_worker, sample_team):
        """Test context when no recent emails provided."""
        builder = ContextBuilder(locale="en")
        
        context = builder.build_planning_context(
            worker=sample_worker,
            tick=100,
            reason="start_of_hour",
            project_plan="Build app",
            daily_plan="Work",
            team=sample_team,
            recent_emails=None,
        )
        
        assert "recent_emails" in context
        assert "No recent emails" in context["recent_emails"]
    
    def test_build_planning_context_multi_project(self, sample_worker, sample_team):
        """Test context for multi-project scenarios."""
        builder = ContextBuilder(locale="en")
        
        projects = [
            {
                "project_name": "Mobile App MVP",
                "plan": "Build iOS and Android apps with core features",
            },
            {
                "project_name": "Web Dashboard",
                "plan": "Create admin dashboard for data visualization",
            },
        ]
        
        context = builder.build_planning_context(
            worker=sample_worker,
            tick=100,
            reason="start_of_hour",
            project_plan="Current project plan",
            daily_plan="Work on both projects",
            team=sample_team,
            all_active_projects=projects,
        )
        
        assert context["multi_project_mode"] is True
        assert "active_projects" in context
        projects_text = context["active_projects"]
        assert "MULTIPLE projects" in projects_text
        assert "Mobile App MVP" in projects_text
        assert "Web Dashboard" in projects_text
    
    def test_build_planning_context_single_project(self, sample_worker, sample_team):
        """Test context when only one project is active."""
        builder = ContextBuilder(locale="en")
        
        projects = [
            {
                "project_name": "Mobile App MVP",
                "plan": "Build iOS and Android apps",
            },
        ]
        
        context = builder.build_planning_context(
            worker=sample_worker,
            tick=100,
            reason="start_of_hour",
            project_plan="Current project plan",
            daily_plan="Work",
            team=sample_team,
            all_active_projects=projects,
        )
        
        assert context["multi_project_mode"] is False


class TestEventContextBuilding:
    """Test building event context."""
    
    def test_build_event_context_basic(self, sample_worker, sample_team):
        """Test basic event context building."""
        builder = ContextBuilder(locale="en")
        
        event = {
            "event_type": "client_request",
            "description": "Client requested new feature",
            "payload": {"priority": "high", "deadline": "2 days"},
        }
        
        project_plan = {
            "project_name": "Mobile App MVP",
            "plan": "Build core features",
        }
        
        context = builder.build_event_context(
            worker=sample_worker,
            event=event,
            tick=100,
            team=sample_team,
            project_plan=project_plan,
        )
        
        assert context["worker_name"] == "Alice Developer"
        assert context["worker_role"] == "Senior Developer"
        assert context["tick"] == 100
        assert context["event_type"] == "client_request"
        assert context["event_description"] == "Client requested new feature"
        assert context["event_payload"]["priority"] == "high"
        assert context["project_name"] == "Mobile App MVP"
    
    def test_build_event_context_with_persona(self, sample_worker, sample_team):
        """Test that persona is included in event context."""
        builder = ContextBuilder(locale="en")
        
        event = {"event_type": "blocker", "description": "API down", "payload": {}}
        project_plan = {"project_name": "Project", "plan": "Plan"}
        
        context = builder.build_event_context(
            worker=sample_worker,
            event=event,
            tick=100,
            team=sample_team,
            project_plan=project_plan,
        )
        
        assert "persona_markdown" in context
        assert "Python and React" in context["persona_markdown"]


class TestReportingContextBuilding:
    """Test building reporting context."""
    
    def test_build_reporting_context_basic(self, sample_worker):
        """Test basic reporting context building."""
        builder = ContextBuilder(locale="en")
        
        context = builder.build_reporting_context(
            worker=sample_worker,
            day_index=0,
            daily_plan="Focus on API integration",
            hourly_log="09:00 - Started API work\n10:00 - Completed auth module",
            minute_schedule="Detailed schedule here",
        )
        
        assert context["worker_name"] == "Alice Developer"
        assert context["worker_role"] == "Senior Developer"
        assert context["day_index"] == 0
        assert context["day_number"] == 1
        assert context["daily_plan"] == "Focus on API integration"
        assert "Started API work" in context["hourly_log"]
        assert context["locale"] == "en"
    
    def test_build_reporting_context_with_persona(self, sample_worker):
        """Test that persona is included in reporting context."""
        builder = ContextBuilder(locale="en")
        
        context = builder.build_reporting_context(
            worker=sample_worker,
            day_index=0,
            daily_plan="Work",
            hourly_log="Log",
            minute_schedule="Schedule",
        )
        
        assert "persona_markdown" in context
        assert "Python and React" in context["persona_markdown"]
    
    def test_build_reporting_context_empty_logs(self, sample_worker):
        """Test reporting context with empty logs."""
        builder = ContextBuilder(locale="en")
        
        context = builder.build_reporting_context(
            worker=sample_worker,
            day_index=0,
            daily_plan="Work",
            hourly_log="",
            minute_schedule="",
        )
        
        assert "No hourly updates recorded" in context["hourly_log"]
        assert "No detailed schedule available" in context["minute_schedule"]


class TestKoreanLocalization:
    """Test Korean locale support in context building."""
    
    def test_korean_team_roster_format(self, sample_team):
        """Test that Korean team roster uses Korean labels."""
        worker = sample_team[0]
        builder = ContextBuilder(locale="ko")
        
        context = builder.build_planning_context(
            worker=worker,
            tick=100,
            reason="시작",
            project_plan="프로젝트 계획",
            daily_plan="일일 계획",
            team=sample_team,
        )
        
        roster = context["team_roster"]
        assert "팀 명단" in roster
        assert "본인" in roster
        assert "팀원" in roster
        assert "이메일" in roster
        assert "채팅" in roster
    
    def test_korean_recent_emails_format(self, sample_worker, sample_team):
        """Test that Korean recent emails use Korean labels."""
        builder = ContextBuilder(locale="ko")
        
        recent_emails = [
            {"email_id": "email-1", "from": "bob@example.dev", "subject": "테스트"},
        ]
        
        context = builder.build_planning_context(
            worker=sample_worker,
            tick=100,
            reason="시작",
            project_plan="계획",
            daily_plan="일일",
            team=sample_team,
            recent_emails=recent_emails,
        )
        
        emails_text = context["recent_emails"]
        assert "최근 이메일" in emails_text
    
    def test_korean_multi_project_format(self, sample_worker, sample_team):
        """Test that Korean multi-project context uses Korean labels."""
        builder = ContextBuilder(locale="ko")
        
        projects = [
            {"project_name": "프로젝트 A", "plan": "계획 A"},
            {"project_name": "프로젝트 B", "plan": "계획 B"},
        ]
        
        context = builder.build_planning_context(
            worker=sample_worker,
            tick=100,
            reason="시작",
            project_plan="계획",
            daily_plan="일일",
            team=sample_team,
            all_active_projects=projects,
        )
        
        projects_text = context["active_projects"]
        assert "여러 프로젝트" in projects_text or "프로젝트" in projects_text


class TestTeamRosterFormatting:
    """Test team roster formatting details."""
    
    def test_team_roster_excludes_self_from_teammates(self, sample_worker, sample_team):
        """Test that worker is not listed in teammates section."""
        builder = ContextBuilder(locale="en")
        
        context = builder.build_planning_context(
            worker=sample_worker,
            tick=100,
            reason="start",
            project_plan="plan",
            daily_plan="daily",
            team=sample_team,
        )
        
        roster = context["team_roster"]
        # Worker should be in YOU section
        assert "YOU: Alice Developer" in roster
        # But not in teammates list (check that Alice doesn't appear after "YOUR TEAMMATES:")
        teammates_section = roster.split("YOUR TEAMMATES:")[1] if "YOUR TEAMMATES:" in roster else ""
        assert "Alice Developer" not in teammates_section or teammates_section.count("Alice Developer") == 0
    
    def test_team_roster_list_structure(self, sample_worker, sample_team):
        """Test that team roster list has correct structure."""
        builder = ContextBuilder(locale="en")
        
        context = builder.build_planning_context(
            worker=sample_worker,
            tick=100,
            reason="start",
            project_plan="plan",
            daily_plan="daily",
            team=sample_team,
        )
        
        roster_list = context["team_roster_list"]
        assert isinstance(roster_list, list)
        assert len(roster_list) == 2  # Excludes worker
        
        for member in roster_list:
            assert "name" in member
            assert "role" in member
            assert "email" in member
            assert "chat_handle" in member
