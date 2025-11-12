"""
Validation tests for template-based prompts.

Tests that template-based prompts produce equivalent or better results
compared to hard-coded prompts.
"""

import pytest
from pathlib import Path

from virtualoffice.sim_manager.prompts import PromptManager, ContextBuilder
from virtualoffice.sim_manager.schemas import PersonRead


@pytest.fixture
def template_dir():
    """Get the templates directory."""
    return Path(__file__).parent.parent.parent / "src" / "virtualoffice" / "sim_manager" / "prompts" / "templates"


@pytest.fixture
def sample_worker():
    """Create a sample worker for testing."""
    return PersonRead(
        id=1,
        name="Alice Developer",
        role="Senior Developer",
        email_address="alice@example.dev",
        chat_handle="alice_dev",
        timezone="America/New_York",
        work_hours="09:00-17:00",
        break_frequency="25/5",
        communication_style="Direct and collaborative",
        skills=["Python", "React", "API Design"],
        personality=["Detail-oriented", "Team player"],
        persona_markdown="Experienced full-stack developer with focus on Python and React. Detail-oriented and collaborative.",
    )


@pytest.fixture
def sample_team(sample_worker):
    """Create a sample team."""
    return [
        sample_worker,
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
            skills=["Design", "Figma"],
            personality=["Creative", "User-focused"],
            persona_markdown="Creative UI/UX designer focused on user experience.",
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
            skills=["Management", "Planning"],
            personality=["Leader", "Strategic"],
            persona_markdown="Strategic project manager with strong leadership skills.",
        ),
    ]


class TestTemplateLoading:
    """Test that all required templates can be loaded."""
    
    def test_hourly_planning_template_exists_en(self, template_dir):
        """Test that English hourly planning template exists and loads."""
        manager = PromptManager(str(template_dir), locale="en")
        template = manager.load_template("hourly")
        
        assert template.name == "hourly_planning_en"
        assert template.locale == "en"
        assert template.category == "planning"
        assert "operations coach" in template.system_prompt.lower()
    
    def test_hourly_planning_template_exists_ko(self, template_dir):
        """Test that Korean hourly planning template exists and loads."""
        manager = PromptManager(str(template_dir), locale="ko")
        template = manager.load_template("hourly")
        
        assert template.name == "hourly_planning_ko"
        assert template.locale == "ko"
        assert template.category == "planning"
        assert "운영 코치" in template.system_prompt
    
    def test_daily_planning_template_exists_en(self, template_dir):
        """Test that English daily planning template exists and loads."""
        manager = PromptManager(str(template_dir), locale="en")
        template = manager.load_template("daily")
        
        assert template.name == "daily_planning_en"
        assert template.locale == "en"
        assert template.category == "planning"
    
    def test_daily_planning_template_exists_ko(self, template_dir):
        """Test that Korean daily planning template exists and loads."""
        manager = PromptManager(str(template_dir), locale="ko")
        template = manager.load_template("daily")
        
        assert template.name == "daily_planning_ko"
        assert template.locale == "ko"
        assert template.category == "planning"
    
    def test_daily_report_template_exists_en(self, template_dir):
        """Test that English daily report template exists and loads."""
        manager = PromptManager(str(template_dir), locale="en")
        template = manager.load_template("daily_report")
        
        assert template.name == "daily_report_en"
        assert template.locale == "en"
        assert template.category == "reporting"
    
    def test_daily_report_template_exists_ko(self, template_dir):
        """Test that Korean daily report template exists and loads."""
        manager = PromptManager(str(template_dir), locale="ko")
        template = manager.load_template("daily_report")
        
        assert template.name == "daily_report_ko"
        assert template.locale == "ko"
        assert template.category == "reporting"


class TestPromptConstruction:
    """Test that templates can construct valid prompts."""
    
    def test_hourly_planning_prompt_construction_en(self, template_dir, sample_worker, sample_team):
        """Test constructing hourly planning prompt in English."""
        manager = PromptManager(str(template_dir), locale="en")
        builder = ContextBuilder(locale="en")
        
        # Build context
        context = builder.build_planning_context(
            worker=sample_worker,
            tick=100,
            reason="start_of_hour",
            project_plan="Build mobile app MVP",
            daily_plan="Focus on API integration",
            team=sample_team,
        )
        
        # Add additional required fields
        context["project_reference"] = "Build mobile app MVP"
        context["valid_email_list"] = "\n".join(f"  - {m.email_address}" for m in sample_team if m.id != sample_worker.id)
        context["correct_examples"] = "- Email at 10:30 to bob@example.dev: Test | Test body"
        
        # Build prompt
        messages = manager.build_prompt("hourly", context)
        
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "Alice Developer" in messages[1]["content"]
        assert "tick 100" in messages[1]["content"]
        assert "Scheduled Communications" in messages[1]["content"]
    
    def test_hourly_planning_prompt_construction_ko(self, template_dir, sample_worker, sample_team):
        """Test constructing hourly planning prompt in Korean."""
        manager = PromptManager(str(template_dir), locale="ko")
        builder = ContextBuilder(locale="ko")
        
        # Build context
        context = builder.build_planning_context(
            worker=sample_worker,
            tick=100,
            reason="시작",
            project_plan="모바일 앱 MVP 구축",
            daily_plan="API 통합에 집중",
            team=sample_team,
        )
        
        # Add additional required fields
        context["project_reference"] = "모바일 앱 MVP 구축"
        context["valid_email_list"] = "\n".join(f"  - {m.email_address}" for m in sample_team if m.id != sample_worker.id)
        context["correct_examples"] = "- 이메일 10:30에 bob@example.dev: 테스트 | 테스트 본문"
        
        # Build prompt
        messages = manager.build_prompt("hourly", context)
        
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "Alice Developer" in messages[1]["content"]
        assert "틱 100" in messages[1]["content"]
        assert "예정된 커뮤니케이션" in messages[1]["content"]
    
    def test_daily_planning_prompt_construction_en(self, template_dir, sample_worker, sample_team):
        """Test constructing daily planning prompt in English."""
        manager = PromptManager(str(template_dir), locale="en")
        
        context = {
            "worker_name": sample_worker.name,
            "worker_role": sample_worker.role,
            "worker_timezone": sample_worker.timezone,
            "persona_markdown": sample_worker.persona_markdown,
            "team_roster": "Bob (Designer)\nCharlie (Manager)",
            "duration_weeks": 4,
            "day_number": 1,
            "project_plan": "Build mobile app MVP",
        }
        
        messages = manager.build_prompt("daily", context)
        
        assert len(messages) == 2
        assert "Alice Developer" in messages[1]["content"]
        assert "day 1" in messages[1]["content"]
        assert "Build mobile app MVP" in messages[1]["content"]
    
    def test_daily_report_prompt_construction_en(self, template_dir, sample_worker):
        """Test constructing daily report prompt in English."""
        manager = PromptManager(str(template_dir), locale="en")
        builder = ContextBuilder(locale="en")
        
        context = builder.build_reporting_context(
            worker=sample_worker,
            day_index=0,
            daily_plan="Focus on API integration",
            hourly_log="09:00 - Started API work\n10:00 - Completed auth module",
            minute_schedule="Detailed schedule",
        )
        
        messages = manager.build_prompt("daily_report", context)
        
        assert len(messages) == 2
        assert "Alice Developer" in messages[1]["content"]
        assert "day 1" in messages[1]["content"]
        assert "Focus on API integration" in messages[1]["content"]


class TestTemplateValidation:
    """Test that templates have all required sections and validation rules."""
    
    def test_hourly_template_has_required_sections(self, template_dir):
        """Test that hourly template has all required sections."""
        manager = PromptManager(str(template_dir), locale="en")
        template = manager.load_template("hourly")
        
        required_sections = [
            "persona_section",
            "team_roster_section",
            "recent_emails_section",
            "project_context_section",
            "format_templates_section",
            "email_guidelines_section",
            "email_rules_section",
            "valid_emails_section",
            "examples_section",
        ]
        
        for section in required_sections:
            assert section in template.sections, f"Missing section: {section}"
    
    def test_hourly_template_has_validation_rules(self, template_dir):
        """Test that hourly template has validation rules."""
        manager = PromptManager(str(template_dir), locale="en")
        template = manager.load_template("hourly")
        
        assert len(template.validation_rules) > 0
        assert any("worker name" in rule.lower() for rule in template.validation_rules)
        assert any("scheduled communications" in rule.lower() for rule in template.validation_rules)
    
    def test_daily_template_has_validation_rules(self, template_dir):
        """Test that daily template has validation rules."""
        manager = PromptManager(str(template_dir), locale="en")
        template = manager.load_template("daily")
        
        assert len(template.validation_rules) > 0
        assert any("worker name" in rule.lower() for rule in template.validation_rules)
        assert any("objectives" in rule.lower() for rule in template.validation_rules)
    
    def test_daily_report_template_has_validation_rules(self, template_dir):
        """Test that daily report template has validation rules."""
        manager = PromptManager(str(template_dir), locale="en")
        template = manager.load_template("daily_report")
        
        assert len(template.validation_rules) > 0
        assert any("worker name" in rule.lower() for rule in template.validation_rules)
        assert any("highlights" in rule.lower() for rule in template.validation_rules)


class TestLocaleConsistency:
    """Test that English and Korean templates are consistent."""
    
    def test_hourly_templates_have_same_sections(self, template_dir):
        """Test that English and Korean hourly templates have the same sections."""
        manager_en = PromptManager(str(template_dir), locale="en")
        manager_ko = PromptManager(str(template_dir), locale="ko")
        
        template_en = manager_en.load_template("hourly")
        template_ko = manager_ko.load_template("hourly")
        
        assert set(template_en.sections.keys()) == set(template_ko.sections.keys())
    
    def test_daily_templates_have_same_sections(self, template_dir):
        """Test that English and Korean daily templates have the same sections."""
        manager_en = PromptManager(str(template_dir), locale="en")
        manager_ko = PromptManager(str(template_dir), locale="ko")
        
        template_en = manager_en.load_template("daily")
        template_ko = manager_ko.load_template("daily")
        
        assert set(template_en.sections.keys()) == set(template_ko.sections.keys())
    
    def test_daily_report_templates_have_same_sections(self, template_dir):
        """Test that English and Korean daily report templates have the same sections."""
        manager_en = PromptManager(str(template_dir), locale="en")
        manager_ko = PromptManager(str(template_dir), locale="ko")
        
        template_en = manager_en.load_template("daily_report")
        template_ko = manager_ko.load_template("daily_report")
        
        assert set(template_en.sections.keys()) == set(template_ko.sections.keys())
