"""
Korean Content Templates for VDOS

Provides Korean-specific templates and prompts for workplace-appropriate
Korean communication patterns and language enforcement.
"""

from typing import Dict, List


class KoreanPrompts:
    """
    Enhanced Korean language enforcement prompts for different contexts.
    
    These prompts are designed to ensure natural, workplace-appropriate Korean
    content generation while preventing English text mixing.
    """
    
    # Strict Korean enforcement prompt
    STRICT_KOREAN = """모든 응답을 자연스러운 한국어로만 작성하세요. 
영어 단어나 표현을 절대 사용하지 마세요. 
한국 직장에서 실제로 사용하는 자연스럽고 간결한 말투로 작성하세요. 
기술 용어도 한국어로 번역하여 사용하세요.
예시: 'API 통합' (O), 'API integration' (X)
예시: '데이터베이스 설정' (O), 'database setup' (X)
예시: '프로젝트 관리' (O), 'project management' (X)"""

    # Business Korean formatting for workplace appropriateness
    BUSINESS_KOREAN = """한국 기업 환경에 적합한 공손하고 전문적인 한국어를 사용하세요.
상하 관계와 업무 맥락을 고려한 적절한 존댓말을 사용하세요.
이메일은 정중한 비즈니스 톤으로, 채팅은 친근하지만 예의 바른 톤으로 작성하세요.
업무 관련 용어는 한국 직장에서 실제로 사용하는 표현을 사용하세요.

이메일 예시:
- 안녕하세요, [이름]님
- 말씀드린 건에 대해 업데이트 드립니다
- 검토 후 의견 부탁드립니다
- 감사합니다

채팅 예시:
- 안녕하세요!
- 진행 상황 공유드려요
- 확인 부탁드립니다
- 수고하세요!"""

    # Project-specific Korean terminology
    PROJECT_KOREAN = """프로젝트 관련 커뮤니케이션에서는 다음 한국어 용어를 사용하세요:

기술 용어:
- 개발 환경 (development environment)
- 데이터베이스 (database)
- 사용자 인터페이스 (user interface)
- 백엔드/프론트엔드 (backend/frontend)
- 테스트 케이스 (test case)
- 배포 (deployment)
- 버그 수정 (bug fix)
- 기능 개발 (feature development)

업무 용어:
- 마일스톤 (milestone)
- 마감일 (deadline)
- 작업 항목 (task)
- 진행 상황 (progress)
- 차단 요소 (blocker)
- 의존성 (dependency)
- 우선순위 (priority)
- 리뷰 (review)"""

    # Korean communication patterns
    COMMUNICATION_PATTERNS = """한국 직장 커뮤니케이션 패턴을 따르세요:

이메일 구조:
1. 인사말: "안녕하세요, [이름]님"
2. 목적 명시: "[주제]에 대해 말씀드립니다"
3. 본문: 구체적인 내용과 요청사항
4. 마무리: "검토 부탁드립니다" 또는 "의견 주시면 감사하겠습니다"
5. 인사: "감사합니다"

채팅 메시지:
1. 간단한 인사: "안녕하세요!" 또는 "수고하세요!"
2. 핵심 내용: 간결하고 명확한 메시지
3. 요청사항: "확인 부탁드려요" 또는 "의견 있으시면 말씀해 주세요"

회의 관련:
- "회의 일정 조율 부탁드립니다"
- "회의록 공유드립니다"
- "논의 사항이 있어 연락드립니다"

상태 업데이트:
- "진행 상황 공유드립니다"
- "완료되었습니다"
- "지연될 것 같습니다"
- "도움이 필요합니다\""""

    @classmethod
    def get_enhanced_korean_prompt(cls, context: str = "general") -> str:
        """
        Get enhanced Korean language enforcement prompt for specific context.
        
        Args:
            context: Context type ("general", "business", "project", "communication")
            
        Returns:
            Enhanced Korean prompt string
        """
        base_prompt = cls.STRICT_KOREAN
        
        if context == "business":
            return f"{base_prompt}\n\n{cls.BUSINESS_KOREAN}"
        elif context == "project":
            return f"{base_prompt}\n\n{cls.PROJECT_KOREAN}"
        elif context == "communication":
            return f"{base_prompt}\n\n{cls.COMMUNICATION_PATTERNS}"
        elif context == "comprehensive":
            return f"{base_prompt}\n\n{cls.BUSINESS_KOREAN}\n\n{cls.PROJECT_KOREAN}\n\n{cls.COMMUNICATION_PATTERNS}"
        
        return base_prompt


class KoreanContentTemplates:
    """
    Korean-specific content templates for common workplace scenarios.
    """
    
    # Korean names for consistent usage (no romanization mixing)
    KOREAN_NAMES = {
        "male": [
            "김민수", "이준호", "박성현", "최동욱", "정재원",
            "강태현", "윤상우", "임현준", "조민재", "한지훈"
        ],
        "female": [
            "김지영", "이수진", "박민정", "최은영", "정혜원",
            "강소영", "윤미경", "임지은", "조예린", "한서연"
        ]
    }
    
    # Client feature requests in Korean
    CLIENT_FEATURE_REQUESTS = [
        "메인 메시지 새로고침",
        "런치 분석 대시보드 준비",
        "고객 후기 캐러셀 추가",
        "온보딩 가이드 제작",
        "사용자 피드백 시스템 구축",
        "모바일 앱 최적화",
        "데이터 시각화 개선",
        "보안 강화 작업",
        "성능 모니터링 도구 추가",
        "다국어 지원 기능",
        "결제 시스템 통합",
        "알림 기능 개선",
        "검색 기능 고도화",
        "사용자 권한 관리",
        "백업 시스템 구축"
    ]
    
    # Common workplace tasks in Korean
    WORKPLACE_TASKS = [
        "코드 리뷰 진행",
        "테스트 케이스 작성",
        "문서 업데이트",
        "버그 수정 작업",
        "기능 명세서 검토",
        "데이터베이스 스키마 설계",
        "API 문서 작성",
        "배포 스크립트 준비",
        "성능 테스트 실행",
        "사용자 가이드 작성"
    ]
    
    # Korean business communication patterns
    EMAIL_SUBJECTS = [
        "프로젝트 진행 상황 업데이트",
        "회의 일정 조율 요청",
        "검토 요청: [문서명]",
        "긴급: 조치 필요 사항",
        "완료 보고: [작업명]",
        "질문: [주제]",
        "제안: [내용]",
        "알림: [공지사항]"
    ]
    
    CHAT_GREETINGS = [
        "안녕하세요!",
        "수고하세요!",
        "안녕하세요 팀!",
        "좋은 아침입니다!",
        "오후에도 수고하세요!"
    ]
    
    CHAT_UPDATES = [
        "진행 상황 공유드려요",
        "간단한 업데이트입니다",
        "완료되었습니다",
        "확인 부탁드려요",
        "의견 있으시면 말씀해 주세요"
    ]
    
    # Korean project terminology and phrases
    PROJECT_TERMINOLOGY = {
        "status_updates": [
            "진행 중입니다",
            "검토 중입니다",
            "완료되었습니다",
            "지연되고 있습니다",
            "차단되었습니다",
            "테스트 중입니다",
            "배포 준비 중입니다"
        ],
        "meeting_phrases": [
            "회의 일정을 조율해 주세요",
            "회의록을 공유드립니다",
            "논의가 필요한 사항이 있습니다",
            "결정 사항을 알려드립니다",
            "다음 회의 안건입니다"
        ],
        "collaboration_phrases": [
            "협업이 필요합니다",
            "의견을 나누고 싶습니다",
            "도움이 필요합니다",
            "함께 검토해 주세요",
            "피드백 부탁드립니다"
        ],
        "technical_terms": [
            "개발 환경", "테스트 환경", "운영 환경",
            "데이터베이스", "서버", "클라이언트",
            "백엔드", "프론트엔드", "풀스택",
            "API", "SDK", "프레임워크",
            "라이브러리", "모듈", "컴포넌트"
        ]
    }
    
    @classmethod
    def get_random_feature_request(cls) -> str:
        """Get a random Korean client feature request."""
        import random
        return random.choice(cls.CLIENT_FEATURE_REQUESTS)
    
    @classmethod
    def get_random_task(cls) -> str:
        """Get a random Korean workplace task."""
        import random
        return random.choice(cls.WORKPLACE_TASKS)
    
    @classmethod
    def get_email_subject_template(cls, project_name: str = None) -> str:
        """Get Korean email subject template."""
        import random
        subject = random.choice(cls.EMAIL_SUBJECTS)
        if project_name:
            return f"[{project_name}] {subject}"
        return subject
    
    @classmethod
    def get_chat_greeting(cls) -> str:
        """Get Korean chat greeting."""
        import random
        return random.choice(cls.CHAT_GREETINGS)
    
    @classmethod
    def get_chat_update(cls) -> str:
        """Get Korean chat update phrase."""
        import random
        return random.choice(cls.CHAT_UPDATES)
    
    @classmethod
    def get_korean_name(cls, gender: str = None) -> str:
        """Get a Korean name without romanization."""
        import random
        if gender and gender.lower() in cls.KOREAN_NAMES:
            return random.choice(cls.KOREAN_NAMES[gender.lower()])
        # Return random name from all names
        all_names = cls.KOREAN_NAMES["male"] + cls.KOREAN_NAMES["female"]
        return random.choice(all_names)
    
    @classmethod
    def get_project_phrase(cls, category: str) -> str:
        """Get Korean project-related phrase by category."""
        import random
        if category in cls.PROJECT_TERMINOLOGY:
            return random.choice(cls.PROJECT_TERMINOLOGY[category])
        return "프로젝트 관련 업무"
    
    @classmethod
    def get_status_update(cls) -> str:
        """Get Korean status update phrase."""
        return cls.get_project_phrase("status_updates")
    
    @classmethod
    def get_meeting_phrase(cls) -> str:
        """Get Korean meeting-related phrase."""
        return cls.get_project_phrase("meeting_phrases")
    
    @classmethod
    def get_collaboration_phrase(cls) -> str:
        """Get Korean collaboration phrase."""
        return cls.get_project_phrase("collaboration_phrases")


# Convenience functions for easy access
def get_korean_prompt(context: str = "general") -> str:
    """Get enhanced Korean language enforcement prompt."""
    return KoreanPrompts.get_enhanced_korean_prompt(context)


def get_korean_feature_request() -> str:
    """Get a Korean client feature request."""
    return KoreanContentTemplates.get_random_feature_request()


def get_korean_task() -> str:
    """Get a Korean workplace task."""
    return KoreanContentTemplates.get_random_task()


def get_korean_name(gender: str = None) -> str:
    """Get a Korean name without romanization."""
    return KoreanContentTemplates.get_korean_name(gender)


def get_korean_status_update() -> str:
    """Get a Korean status update phrase."""
    return KoreanContentTemplates.get_status_update()


def get_korean_meeting_phrase() -> str:
    """Get a Korean meeting-related phrase."""
    return KoreanContentTemplates.get_meeting_phrase()


def get_korean_collaboration_phrase() -> str:
    """Get a Korean collaboration phrase."""
    return KoreanContentTemplates.get_collaboration_phrase()