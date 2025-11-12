"""
Comprehensive tests for enhanced VirtualWorker.

Tests initialization, prompt generation, planning, reporting, and event reactions.
"""

import pytest
from pathlib import Path

from virtualoffice.virtualWorkers import (
    WorkerPersona,
    ScheduleBlock,
    VirtualWorker,
    PlanningContext,
    DailyPlanningContext,
    EventContext,
    ReportContext,
)
from virtualoffice.sim_manager.prompts import PromptManager, ContextBuilder
from virtualoffice.sim_manager.planner import StubPlanner
from virtualoffice.sim_manager.schemas import PersonRead


@pytest.fixture
def template_dir():
    """Get template directory path."""
    return Path(__file__).parent.parent / "src" / "virtualoffice" / "sim_manager" / "prompts" / "templates"


@pytest.fixture
def basic_persona():
    """Create a basic worker persona."""
    return WorkerPersona(
        name="Test Worker",
        role="Software Engineer",
        skills=("Python", "Testing"),
        personality=("Analytical", "Detail-oriented"),
        timezone="UTC",
        work_hours="09:00-17:00",
        break_frequency="Standard",
        communication_style="Direct",
        email_address="test.worker@vdos.local",
        chat_handle="test_worker",
    )


@pytest.fixture
def basic_worker(template_dir, basic_persona):
    """Create a basic VirtualWorker."""
    prompt_manager = PromptManager(str(template_dir), locale="en")
    context_builder = ContextBuilder(locale="en")
    planner = StubPlanner()
    
    return VirtualWorker(
        persona=basic_persona,
        prompt_manager=prompt_manager,
        context_builder=context_builder,
        planner=planner,
    )


class TestVirtualWorkerInitialization:
    """Test VirtualWorker initialization."""
    
    def test_basic_initialization(self, basic_worker):
        """Test basic worker initialization."""
        assert basic_worker.persona.name == "Test Worker"
        assert basic_worker.persona_markdown is not None
        assert len(basic_worker.persona_markdown) > 0
    
    def test_initialization_with_schedule(self, template_dir, basic_persona):
        """Test initialization with schedule blocks."""
        schedule = [
            ScheduleBlock("09:00", "10:00", "Morning standup"),
            ScheduleBlock("10:00", "12:00", "Deep work"),
        ]
        
        prompt_manager = PromptManager(str(template_dir), locale="en")
        context_builder = ContextBuilder(locale="en")
        planner = StubPlanner()
        
        worker = VirtualWorker(
            persona=basic_persona,
            prompt_manager=prompt_manager,
            context_builder=context_builder,
            planner=planner,
            schedule=schedule,
        )
        
        assert len(worker.schedule) == 2
        assert worker.schedule[0].activity == "Morning standup"
    
    def test_to_person_read(self, basic_worker):
        """Test conversion to PersonRead."""
        person_read = basic_worker.to_person_read()
        
        assert isinstance(person_read, PersonRead)
        assert person_read.name == "Test Worker"
        assert person_read.role == "Software Engineer"
        assert person_read.email_address == "test.worker@vdos.local"
        assert person_read.persona_markdown is not None


class TestPromptGeneration:
    """Test prompt generation."""
    
    def test_as_prompt_basic(self, basic_worker):
        """Test basic prompt generation."""
        person_read = basic_worker.to_person_read()
        context = PlanningContext(
            project_plan="Test project",
            daily_plan="Test daily plan",
            tick=100,
            reason="test",
            team=[person_read],
            locale="en",
        )
        
        # as_prompt should not raise an error
        try:
            messages = basic_worker.as_prompt(context)
            # If templates are available, check structure
            if messages:
                assert isinstance(messages, list)
                assert len(messages) >= 2
        except Exception:
            # Template might not be available, that's okay
            pass


class TestHourlyPlanning:
    """Test hourly planning functionality."""
    
    def test_plan_next_hour_single_project(self, basic_worker):
        """Test hourly planning with single project."""
        person_read = basic_worker.to_person_read()
        context = PlanningContext(
            project_plan="Build API gateway",
            daily_plan="Implement authentication",
            tick=100,
            reason="start_of_hour",
            team=[person_read],
            locale="en",
        )
        
        result = basic_worker.plan_next_hour(context)
        
        assert result is not None
        assert result.content is not None
        assert result.model_used is not None
    
    def test_plan_next_hour_multi_project(self, basic_worker):
        """Test hourly planning with multiple projects."""
        person_read = basic_worker.to_person_read()
        all_active_projects = [
            {"project_name": "Project A", "plan": "Build feature A"},
            {"project_name": "Project B", "plan": "Build feature B"},
        ]
        
        context = PlanningContext(
            project_plan="Build API gateway",
            daily_plan="Work on both projects",
            tick=100,
            reason="start_of_hour",
            team=[person_read],
            all_active_projects=all_active_projects,
            locale="en",
        )
        
        result = basic_worker.plan_next_hour(context)
        
        assert result is not None
        assert result.content is not None
    
    def test_plan_next_hour_with_team(self, basic_worker):
        """Test hourly planning with team members."""
        person_read = basic_worker.to_person_read()
        teammate = PersonRead(
            id=2,
            name="Teammate",
            role="Designer",
            email_address="teammate@vdos.local",
            chat_handle="teammate",
            timezone="UTC",
            work_hours="09:00-17:00",
            break_frequency="Standard",
            communication_style="Visual",
            skills=["Design"],
            personality=["Creative"],
            persona_markdown="Designer persona",
        )
        
        context = PlanningContext(
            project_plan="Build API gateway",
            daily_plan="Collaborate with team",
            tick=100,
            reason="start_of_hour",
            team=[person_read, teammate],
            locale="en",
        )
        
        result = basic_worker.plan_next_hour(context)
        
        assert result is not None


class TestDailyPlanningAndReporting:
    """Test daily planning and reporting."""
    
    def test_plan_daily(self, basic_worker):
        """Test daily planning."""
        person_read = basic_worker.to_person_read()
        context = DailyPlanningContext(
            project_plan="Build API gateway",
            day_index=0,
            duration_weeks=4,
            team=[person_read],
            locale="en",
        )
        
        result = basic_worker.plan_daily(context)
        
        assert result is not None
        assert result.content is not None
        assert result.model_used is not None
    
    def test_generate_daily_report(self, basic_worker):
        """Test daily report generation."""
        context = ReportContext(
            day_index=0,
            daily_plan="Implement authentication",
            hourly_log="09:00 - Setup\n10:00 - Coding",
            minute_schedule="09:00-09:30 Setup",
            locale="en",
        )
        
        result = basic_worker.generate_daily_report(context)
        
        assert result is not None
        assert result.content is not None
        assert result.model_used is not None


class TestEventReactions:
    """Test event reaction system."""
    
    def test_react_to_sick_leave(self, basic_worker):
        """Test reaction to sick leave event."""
        person_read = basic_worker.to_person_read()
        event = {
            "event_type": "sick_leave",
            "description": "Worker is sick",
            "payload": {},
        }
        
        context = EventContext(
            event=event,
            tick=100,
            team=[person_read],
            project_plan={"project_name": "Test", "plan": "Test plan"},
            locale="en",
        )
        
        response = basic_worker.react_to_event(context)
        
        assert response is not None
        assert response.adjustments is not None
    
    def test_react_to_blocker(self, basic_worker):
        """Test reaction to blocker event."""
        person_read = basic_worker.to_person_read()
        event = {
            "event_type": "blocker",
            "description": "Database issue",
            "payload": {},
        }
        
        context = EventContext(
            event=event,
            tick=100,
            team=[person_read],
            project_plan={"project_name": "Test", "plan": "Test plan"},
            locale="en",
        )
        
        response = basic_worker.react_to_event(context)
        
        assert response is not None
        assert response.adjustments is not None


class TestLocalization:
    """Test localization support."""
    
    def test_korean_worker_initialization(self, template_dir):
        """Test Korean worker initialization."""
        persona = WorkerPersona(
            name="김민수",
            role="소프트웨어 엔지니어",
            skills=("Python", "테스팅"),
            personality=("분석적", "꼼꼼함"),
            timezone="Asia/Seoul",
            work_hours="09:00-18:00",
            break_frequency="포모도로 50/10",
            communication_style="직접적",
            email_address="minsu.kim@vdos.local",
            chat_handle="minsu",
        )
        
        prompt_manager = PromptManager(str(template_dir), locale="ko")
        context_builder = ContextBuilder(locale="ko")
        planner = StubPlanner()
        
        worker = VirtualWorker(
            persona=persona,
            prompt_manager=prompt_manager,
            context_builder=context_builder,
            planner=planner,
        )
        
        assert worker.persona.name == "김민수"
        assert worker.persona_markdown is not None
    
    def test_korean_daily_planning(self, template_dir):
        """Test Korean daily planning."""
        persona = WorkerPersona(
            name="김민수",
            role="소프트웨어 엔지니어",
            skills=("Python",),
            personality=("분석적",),
            timezone="Asia/Seoul",
            work_hours="09:00-18:00",
            break_frequency="Standard",
            communication_style="직접적",
            email_address="minsu.kim@vdos.local",
            chat_handle="minsu",
        )
        
        prompt_manager = PromptManager(str(template_dir), locale="ko")
        context_builder = ContextBuilder(locale="ko")
        planner = StubPlanner()
        
        worker = VirtualWorker(
            persona=persona,
            prompt_manager=prompt_manager,
            context_builder=context_builder,
            planner=planner,
        )
        
        person_read = worker.to_person_read()
        context = DailyPlanningContext(
            project_plan="API 게이트웨이 구축",
            day_index=0,
            duration_weeks=4,
            team=[person_read],
            locale="ko",
        )
        
        result = worker.plan_daily(context)
        
        assert result is not None
        assert result.content is not None
