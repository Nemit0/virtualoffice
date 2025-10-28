"""
Tests for LocalizationManager functionality and Korean content validation
"""

import os
import pytest
from virtualoffice.common.localization import (
    LocalizationManager, 
    get_text, 
    get_korean_text,
    get_current_locale_manager,
    get_current_locale_text
)
from virtualoffice.common.korean_validation import (
    KoreanContentValidator,
    validate_korean_content,
    detect_english_in_korean,
    suggest_korean_translation
)
from virtualoffice.common.korean_templates import (
    KoreanPrompts,
    KoreanContentTemplates,
    get_korean_prompt,
    get_korean_feature_request,
    get_korean_name
)


class TestLocalizationManager:
    """Test LocalizationManager class functionality"""
    
    def test_default_locale_is_english(self):
        """Test that default locale is English"""
        manager = LocalizationManager()
        assert manager.locale == "en"
        assert not manager.is_korean_locale()
    
    def test_korean_locale_initialization(self):
        """Test Korean locale initialization"""
        manager = LocalizationManager("ko")
        assert manager.locale == "ko"
        assert manager.is_korean_locale()
    
    def test_scheduled_communications_localization(self):
        """Test scheduled communications string localization"""
        en_manager = LocalizationManager("en")
        ko_manager = LocalizationManager("ko")
        
        assert en_manager.get_text("scheduled_communications") == "Scheduled Communications"
        assert ko_manager.get_text("scheduled_communications") == "예정된 커뮤니케이션"
    
    def test_live_collaboration_adjustments_localization(self):
        """Test live collaboration adjustments string localization"""
        en_manager = LocalizationManager("en")
        ko_manager = LocalizationManager("ko")
        
        assert en_manager.get_text("live_collaboration_adjustments") == "Adjustments from live collaboration"
        assert ko_manager.get_text("live_collaboration_adjustments") == "실시간 협업 조정사항"
    
    def test_client_feature_requests_localization(self):
        """Test client feature requests list localization"""
        en_manager = LocalizationManager("en")
        ko_manager = LocalizationManager("ko")
        
        en_features = en_manager.get_list("client_feature_requests")
        ko_features = ko_manager.get_list("client_feature_requests")
        
        assert "refresh hero messaging" in en_features
        assert "메인 메시지 새로고침" in ko_features
        assert len(en_features) == len(ko_features)
    
    def test_locale_switching(self):
        """Test locale switching functionality"""
        manager = LocalizationManager("en")
        assert manager.get_text("scheduled_communications") == "Scheduled Communications"
        
        manager.set_locale("ko")
        assert manager.get_text("scheduled_communications") == "예정된 커뮤니케이션"
    
    def test_invalid_locale_raises_error(self):
        """Test that invalid locale raises ValueError"""
        with pytest.raises(ValueError, match="Unsupported locale"):
            LocalizationManager("invalid")
    
    def test_invalid_key_raises_error(self):
        """Test that invalid key raises KeyError"""
        manager = LocalizationManager("en")
        with pytest.raises(KeyError, match="not found"):
            manager.get_text("nonexistent_key")
    
    def test_convenience_functions(self):
        """Test convenience functions work correctly"""
        assert get_text("scheduled_communications", "en") == "Scheduled Communications"
        assert get_text("scheduled_communications", "ko") == "예정된 커뮤니케이션"
        assert get_korean_text("scheduled_communications") == "예정된 커뮤니케이션"
    
    def test_get_available_locales(self):
        """Test getting available locales"""
        manager = LocalizationManager()
        locales = manager.get_available_locales()
        assert "en" in locales
        assert "ko" in locales
        assert len(locales) >= 2
    
    def test_current_locale_integration(self, monkeypatch):
        """Test integration with VDOS_LOCALE environment variable"""
        # Test default (English)
        monkeypatch.delenv("VDOS_LOCALE", raising=False)
        manager = get_current_locale_manager()
        assert manager.locale == "en"
        assert get_current_locale_text("scheduled_communications") == "Scheduled Communications"
        
        # Test Korean locale
        monkeypatch.setenv("VDOS_LOCALE", "ko")
        manager = get_current_locale_manager()
        assert manager.locale == "ko"
        assert get_current_locale_text("scheduled_communications") == "예정된 커뮤니케이션"


class TestKoreanContentValidator:
    """Test Korean content validation functionality"""
    
    def test_validator_initialization(self):
        """Test validator initialization with different modes"""
        validator = KoreanContentValidator()
        assert validator.strict_mode is True
        
        validator_lenient = KoreanContentValidator(strict_mode=False)
        assert validator_lenient.strict_mode is False
    
    def test_detect_english_words(self):
        """Test detection of English words in Korean content"""
        validator = KoreanContentValidator()
        
        # Pure Korean content should have no issues
        korean_content = "안녕하세요. 프로젝트 진행 상황을 공유드립니다."
        issues = validator.detect_english_text(korean_content)
        assert len(issues) == 0
        
        # Mixed content should be detected
        mixed_content = "안녕하세요. project 진행 상황을 공유드립니다."
        issues = validator.detect_english_text(mixed_content)
        assert len(issues) > 0
        assert any("project" in issue[0] for issue in issues)
    
    def test_detect_english_phrases(self):
        """Test detection of English phrases and patterns"""
        validator = KoreanContentValidator()
        
        # English sentence patterns
        mixed_content = "안녕하세요. We need to update the database."
        issues = validator.detect_english_text(mixed_content)
        assert len(issues) > 0
        
        # English verb patterns
        mixed_content = "프로젝트가 running 중입니다."
        issues = validator.detect_english_text(mixed_content)
        assert len(issues) > 0
    
    def test_allowed_english_terms(self):
        """Test that allowed English terms don't trigger validation errors"""
        validator = KoreanContentValidator()
        
        # API and common tech abbreviations should be allowed
        content_with_api = "API 통합 작업을 진행합니다."
        issues = validator.detect_english_text(content_with_api)
        # Should not detect 'api' as an issue since it's in allowed list
        api_issues = [issue for issue in issues if 'api' in issue[0].lower()]
        assert len(api_issues) == 0
    
    def test_validate_korean_content(self):
        """Test comprehensive Korean content validation"""
        validator = KoreanContentValidator()
        
        # Valid Korean content
        valid_content = "안녕하세요. 프로젝트 진행 상황을 공유드립니다. 검토 부탁드립니다."
        is_valid, issues = validator.validate_korean_content(valid_content)
        assert is_valid is True
        assert len(issues) == 0
        
        # Invalid mixed content
        invalid_content = "Hello. project status update입니다."
        is_valid, issues = validator.validate_korean_content(invalid_content)
        assert is_valid is False
        assert len(issues) > 0
        
        # Empty content
        is_valid, issues = validator.validate_korean_content("")
        assert is_valid is False
        assert "empty" in issues[0].lower()
    
    def test_korean_structure_detection(self):
        """Test detection of proper Korean sentence structure"""
        validator = KoreanContentValidator()
        
        # Content with Korean endings
        content_with_endings = "프로젝트를 진행합니다."
        assert validator._has_proper_korean_structure(content_with_endings) is True
        
        # Content with Korean particles
        content_with_particles = "프로젝트가 진행 중이에요."
        assert validator._has_proper_korean_structure(content_with_particles) is True
        
        # English-only content
        english_content = "This is English content."
        assert validator._has_proper_korean_structure(english_content) is False
    
    def test_suggest_korean_alternatives(self):
        """Test Korean translation suggestions"""
        validator = KoreanContentValidator()
        
        # Test known translations
        suggestions = validator.suggest_korean_alternatives("project")
        assert "프로젝트" in suggestions
        
        suggestions = validator.suggest_korean_alternatives("database")
        assert "데이터베이스" in suggestions
        
        # Test unknown terms
        suggestions = validator.suggest_korean_alternatives("unknownterm")
        assert len(suggestions) > 0
        assert any("한국어" in suggestion for suggestion in suggestions)
    
    def test_convenience_functions(self):
        """Test convenience functions for Korean validation"""
        # Test validate_korean_content function
        is_valid, issues = validate_korean_content("안녕하세요. 프로젝트 진행 중입니다.")
        assert is_valid is True
        
        # Test detect_english_in_korean function
        issues = detect_english_in_korean("안녕하세요. project 진행 중입니다.")
        assert len(issues) > 0
        
        # Test suggest_korean_translation function
        suggestions = suggest_korean_translation("meeting")
        assert "회의" in suggestions


class TestKoreanContentTemplates:
    """Test Korean content templates and prompts"""
    
    def test_korean_prompts(self):
        """Test Korean language enforcement prompts"""
        # Test basic strict Korean prompt
        prompt = KoreanPrompts.get_enhanced_korean_prompt("general")
        assert "자연스러운 한국어" in prompt
        assert "영어 단어나 표현을 절대 사용하지 마세요" in prompt
        
        # Test business context prompt
        business_prompt = KoreanPrompts.get_enhanced_korean_prompt("business")
        assert "공손하고 전문적인 한국어" in business_prompt
        assert "존댓말" in business_prompt
        
        # Test project context prompt
        project_prompt = KoreanPrompts.get_enhanced_korean_prompt("project")
        assert "프로젝트 관련" in project_prompt
        assert "개발 환경" in project_prompt
        
        # Test comprehensive prompt
        comprehensive_prompt = KoreanPrompts.get_enhanced_korean_prompt("comprehensive")
        assert "자연스러운 한국어" in comprehensive_prompt
        assert "공손하고 전문적인 한국어" in comprehensive_prompt
        assert "프로젝트 관련" in comprehensive_prompt
    
    def test_korean_names(self):
        """Test Korean name generation without romanization"""
        # Test male names
        male_names = KoreanContentTemplates.KOREAN_NAMES["male"]
        assert all("김" in name or "이" in name or "박" in name or "최" in name or "정" in name 
                  or "강" in name or "윤" in name or "임" in name or "조" in name or "한" in name 
                  for name in male_names)
        
        # Test female names
        female_names = KoreanContentTemplates.KOREAN_NAMES["female"]
        assert all("김" in name or "이" in name or "박" in name or "최" in name or "정" in name 
                  or "강" in name or "윤" in name or "임" in name or "조" in name or "한" in name 
                  for name in female_names)
        
        # Test random name generation
        name = KoreanContentTemplates.get_korean_name()
        assert len(name) >= 3  # Korean names are typically 3 characters
        assert any(char in "김이박최정강윤임조한" for char in name)
        
        # Test gender-specific name generation
        male_name = KoreanContentTemplates.get_korean_name("male")
        assert male_name in male_names
        
        female_name = KoreanContentTemplates.get_korean_name("female")
        assert female_name in female_names
    
    def test_client_feature_requests(self):
        """Test Korean client feature request templates"""
        requests = KoreanContentTemplates.CLIENT_FEATURE_REQUESTS
        assert len(requests) > 0
        
        # All requests should be in Korean
        for request in requests:
            assert any('\uAC00' <= char <= '\uD7AF' for char in request)  # Korean Unicode range
            # Should not contain common English words
            assert "feature" not in request.lower()
            assert "request" not in request.lower()
        
        # Test random request generation
        random_request = KoreanContentTemplates.get_random_feature_request()
        assert random_request in requests
    
    def test_workplace_tasks(self):
        """Test Korean workplace task templates"""
        tasks = KoreanContentTemplates.WORKPLACE_TASKS
        assert len(tasks) > 0
        
        # All tasks should be in Korean
        for task in tasks:
            assert any('\uAC00' <= char <= '\uD7AF' for char in task)  # Korean Unicode range
        
        # Test random task generation
        random_task = KoreanContentTemplates.get_random_task()
        assert random_task in tasks
    
    def test_communication_templates(self):
        """Test Korean communication templates"""
        # Test email subjects
        subjects = KoreanContentTemplates.EMAIL_SUBJECTS
        assert len(subjects) > 0
        for subject in subjects:
            assert any('\uAC00' <= char <= '\uD7AF' for char in subject)  # Korean Unicode range
        
        # Test chat greetings
        greetings = KoreanContentTemplates.CHAT_GREETINGS
        assert len(greetings) > 0
        for greeting in greetings:
            assert any('\uAC00' <= char <= '\uD7AF' for char in greeting)  # Korean Unicode range
        
        # Test chat updates
        updates = KoreanContentTemplates.CHAT_UPDATES
        assert len(updates) > 0
        for update in updates:
            assert any('\uAC00' <= char <= '\uD7AF' for char in update)  # Korean Unicode range
    
    def test_project_terminology(self):
        """Test Korean project terminology"""
        terminology = KoreanContentTemplates.PROJECT_TERMINOLOGY
        
        # Test status updates
        status_updates = terminology["status_updates"]
        assert len(status_updates) > 0
        for status in status_updates:
            assert any('\uAC00' <= char <= '\uD7AF' for char in status)  # Korean Unicode range
        
        # Test meeting phrases
        meeting_phrases = terminology["meeting_phrases"]
        assert len(meeting_phrases) > 0
        for phrase in meeting_phrases:
            assert any('\uAC00' <= char <= '\uD7AF' for char in phrase)  # Korean Unicode range
        
        # Test collaboration phrases
        collaboration_phrases = terminology["collaboration_phrases"]
        assert len(collaboration_phrases) > 0
        for phrase in collaboration_phrases:
            assert any('\uAC00' <= char <= '\uD7AF' for char in phrase)  # Korean Unicode range
    
    def test_convenience_functions(self):
        """Test convenience functions for Korean templates"""
        # Test prompt function
        prompt = get_korean_prompt("business")
        assert "한국어" in prompt
        
        # Test feature request function
        request = get_korean_feature_request()
        assert request in KoreanContentTemplates.CLIENT_FEATURE_REQUESTS
        
        # Test name function
        name = get_korean_name()
        assert len(name) >= 3
        assert any(char in "김이박최정강윤임조한" for char in name)


class TestPlannerKoreanIntegration:
    """Test planner Korean content generation integration"""
    
    def test_localization_manager_integration(self):
        """Test that LocalizationManager integrates properly with planner needs"""
        manager = LocalizationManager("ko")
        
        # Test key strings that planner uses
        assert manager.get_text("scheduled_communications") == "예정된 커뮤니케이션"
        assert manager.get_text("live_collaboration_adjustments") == "실시간 협업 조정사항"
        
        # Test client feature requests
        requests = manager.get_list("client_feature_requests")
        assert len(requests) > 0
        assert "메인 메시지 새로고침" in requests
        
        # Test template functionality
        template = manager.get_template("client_request_subject", feature="테스트 기능")
        assert "클라이언트 요청: 테스트 기능" == template
    
    def test_korean_validation_for_planner_content(self):
        """Test Korean validation for typical planner-generated content"""
        validator = KoreanContentValidator()
        
        # Test typical planner output patterns
        planner_content = """
        예정된 커뮤니케이션:
        - 김민수님께 프로젝트 진행 상황 이메일 발송
        - 팀 채팅방에 일일 업데이트 공유
        - 클라이언트와 회의 일정 조율
        """
        
        is_valid, issues = validator.validate_korean_content(planner_content)
        assert is_valid is True
        assert len(issues) == 0
        
        # Test mixed content that should be caught
        mixed_planner_content = """
        Scheduled Communications:
        - Send email to 김민수님 about project status
        - Share daily update in team chat
        """
        
        is_valid, issues = validator.validate_korean_content(mixed_planner_content)
        assert is_valid is False
        assert len(issues) > 0