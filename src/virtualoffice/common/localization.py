"""
Localization Manager for VDOS

Provides centralized management of all localizable strings and templates
to ensure consistent Korean localization throughout the application.
"""

import os
from typing import Dict, List, Optional, Any


class LocalizationManager:
    """
    Centralized localization management for VDOS.
    
    Handles string retrieval based on locale settings and provides
    Korean translations for all hardcoded text in the system.
    """
    
    # Comprehensive localization strings dictionary
    LOCALIZATION_STRINGS: Dict[str, Dict[str, Any]] = {
        "en": {
            # Planner strings
            "scheduled_communications": "Scheduled Communications",
            
            # Engine strings
            "live_collaboration_adjustments": "Adjustments from live collaboration",
            
            # Client feature requests
            "client_feature_requests": [
                "refresh hero messaging",
                "prepare launch analytics dashboard", 
                "add testimonial carousel",
                "deliver onboarding walkthrough"
            ],
            
            # Common UI strings
            "status_working": "Working",
            "status_away": "Away",
            "status_off_duty": "Off Duty",
            "status_overtime": "Overtime",
            "status_sick_leave": "Sick Leave",
            "status_vacation": "Vacation",
            
            # Communication templates
            "email_subject_update": "Project Update",
            "email_subject_meeting": "Meeting Request",
            "email_subject_urgent": "Urgent: Action Required",
            "chat_greeting": "Hi team",
            "chat_update": "Quick update",
            
            # Client request templates
            "client_request_subject": "Client request: {feature}",
            "client_request_body": "Client requested {feature}. Align on next steps within this cycle.",
            "client_request_action": "Plan response to client request: {feature}.",
            
            # Event message templates
            "pending_adjustment": "Pending adjustment",
            "acknowledgement_from": "Acknowledgement from {name}",
            "update_for": "Update for {name}",
            "update_from_to": "Update: {from_name} → {to_name}",
            "update_generic": "Update: {name}",
            "rest_and_recover": "Rest and recover",
            "rest_and_recover_body": "Take the remainder of the day off to recover.",
            "rest_and_recover_action": "Pause all work and update once you are back online.",
            "coverage_needed": "Coverage needed: {name} is out sick",
            "coverage_needed_body": "{name} reported sick leave at tick {tick}. Please redistribute their urgent work.",
            "your_latest_update": "your latest update",
            "partner_with": "Partner with {name} on {feature}.",
            "support_on": "Support {name} on {feature}.",
            "no_hourly_activities": "No hourly activities recorded.",
            
            # Project terminology
            "project_milestone": "Milestone",
            "project_deadline": "Deadline",
            "project_task": "Task",
            "project_blocker": "Blocker",
            "project_dependency": "Dependency",
        },
        
        "ko": {
            # Planner strings
            "scheduled_communications": "예정된 커뮤니케이션",
            
            # Engine strings
            "live_collaboration_adjustments": "실시간 협업 조정사항",
            
            # Client feature requests (Korean workplace appropriate)
            "client_feature_requests": [
                "메인 메시지 새로고침",
                "런치 분석 대시보드 준비",
                "고객 후기 캐러셀 추가", 
                "온보딩 가이드 제작"
            ],
            
            # Common UI strings
            "status_working": "근무중",
            "status_away": "자리비움",
            "status_off_duty": "퇴근",
            "status_overtime": "야근",
            "status_sick_leave": "병가",
            "status_vacation": "휴가",
            
            # Communication templates
            "email_subject_update": "프로젝트 업데이트",
            "email_subject_meeting": "회의 요청",
            "email_subject_urgent": "긴급: 조치 필요",
            "chat_greeting": "안녕하세요 팀",
            "chat_update": "간단한 업데이트",
            
            # Client request templates
            "client_request_subject": "클라이언트 요청: {feature}",
            "client_request_body": "클라이언트가 {feature}을(를) 요청했습니다. 이번 주기 내에 다음 단계를 조율해주세요.",
            "client_request_action": "클라이언트 요청에 대한 대응 계획: {feature}.",
            
            # Event message templates
            "pending_adjustment": "보류 중인 조정사항",
            "acknowledgement_from": "{name}의 확인",
            "update_for": "{name}에 대한 업데이트",
            "update_from_to": "업데이트: {from_name} → {to_name}",
            "update_generic": "업데이트: {name}",
            "rest_and_recover": "휴식 및 회복",
            "rest_and_recover_body": "오늘 남은 시간은 회복을 위해 휴식하세요.",
            "rest_and_recover_action": "모든 업무를 중단하고 복귀 시 업데이트해주세요.",
            "coverage_needed": "업무 대행 필요: {name}이 병가 중입니다",
            "coverage_needed_body": "{name}이 {tick} 시점에 병가를 신고했습니다. 긴급 업무를 재분배해주세요.",
            "your_latest_update": "요청하신 내용",
            "partner_with": "{name}과 {feature}에 대해 협력하세요.",
            "support_on": "{name}의 {feature} 작업을 지원하세요.",
            "no_hourly_activities": "기록된 시간별 활동이 없습니다.",
            
            # Project terminology
            "project_milestone": "마일스톤",
            "project_deadline": "마감일",
            "project_task": "작업",
            "project_blocker": "차단 요소",
            "project_dependency": "의존성",
        }
    }
    
    def __init__(self, locale: str = "en"):
        """
        Initialize LocalizationManager with specified locale.
        
        Args:
            locale: Language code ("en" for English, "ko" for Korean)
        """
        self.locale = locale
        self._validate_locale()
    
    def _validate_locale(self) -> None:
        """Validate that the locale is supported."""
        if self.locale not in self.LOCALIZATION_STRINGS:
            raise ValueError(f"Unsupported locale: {self.locale}. Supported locales: {list(self.LOCALIZATION_STRINGS.keys())}")
    
    def get_text(self, key: str) -> str:
        """
        Get localized text for the given key.
        
        Args:
            key: The string key to look up
            
        Returns:
            Localized string for the current locale
            
        Raises:
            KeyError: If the key is not found in the localization strings
        """
        try:
            return self.LOCALIZATION_STRINGS[self.locale][key]
        except KeyError:
            # Fallback to English if key not found in current locale
            if self.locale != "en" and key in self.LOCALIZATION_STRINGS["en"]:
                return self.LOCALIZATION_STRINGS["en"][key]
            raise KeyError(f"Localization key '{key}' not found for locale '{self.locale}'")
    
    def get_list(self, key: str) -> List[str]:
        """
        Get localized list for the given key.
        
        Args:
            key: The list key to look up
            
        Returns:
            Localized list for the current locale
            
        Raises:
            KeyError: If the key is not found
            TypeError: If the value is not a list
        """
        value = self.get_text(key)
        if not isinstance(value, list):
            raise TypeError(f"Key '{key}' does not contain a list value")
        return value
    
    def get_template(self, template_name: str, **kwargs) -> str:
        """
        Get localized template with variable substitution.
        
        Args:
            template_name: The template key to look up
            **kwargs: Variables to substitute in the template
            
        Returns:
            Formatted template string
        """
        template = self.get_text(template_name)
        if kwargs:
            return template.format(**kwargs)
        return template
    
    def set_locale(self, locale: str) -> None:
        """
        Change the current locale.
        
        Args:
            locale: New locale to set
        """
        old_locale = self.locale
        self.locale = locale
        try:
            self._validate_locale()
        except ValueError:
            # Revert to old locale if new one is invalid
            self.locale = old_locale
            raise
    
    def get_available_locales(self) -> List[str]:
        """
        Get list of available locales.
        
        Returns:
            List of supported locale codes
        """
        return list(self.LOCALIZATION_STRINGS.keys())
    
    def is_korean_locale(self) -> bool:
        """
        Check if current locale is Korean.
        
        Returns:
            True if locale is Korean, False otherwise
        """
        return self.locale == "ko"
    
    def get_client_feature_request(self, index: Optional[int] = None) -> str:
        """
        Get a client feature request, optionally by index.
        
        Args:
            index: Optional index to get specific feature request
            
        Returns:
            Client feature request string
        """
        requests = self.get_list("client_feature_requests")
        if index is not None:
            if 0 <= index < len(requests):
                return requests[index]
            raise IndexError(f"Feature request index {index} out of range")
        
        # Return first request if no index specified
        return requests[0] if requests else ""


# Global instance for easy access
_default_manager = LocalizationManager()


def get_localization_manager(locale: Optional[str] = None) -> LocalizationManager:
    """
    Get a LocalizationManager instance.
    
    Args:
        locale: Optional locale to use. If None, returns default manager.
        
    Returns:
        LocalizationManager instance
    """
    if locale is None:
        return _default_manager
    return LocalizationManager(locale)


def get_text(key: str, locale: str = "en") -> str:
    """
    Convenience function to get localized text.
    
    Args:
        key: The string key to look up
        locale: Locale to use for lookup
        
    Returns:
        Localized string
    """
    manager = get_localization_manager(locale)
    return manager.get_text(key)


def get_korean_text(key: str) -> str:
    """
    Convenience function to get Korean localized text.
    
    Args:
        key: The string key to look up
        
    Returns:
        Korean localized string
    """
    return get_text(key, "ko")


def get_current_locale_manager() -> LocalizationManager:
    """
    Get LocalizationManager instance based on current VDOS_LOCALE environment variable.
    
    This function integrates with the existing VDOS locale system by reading
    the VDOS_LOCALE environment variable that's already used by planner and engine.
    
    Returns:
        LocalizationManager instance configured for current locale
    """
    current_locale = os.getenv("VDOS_LOCALE", "en").strip().lower() or "en"
    return LocalizationManager(current_locale)


def get_current_locale_text(key: str) -> str:
    """
    Get localized text using current VDOS_LOCALE environment variable.
    
    Args:
        key: The string key to look up
        
    Returns:
        Localized string for current VDOS locale
    """
    manager = get_current_locale_manager()
    return manager.get_text(key)