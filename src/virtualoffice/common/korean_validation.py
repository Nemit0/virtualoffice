"""
Korean Content Validation for VDOS

Provides validation utilities to detect English text in Korean content
and ensure natural Korean language generation.
"""

import re
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class KoreanContentValidator:
    """
    Validates Korean content to detect English text mixing and ensure
    natural Korean language generation.
    """
    
    # Common English words that should not appear in Korean content
    ENGLISH_WORDS = {
        # Technical terms that should be translated
        'api', 'database', 'server', 'client', 'frontend', 'backend',
        'framework', 'library', 'repository', 'deployment', 'testing',
        'debugging', 'development', 'production', 'staging', 'environment',
        'configuration', 'integration', 'authentication', 'authorization',
        'validation', 'optimization', 'performance', 'monitoring',
        'analytics', 'dashboard', 'interface', 'component', 'module',
        'service', 'endpoint', 'request', 'response', 'session',
        'cache', 'storage', 'backup', 'security', 'encryption',
        
        # Business terms
        'project', 'management', 'planning', 'schedule', 'deadline',
        'milestone', 'task', 'priority', 'blocker', 'dependency',
        'requirement', 'specification', 'documentation', 'review',
        'approval', 'feedback', 'meeting', 'presentation', 'report',
        'update', 'status', 'progress', 'completion', 'delivery',
        
        # Communication terms
        'email', 'chat', 'message', 'notification', 'alert',
        'communication', 'collaboration', 'coordination', 'sync',
        'discussion', 'decision', 'agreement', 'confirmation',
        
        # Common words
        'the', 'and', 'or', 'but', 'with', 'from', 'to', 'for',
        'in', 'on', 'at', 'by', 'of', 'is', 'are', 'was', 'were',
        'have', 'has', 'had', 'will', 'would', 'should', 'could',
        'can', 'may', 'might', 'must', 'shall', 'do', 'does', 'did',
        'get', 'got', 'make', 'made', 'take', 'took', 'give', 'gave',
        'go', 'went', 'come', 'came', 'see', 'saw', 'know', 'knew',
        'think', 'thought', 'say', 'said', 'tell', 'told', 'ask',
        'work', 'working', 'works', 'worked', 'need', 'needs', 'needed',
        'want', 'wants', 'wanted', 'like', 'likes', 'liked', 'help',
        'helps', 'helped', 'use', 'uses', 'used', 'find', 'found',
        'look', 'looks', 'looked', 'try', 'tries', 'tried', 'start',
        'starts', 'started', 'stop', 'stops', 'stopped', 'finish',
        'finished', 'complete', 'completed', 'ready', 'done'
    }
    
    # Allowed English terms that are commonly used in Korean tech contexts
    ALLOWED_ENGLISH = {
        # Commonly accepted tech abbreviations
        'api', 'ui', 'ux', 'db', 'sql', 'html', 'css', 'js', 'json',
        'xml', 'http', 'https', 'url', 'uri', 'rest', 'soap', 'tcp',
        'ip', 'dns', 'ssl', 'tls', 'oauth', 'jwt', 'crud', 'mvp',
        'poc', 'qa', 'ci', 'cd', 'devops', 'aws', 'gcp', 'azure',
        
        # Brand names and proper nouns (when used appropriately)
        'github', 'gitlab', 'docker', 'kubernetes', 'jenkins',
        'slack', 'teams', 'zoom', 'jira', 'confluence',
        
        # Time formats
        'am', 'pm'
    }
    
    # Patterns for detecting English text
    ENGLISH_PATTERNS = [
        # English sentences (words connected by spaces with English grammar)
        r'\b[a-zA-Z]+\s+[a-zA-Z]+\s+[a-zA-Z]+\b',
        
        # English phrases with common prepositions
        r'\b(in|on|at|by|for|with|from|to)\s+[a-zA-Z]+\b',
        
        # English verb patterns
        r'\b[a-zA-Z]+ing\b',  # -ing endings
        r'\b[a-zA-Z]+ed\b',   # -ed endings
        r'\b[a-zA-Z]+ly\b',   # -ly adverbs
        
        # English articles and determiners
        r'\b(the|a|an|this|that|these|those)\s+[a-zA-Z]+\b',
        
        # English question patterns
        r'\b(what|when|where|why|how|who)\s+[a-zA-Z]+\b',
        
        # English modal verbs
        r'\b(will|would|should|could|can|may|might|must)\s+[a-zA-Z]+\b'
    ]
    
    def __init__(self, strict_mode: bool = True):
        """
        Initialize Korean content validator.
        
        Args:
            strict_mode: If True, applies stricter validation rules
        """
        self.strict_mode = strict_mode
    
    def detect_english_text(self, content: str) -> List[Tuple[str, str]]:
        """
        Detect English text in Korean content.
        
        Args:
            content: Content to validate
            
        Returns:
            List of tuples (detected_text, reason) for each English text found
        """
        issues = []
        
        # Normalize content for analysis
        normalized_content = content.lower().strip()
        
        # Check for English word patterns
        words = re.findall(r'\b[a-zA-Z]+\b', normalized_content)
        for word in words:
            if word in self.ENGLISH_WORDS and word not in self.ALLOWED_ENGLISH:
                issues.append((word, f"English word '{word}' should be translated to Korean"))
        
        # Check for English sentence patterns
        for pattern in self.ENGLISH_PATTERNS:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                matched_text = match.group()
                # Skip if it's just allowed abbreviations
                if not any(allowed in matched_text.lower() for allowed in self.ALLOWED_ENGLISH):
                    issues.append((matched_text, f"English phrase pattern detected: '{matched_text}'"))
        
        # Check for mixed language in the same sentence
        sentences = re.split(r'[.!?。！？]', content)
        for sentence in sentences:
            if self._has_mixed_language(sentence.strip()):
                issues.append((sentence.strip(), "Mixed Korean-English in same sentence"))
        
        return issues
    
    def _has_mixed_language(self, sentence: str) -> bool:
        """
        Check if a sentence has mixed Korean and English text.
        
        Args:
            sentence: Sentence to check
            
        Returns:
            True if mixed language detected
        """
        if not sentence:
            return False
        
        # Check for Korean characters
        has_korean = bool(re.search(r'[가-힣]', sentence))
        
        # Check for English words (excluding allowed terms)
        english_words = re.findall(r'\b[a-zA-Z]+\b', sentence.lower())
        has_english = any(word not in self.ALLOWED_ENGLISH for word in english_words)
        
        return has_korean and has_english
    
    def validate_korean_content(self, content: str) -> Tuple[bool, List[str]]:
        """
        Validate Korean content and return validation results.
        
        Args:
            content: Content to validate
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        if not content or not content.strip():
            return False, ["Content is empty"]
        
        issues = []
        detected_english = self.detect_english_text(content)
        
        if detected_english:
            for text, reason in detected_english:
                issues.append(f"English text detected: {reason}")
        
        # Check for minimum Korean content
        korean_chars = len(re.findall(r'[가-힣]', content))
        total_chars = len(re.sub(r'\s', '', content))
        
        if total_chars > 0:
            korean_ratio = korean_chars / total_chars
            if korean_ratio < 0.3:  # Less than 30% Korean characters
                issues.append(f"Insufficient Korean content (only {korean_ratio:.1%} Korean characters)")
        
        # Check for proper Korean sentence structure
        if not self._has_proper_korean_structure(content):
            issues.append("Content lacks proper Korean sentence structure")
        
        is_valid = len(issues) == 0
        return is_valid, issues
    
    def _has_proper_korean_structure(self, content: str) -> bool:
        """
        Check if content has proper Korean sentence structure.
        
        Args:
            content: Content to check
            
        Returns:
            True if proper Korean structure detected
        """
        # Look for Korean sentence endings
        korean_endings = r'[다요니까요세요습니다]'
        has_korean_endings = bool(re.search(korean_endings, content))
        
        # Look for Korean particles
        korean_particles = r'[은는이가을를에서로와과의도만]'
        has_korean_particles = bool(re.search(korean_particles, content))
        
        # Look for Korean characters
        has_korean_chars = bool(re.search(r'[가-힣]', content))
        
        return has_korean_chars and (has_korean_endings or has_korean_particles)
    
    def suggest_korean_alternatives(self, english_text: str) -> List[str]:
        """
        Suggest Korean alternatives for English text.
        
        Args:
            english_text: English text to translate
            
        Returns:
            List of suggested Korean alternatives
        """
        # Common translations
        translations = {
            'api': 'API',
            'database': '데이터베이스',
            'server': '서버',
            'client': '클라이언트',
            'frontend': '프론트엔드',
            'backend': '백엔드',
            'framework': '프레임워크',
            'library': '라이브러리',
            'repository': '저장소',
            'deployment': '배포',
            'testing': '테스트',
            'debugging': '디버깅',
            'development': '개발',
            'production': '운영',
            'staging': '스테이징',
            'environment': '환경',
            'configuration': '설정',
            'integration': '통합',
            'authentication': '인증',
            'authorization': '권한',
            'validation': '검증',
            'optimization': '최적화',
            'performance': '성능',
            'monitoring': '모니터링',
            'analytics': '분석',
            'dashboard': '대시보드',
            'interface': '인터페이스',
            'component': '컴포넌트',
            'module': '모듈',
            'service': '서비스',
            'endpoint': '엔드포인트',
            'request': '요청',
            'response': '응답',
            'session': '세션',
            'cache': '캐시',
            'storage': '저장소',
            'backup': '백업',
            'security': '보안',
            'encryption': '암호화',
            'project': '프로젝트',
            'management': '관리',
            'planning': '계획',
            'schedule': '일정',
            'deadline': '마감일',
            'milestone': '마일스톤',
            'task': '작업',
            'priority': '우선순위',
            'blocker': '차단 요소',
            'dependency': '의존성',
            'requirement': '요구사항',
            'specification': '명세서',
            'documentation': '문서',
            'review': '리뷰',
            'approval': '승인',
            'feedback': '피드백',
            'meeting': '회의',
            'presentation': '발표',
            'report': '보고서',
            'update': '업데이트',
            'status': '상태',
            'progress': '진행상황',
            'completion': '완료',
            'delivery': '전달',
            'email': '이메일',
            'chat': '채팅',
            'message': '메시지',
            'notification': '알림',
            'alert': '경고',
            'communication': '커뮤니케이션',
            'collaboration': '협업',
            'coordination': '조정',
            'sync': '동기화',
            'discussion': '논의',
            'decision': '결정',
            'agreement': '합의',
            'confirmation': '확인'
        }
        
        suggestions = []
        english_lower = english_text.lower()
        
        if english_lower in translations:
            suggestions.append(translations[english_lower])
        
        # Add generic suggestions if no specific translation found
        if not suggestions:
            suggestions.extend([
                f"'{english_text}'를 한국어로 번역",
                f"'{english_text}' 대신 한국어 표현 사용",
                "적절한 한국어 용어로 대체"
            ])
        
        return suggestions


# Global validator instance
_default_validator = KoreanContentValidator()


def validate_korean_content(content: str, strict_mode: bool = True) -> Tuple[bool, List[str]]:
    """
    Convenience function to validate Korean content.
    
    Args:
        content: Content to validate
        strict_mode: Whether to use strict validation
        
    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    validator = KoreanContentValidator(strict_mode)
    return validator.validate_korean_content(content)


def detect_english_in_korean(content: str) -> List[Tuple[str, str]]:
    """
    Convenience function to detect English text in Korean content.
    
    Args:
        content: Content to check
        
    Returns:
        List of tuples (detected_text, reason)
    """
    return _default_validator.detect_english_text(content)


def suggest_korean_translation(english_text: str) -> List[str]:
    """
    Convenience function to get Korean translation suggestions.
    
    Args:
        english_text: English text to translate
        
    Returns:
        List of Korean translation suggestions
    """
    return _default_validator.suggest_korean_alternatives(english_text)