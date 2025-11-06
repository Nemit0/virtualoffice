"""
Unit tests for CommunicationGenerator.

Tests the GPT-powered fallback communication generation system.
"""

import json
import pytest
from unittest.mock import Mock, MagicMock

from virtualoffice.sim_manager.communication_generator import CommunicationGenerator
from virtualoffice.sim_manager.planner import PlanResult
from virtualoffice.sim_manager.schemas import PersonRead


@pytest.fixture
def mock_planner():
    """Create a mock planner for testing."""
    planner = Mock()
    return planner


@pytest.fixture
def sample_person():
    """Create a sample persona for testing."""
    return PersonRead(
        id=1,
        name="김개발",
        role="개발자",
        timezone="Asia/Seoul",
        work_hours="09:00-18:00",
        break_frequency="25/5,90/lunch/60",
        communication_style="직접적이고 기술적",
        email_address="kim@example.com",
        chat_handle="kim_dev",
        is_department_head=False,
        team_name="개발팀",
        skills=["Python", "FastAPI", "SQLite"],
        personality=["꼼꼼함", "논리적"],
        objectives=["고품질 코드 작성"],
        metrics=["코드 리뷰 완료율"],
        persona_markdown="# 김개발\n개발자",
        planning_guidelines=["테스트 작성"],
        event_playbook={},
        statuses=["working"]
    )


def test_communication_generator_initialization(mock_planner):
    """Test CommunicationGenerator initialization."""
    generator = CommunicationGenerator(
        planner=mock_planner,
        locale="ko",
        random_seed=42
    )
    
    assert generator.planner == mock_planner
    assert generator.locale == "ko"
    assert generator.random is not None


def test_build_context_basic(mock_planner, sample_person):
    """Test context building with basic information."""
    generator = CommunicationGenerator(mock_planner, locale="ko")
    
    context = generator._build_context(
        person=sample_person,
        hourly_plan="API 엔드포인트 개발 중",
        daily_plan="로그인 기능 구현",
        project={"project_name": "모바일앱", "project_summary": "모바일 앱 개발"},
        inbox_messages=None,
        collaborators=None
    )
    
    assert context["person_name"] == "김개발"
    assert context["person_role"] == "개발자"
    assert context["current_work"] == "API 엔드포인트 개발 중"
    assert context["daily_summary"] == "로그인 기능 구현"
    assert context["project_name"] == "모바일앱"
    assert context["locale"] == "ko"


def test_build_context_with_inbox(mock_planner, sample_person):
    """Test context building with inbox messages."""
    generator = CommunicationGenerator(mock_planner, locale="ko")
    
    inbox_messages = [
        {"sender_name": "박디자인", "subject": "UI 검토 요청"},
        {"sender_name": "이QA", "message": "버그 발견"}
    ]
    
    context = generator._build_context(
        person=sample_person,
        hourly_plan=None,
        daily_plan=None,
        project=None,
        inbox_messages=inbox_messages,
        collaborators=None
    )
    
    assert "박디자인" in context["inbox"]
    assert "UI 검토 요청" in context["inbox"]


def test_build_context_truncates_long_text(mock_planner, sample_person):
    """Test that long text fields are truncated."""
    generator = CommunicationGenerator(mock_planner, locale="ko")
    
    long_plan = "작업 " * 200  # Very long text
    
    context = generator._build_context(
        person=sample_person,
        hourly_plan=long_plan,
        daily_plan=None,
        project=None,
        inbox_messages=None,
        collaborators=None
    )
    
    assert len(context["current_work"]) <= 503  # 500 + "..."
    assert context["current_work"].endswith("...")


def test_build_korean_prompt(mock_planner, sample_person):
    """Test Korean prompt building."""
    generator = CommunicationGenerator(mock_planner, locale="ko")
    
    context = generator._build_context(
        person=sample_person,
        hourly_plan="API 개발",
        daily_plan=None,
        project={"project_name": "모바일앱"},
        inbox_messages=None,
        collaborators=None
    )
    
    messages = generator._build_korean_prompt(context)
    
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "김개발" in messages[0]["content"]
    assert "개발자" in messages[0]["content"]
    assert "JSON" in messages[1]["content"]


def test_build_english_prompt(mock_planner, sample_person):
    """Test English prompt building."""
    generator = CommunicationGenerator(mock_planner, locale="en")
    
    context = generator._build_context(
        person=sample_person,
        hourly_plan="API development",
        daily_plan=None,
        project={"project_name": "MobileApp"},
        inbox_messages=None,
        collaborators=None
    )
    
    messages = generator._build_english_prompt(context)
    
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "JSON" in messages[1]["content"]


def test_parse_gpt_response_valid_json(mock_planner):
    """Test parsing valid JSON response."""
    generator = CommunicationGenerator(mock_planner, locale="ko")
    
    response = json.dumps({
        "communications": [
            {
                "type": "email",
                "to": ["test@example.com"],
                "subject": "테스트",
                "body": "본문"
            },
            {
                "type": "chat",
                "target": "@user",
                "message": "메시지"
            }
        ]
    })
    
    communications = generator._parse_gpt_response(response)
    
    assert len(communications) == 2
    assert communications[0]["type"] == "email"
    assert communications[1]["type"] == "chat"


def test_parse_gpt_response_with_markdown(mock_planner):
    """Test parsing JSON in markdown code blocks."""
    generator = CommunicationGenerator(mock_planner, locale="ko")
    
    response = """```json
{
  "communications": [
    {
      "type": "email",
      "to": ["test@example.com"],
      "subject": "테스트",
      "body": "본문"
    }
  ]
}
```"""
    
    communications = generator._parse_gpt_response(response)
    
    assert len(communications) == 1
    assert communications[0]["type"] == "email"


def test_parse_gpt_response_invalid_json(mock_planner):
    """Test handling of invalid JSON."""
    generator = CommunicationGenerator(mock_planner, locale="ko")
    
    response = "This is not JSON"
    
    communications = generator._parse_gpt_response(response)
    
    assert communications == []


def test_parse_gpt_response_missing_fields(mock_planner):
    """Test handling of communications with missing required fields."""
    generator = CommunicationGenerator(mock_planner, locale="ko")
    
    response = json.dumps({
        "communications": [
            {
                "type": "email",
                "subject": "테스트"
                # Missing 'to' and 'body'
            },
            {
                "type": "chat",
                "target": "@user",
                "message": "메시지"
            }
        ]
    })
    
    communications = generator._parse_gpt_response(response)
    
    # Only the valid chat message should be returned
    assert len(communications) == 1
    assert communications[0]["type"] == "chat"


def test_generate_fallback_communications_success(mock_planner, sample_person):
    """Test successful fallback communication generation."""
    # Mock the planner response
    mock_result = PlanResult(
        content=json.dumps({
            "communications": [
                {
                    "type": "email",
                    "to": ["test@example.com"],
                    "subject": "[모바일앱] API 개발 완료",
                    "body": "API 엔드포인트 개발이 완료되었습니다."
                }
            ]
        }),
        model_used="gpt-4o-mini",
        tokens_used=150
    )
    mock_planner.generate_with_messages = Mock(return_value=mock_result)
    
    generator = CommunicationGenerator(mock_planner, locale="ko")
    
    communications = generator.generate_fallback_communications(
        person=sample_person,
        hourly_plan="API 엔드포인트 개발",
        project={"project_name": "모바일앱"}
    )
    
    assert len(communications) == 1
    assert communications[0]["type"] == "email"
    assert "모바일앱" in communications[0]["subject"]
    mock_planner.generate_with_messages.assert_called_once()


def test_generate_fallback_communications_error_handling(mock_planner, sample_person):
    """Test error handling in fallback communication generation."""
    # Mock the planner to raise an exception
    mock_planner.generate_with_messages = Mock(side_effect=Exception("API Error"))
    
    generator = CommunicationGenerator(mock_planner, locale="ko")
    
    communications = generator.generate_fallback_communications(
        person=sample_person,
        hourly_plan="API 개발"
    )
    
    # Should return empty list on error
    assert communications == []


def test_parse_gpt_response_converts_string_to_list(mock_planner):
    """Test that 'to' field is converted from string to list."""
    generator = CommunicationGenerator(mock_planner, locale="ko")
    
    response = json.dumps({
        "communications": [
            {
                "type": "email",
                "to": "test@example.com",  # String instead of list
                "subject": "테스트",
                "body": "본문"
            }
        ]
    })
    
    communications = generator._parse_gpt_response(response)
    
    assert len(communications) == 1
    assert isinstance(communications[0]["to"], list)
    assert communications[0]["to"] == ["test@example.com"]
