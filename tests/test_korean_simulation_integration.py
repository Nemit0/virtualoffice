"""
Integration tests for Korean localization functionality

Tests that validate Korean localization components work together properly
and that the localization system integrates correctly with the simulation.
"""

import os
import pytest
from virtualoffice.common.korean_validation import KoreanContentValidator
from virtualoffice.common.localization import LocalizationManager, get_current_locale_manager
from virtualoffice.common.korean_templates import KoreanPrompts, KoreanContentTemplates


class MockKoreanPlanner:
    """Mock planner that generates Korean content for testing"""
    
    def __init__(self):
        self.localization_manager = LocalizationManager("ko")
    
    def generate_hourly_plan_content(self, worker_name: str, tick: int = 0, reason: str = "테스트") -> str:
        """Generate Korean hourly plan content for testing"""
        scheduled_comm = self.localization_manager.get_text("scheduled_communications")
        
        content = f"""
{worker_name}님의 {tick}시간 계획:

{scheduled_comm}:
- 팀원들과 진행 상황 공유
- 프로젝트 업데이트 이메일 발송
- 일일 스탠드업 참여

작업 계획:
- 디자인 시안 검토
- 코드 리뷰 진행
- 문서 업데이트

사유: {reason}
        """.strip()
        
        return content


class TestKoreanLocalizationIntegration:
    """Integration tests for Korean localization functionality"""
    
    def test_localization_manager_environment_integration(self, monkeypatch):
        """Test LocalizationManager integrates with VDOS_LOCALE environment variable"""
        # Test default (English)
        monkeypatch.delenv("VDOS_LOCALE", raising=False)
        manager = get_current_locale_manager()
        assert manager.locale == "en"
        assert manager.get_text("scheduled_communications") == "Scheduled Communications"
        
        # Test Korean locale
        monkeypatch.setenv("VDOS_LOCALE", "ko")
        manager = get_current_locale_manager()
        assert manager.locale == "ko"
        assert manager.get_text("scheduled_communications") == "예정된 커뮤니케이션"
        assert manager.get_text("live_collaboration_adjustments") == "실시간 협업 조정사항"
    
    def test_korean_planner_content_generation(self):
        """Test that Korean planner generates proper Korean content"""
        planner = MockKoreanPlanner()
        
        # Generate hourly plan content
        content = planner.generate_hourly_plan_content("김민수", tick=1, reason="테스트")
        
        # Validate content is Korean
        validator = KoreanContentValidator()
        is_valid, issues = validator.validate_korean_content(content)
        assert is_valid, f"Generated content contains English: {issues}"
        
        # Check for localized strings
        assert "예정된 커뮤니케이션" in content, "Should use Korean 'Scheduled Communications'"
        assert "Scheduled Communications" not in content, "Should not contain English 'Scheduled Communications'"
        
        # Check for Korean structure
        assert "김민수님의" in content, "Should use Korean name with honorific"
        assert "시간 계획" in content, "Should use Korean time planning terminology"
    
    def test_korean_validation_with_templates(self):
        """Test Korean validation works with Korean templates"""
        validator = KoreanContentValidator(strict_mode=False)  # Use lenient mode for templates
        
        # Test Korean feature requests - these are short phrases, so use basic Korean character check
        for request in KoreanContentTemplates.CLIENT_FEATURE_REQUESTS:
            # For short phrases, just check they contain Korean characters
            has_korean = any('\uAC00' <= char <= '\uD7AF' for char in request)
            assert has_korean, f"Korean feature request should contain Korean characters: {request}"
            
            # Check they don't contain obvious English words
            english_issues = validator.detect_english_text(request)
            major_english_issues = [issue for issue in english_issues if 'Mixed Korean-English' not in issue[1]]
            assert len(major_english_issues) == 0, f"Korean feature request contains English words: {request} - {major_english_issues}"
        
        # Test Korean workplace tasks
        for task in KoreanContentTemplates.WORKPLACE_TASKS:
            has_korean = any('\uAC00' <= char <= '\uD7AF' for char in task)
            assert has_korean, f"Korean workplace task should contain Korean characters: {task}"
        
        # Test Korean communication templates
        for greeting in KoreanContentTemplates.CHAT_GREETINGS:
            has_korean = any('\uAC00' <= char <= '\uD7AF' for char in greeting)
            assert has_korean, f"Korean chat greeting should contain Korean characters: {greeting}"
    
    def test_korean_prompts_integration(self):
        """Test Korean prompts generate appropriate instructions"""
        # Test different prompt contexts
        contexts = ["general", "business", "project", "communication", "comprehensive"]
        
        for context in contexts:
            prompt = KoreanPrompts.get_enhanced_korean_prompt(context)
            
            # All prompts should contain Korean language enforcement
            assert "자연스러운 한국어" in prompt, f"Prompt for {context} should enforce Korean"
            assert "영어 단어나 표현을 절대 사용하지 마세요" in prompt, f"Prompt for {context} should prohibit English"
            
            # Check that prompt is primarily Korean (contains Korean characters)
            has_korean = any('\uAC00' <= char <= '\uD7AF' for char in prompt)
            assert has_korean, f"Korean prompt for {context} should contain Korean characters"
            
            # Check that the main instruction is in Korean
            korean_instruction_phrases = [
                "자연스러운 한국어",
                "영어 단어나 표현을 절대 사용하지 마세요",
                "한국 직장에서"
            ]
            
            found_korean_instructions = sum(1 for phrase in korean_instruction_phrases if phrase in prompt)
            assert found_korean_instructions >= 2, f"Korean prompt for {context} should contain Korean instructions"
    
    def test_localization_string_completeness(self):
        """Test that all required localization strings are present"""
        manager_en = LocalizationManager("en")
        manager_ko = LocalizationManager("ko")
        
        # Key strings that must be localized
        required_keys = [
            "scheduled_communications",
            "live_collaboration_adjustments",
            "client_feature_requests",
            "status_working",
            "status_away",
            "email_subject_update",
            "chat_greeting"
        ]
        
        for key in required_keys:
            # English version should exist
            en_text = manager_en.get_text(key)
            assert en_text, f"English text missing for key: {key}"
            
            # Korean version should exist
            ko_text = manager_ko.get_text(key)
            assert ko_text, f"Korean text missing for key: {key}"
            
            # Korean and English should be different
            assert en_text != ko_text, f"Korean and English text are the same for key: {key}"
            
            # Korean text should contain Korean characters
            if isinstance(ko_text, str):
                assert any('\uAC00' <= char <= '\uD7AF' for char in ko_text), f"Korean text for {key} doesn't contain Korean characters: {ko_text}"
    
    def test_korean_content_templates_integration(self):
        """Test Korean content templates work together properly"""
        # Test name generation
        korean_name = KoreanContentTemplates.get_korean_name()
        assert len(korean_name) >= 3, "Korean names should be at least 3 characters"
        assert any('\uAC00' <= char <= '\uD7AF' for char in korean_name), "Korean name should contain Korean characters"
        
        # Test feature request generation
        feature_request = KoreanContentTemplates.get_random_feature_request()
        assert feature_request in KoreanContentTemplates.CLIENT_FEATURE_REQUESTS
        
        # Test email subject generation
        email_subject = KoreanContentTemplates.get_email_subject_template("테스트 프로젝트")
        assert "테스트 프로젝트" in email_subject, "Email subject should contain project name"
        assert any('\uAC00' <= char <= '\uD7AF' for char in email_subject), "Email subject should contain Korean characters"
        
        # Test project phrases
        status_update = KoreanContentTemplates.get_status_update()
        assert status_update in KoreanContentTemplates.PROJECT_TERMINOLOGY["status_updates"]
        
        meeting_phrase = KoreanContentTemplates.get_meeting_phrase()
        assert meeting_phrase in KoreanContentTemplates.PROJECT_TERMINOLOGY["meeting_phrases"]
    
    def test_korean_validation_edge_cases(self):
        """Test Korean validation handles edge cases properly"""
        validator = KoreanContentValidator()
        
        # Test mixed content that should fail
        mixed_content = "안녕하세요. This is a mixed message with English."
        is_valid, issues = validator.validate_korean_content(mixed_content)
        assert not is_valid, "Mixed Korean-English content should fail validation"
        assert len(issues) > 0, "Mixed content should have validation issues"
        
        # Test pure Korean content that should pass
        pure_korean = "안녕하세요. 프로젝트 진행 상황을 공유드립니다. 검토 부탁드립니다."
        is_valid, issues = validator.validate_korean_content(pure_korean)
        assert is_valid, f"Pure Korean content should pass validation: {issues}"
        
        # Test content with allowed English terms
        korean_with_api = "API 통합 작업을 진행합니다."
        is_valid, issues = validator.validate_korean_content(korean_with_api)
        # This might still fail due to insufficient Korean content ratio, but should not fail due to 'API'
        english_api_issues = [issue for issue in issues if 'api' in issue.lower()]
        assert len(english_api_issues) == 0, "API should be allowed in Korean content"
        
        # Test empty content
        is_valid, issues = validator.validate_korean_content("")
        assert not is_valid, "Empty content should fail validation"
        assert any("empty" in issue.lower() for issue in issues), "Empty content should have appropriate error message"
    
    def test_localization_fallback_behavior(self):
        """Test localization fallback behavior works correctly"""
        manager = LocalizationManager("ko")
        
        # Test existing key
        text = manager.get_text("scheduled_communications")
        assert text == "예정된 커뮤니케이션"
        
        # Test non-existent key should raise KeyError
        with pytest.raises(KeyError):
            manager.get_text("nonexistent_key")
        
        # Test list retrieval
        requests = manager.get_list("client_feature_requests")
        assert isinstance(requests, list)
        assert len(requests) > 0
        assert "메인 메시지 새로고침" in requests
        
        # Test template functionality
        template = manager.get_template("client_request_subject", feature="테스트 기능")
        assert "클라이언트 요청: 테스트 기능" == template