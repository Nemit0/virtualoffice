"""
Tests for PromptManager class.

Tests template loading, caching, validation, and prompt construction.
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from virtualoffice.sim_manager.prompts import (
    PromptManager,
    PromptTemplate,
    PromptTemplateError,
)


@pytest.fixture
def temp_template_dir():
    """Create a temporary directory for test templates."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_template_yaml():
    """Sample template YAML content."""
    return """
name: "test_template_en"
version: "1.0"
locale: "en"
category: "planning"
description: "Test template for unit tests"

system_prompt: |
  You are a test assistant.
  Follow the instructions carefully.

user_prompt_template: |
  Worker: {worker_name} ({worker_role})
  Tick: {tick}
  
  {persona_section}
  {team_roster_section}
  
  Generate a test plan.

sections:
  persona_section:
    template: |
      === PERSONA ===
      {persona_markdown}
    required_variables: ["persona_markdown"]
  
  team_roster_section:
    template: |
      === TEAM ===
      {team_roster}
    required_variables: ["team_roster"]

validation_rules:
  - "Must include worker name"
  - "Must include tick number"

variants:
  - name: "verbose"
    system_prompt: "You are a very detailed test assistant."
  - name: "concise"
    user_prompt_template: "Worker: {worker_name}. Quick plan for tick {tick}."

metadata:
  author: "test"
  created: "2025-01-01"
"""


@pytest.fixture
def prompt_manager_with_template(temp_template_dir, sample_template_yaml):
    """Create a PromptManager with a sample template."""
    # Create planning subdirectory
    planning_dir = temp_template_dir / "planning"
    planning_dir.mkdir()
    
    # Write sample template
    template_file = planning_dir / "test_template_en.yaml"
    template_file.write_text(sample_template_yaml, encoding='utf-8')
    
    # Create manager
    manager = PromptManager(str(temp_template_dir), locale="en")
    return manager


class TestPromptManagerInitialization:
    """Test PromptManager initialization."""
    
    def test_init_with_valid_directory(self, temp_template_dir):
        """Test initialization with valid directory."""
        manager = PromptManager(str(temp_template_dir), locale="en")
        assert manager.template_dir == temp_template_dir
        assert manager.locale == "en"
        assert manager._cache == {}
    
    def test_init_with_invalid_directory(self):
        """Test initialization with non-existent directory."""
        with pytest.raises(PromptTemplateError, match="does not exist"):
            PromptManager("/nonexistent/path", locale="en")
    
    def test_init_with_korean_locale(self, temp_template_dir):
        """Test initialization with Korean locale."""
        manager = PromptManager(str(temp_template_dir), locale="ko")
        assert manager.locale == "ko"
    
    def test_init_normalizes_locale(self, temp_template_dir):
        """Test that locale is normalized to lowercase."""
        manager = PromptManager(str(temp_template_dir), locale="EN")
        assert manager.locale == "en"


class TestTemplateLoading:
    """Test template loading functionality."""
    
    def test_load_template_success(self, prompt_manager_with_template):
        """Test successful template loading."""
        template = prompt_manager_with_template.load_template("test_template")
        
        assert isinstance(template, PromptTemplate)
        assert template.name == "test_template_en"
        assert template.version == "1.0"
        assert template.locale == "en"
        assert template.category == "planning"
        assert "test assistant" in template.system_prompt.lower()
        assert "{worker_name}" in template.user_prompt_template
    
    def test_load_template_caching(self, prompt_manager_with_template):
        """Test that templates are cached after first load."""
        # Load template twice
        template1 = prompt_manager_with_template.load_template("test_template")
        template2 = prompt_manager_with_template.load_template("test_template")
        
        # Should be the same object (cached)
        assert template1 is template2
    
    def test_load_template_not_found(self, prompt_manager_with_template):
        """Test loading non-existent template."""
        with pytest.raises(PromptTemplateError, match="not found"):
            prompt_manager_with_template.load_template("nonexistent")
    
    def test_load_template_with_sections(self, prompt_manager_with_template):
        """Test that sections are loaded correctly."""
        template = prompt_manager_with_template.load_template("test_template")
        
        assert "persona_section" in template.sections
        assert "team_roster_section" in template.sections
        assert "persona_markdown" in template.sections["persona_section"]["required_variables"]
    
    def test_load_template_with_variants(self, prompt_manager_with_template):
        """Test that variants are loaded correctly."""
        template = prompt_manager_with_template.load_template("test_template")
        
        assert len(template.variants) == 2
        variant_names = [v["name"] for v in template.variants]
        assert "verbose" in variant_names
        assert "concise" in variant_names
    
    def test_load_template_missing_required_fields(self, temp_template_dir):
        """Test loading template with missing required fields."""
        # Create invalid template
        planning_dir = temp_template_dir / "planning"
        planning_dir.mkdir()
        
        invalid_yaml = """
name: "invalid_en"
version: "1.0"
# Missing locale, category, system_prompt, user_prompt_template
"""
        template_file = planning_dir / "invalid_en.yaml"
        template_file.write_text(invalid_yaml, encoding='utf-8')
        
        manager = PromptManager(str(temp_template_dir), locale="en")
        
        with pytest.raises(PromptTemplateError, match="missing required fields"):
            manager.load_template("invalid")


class TestPromptConstruction:
    """Test prompt construction with context."""
    
    def test_build_prompt_basic(self, prompt_manager_with_template):
        """Test basic prompt construction."""
        context = {
            "worker_name": "Alice",
            "worker_role": "Developer",
            "tick": 100,
            "persona_markdown": "Experienced developer",
            "team_roster": "Bob (Designer)\nCharlie (Manager)",
        }
        
        messages = prompt_manager_with_template.build_prompt("test_template", context)
        
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "Alice" in messages[1]["content"]
        assert "Developer" in messages[1]["content"]
        assert "100" in messages[1]["content"]
    
    def test_build_prompt_with_sections(self, prompt_manager_with_template):
        """Test that sections are rendered correctly."""
        context = {
            "worker_name": "Alice",
            "worker_role": "Developer",
            "tick": 100,
            "persona_markdown": "Experienced developer",
            "team_roster": "Bob (Designer)",
        }
        
        messages = prompt_manager_with_template.build_prompt("test_template", context)
        user_content = messages[1]["content"]
        
        assert "=== PERSONA ===" in user_content
        assert "Experienced developer" in user_content
        assert "=== TEAM ===" in user_content
        assert "Bob (Designer)" in user_content
    
    def test_build_prompt_with_variant(self, prompt_manager_with_template):
        """Test building prompt with a specific variant."""
        context = {
            "worker_name": "Alice",
            "worker_role": "Developer",
            "tick": 100,
            "persona_markdown": "Experienced developer",
            "team_roster": "Bob (Designer)",
        }
        
        messages = prompt_manager_with_template.build_prompt(
            "test_template", context, variant="verbose"
        )
        
        assert "very detailed" in messages[0]["content"].lower()
    
    def test_build_prompt_missing_variable(self, prompt_manager_with_template):
        """Test building prompt with missing required variable."""
        context = {
            "worker_name": "Alice",
            # Missing worker_role, tick, persona_markdown, team_roster
        }
        
        with pytest.raises(PromptTemplateError, match="missing required context variables"):
            prompt_manager_with_template.build_prompt("test_template", context)
    
    def test_build_prompt_missing_section_variable(self, prompt_manager_with_template):
        """Test building prompt with missing section variable."""
        context = {
            "worker_name": "Alice",
            "worker_role": "Developer",
            "tick": 100,
            # Missing persona_markdown (required by persona_section)
            "team_roster": "Bob (Designer)",
        }
        
        with pytest.raises(PromptTemplateError, match="missing required context variables"):
            prompt_manager_with_template.build_prompt("test_template", context)


class TestContextValidation:
    """Test context validation."""
    
    def test_validate_context_success(self, prompt_manager_with_template):
        """Test successful context validation."""
        template = prompt_manager_with_template.load_template("test_template")
        context = {
            "worker_name": "Alice",
            "worker_role": "Developer",
            "tick": 100,
            "persona_markdown": "Experienced developer",
            "team_roster": "Bob (Designer)",
        }
        
        result = prompt_manager_with_template.validate_context(template, context)
        assert result is True
    
    def test_validate_context_missing_variables(self, prompt_manager_with_template):
        """Test validation with missing variables."""
        template = prompt_manager_with_template.load_template("test_template")
        context = {
            "worker_name": "Alice",
            # Missing other required variables
        }
        
        with pytest.raises(PromptTemplateError, match="missing required context variables"):
            prompt_manager_with_template.validate_context(template, context)


class TestVariantSelection:
    """Test variant selection functionality."""
    
    def test_get_best_variant_with_variants(self, prompt_manager_with_template):
        """Test getting best variant when variants exist."""
        variant = prompt_manager_with_template.get_best_variant("test_template")
        
        # Should return first variant name as placeholder
        assert variant in ["verbose", "concise", "default"]
    
    def test_get_best_variant_no_template(self, prompt_manager_with_template):
        """Test getting best variant for non-existent template."""
        variant = prompt_manager_with_template.get_best_variant("nonexistent")
        assert variant == "default"


class TestTemplateListingAndManagement:
    """Test template listing and management."""
    
    def test_list_templates(self, prompt_manager_with_template):
        """Test listing available templates."""
        templates = prompt_manager_with_template.list_templates()
        
        assert "test_template" in templates
    
    def test_list_templates_by_category(self, temp_template_dir, sample_template_yaml):
        """Test listing templates filtered by category."""
        # Create templates in different categories
        planning_dir = temp_template_dir / "planning"
        planning_dir.mkdir()
        (planning_dir / "plan_en.yaml").write_text(sample_template_yaml, encoding='utf-8')
        
        reporting_dir = temp_template_dir / "reporting"
        reporting_dir.mkdir()
        (reporting_dir / "report_en.yaml").write_text(
            sample_template_yaml.replace('category: "planning"', 'category: "reporting"'),
            encoding='utf-8'
        )
        
        manager = PromptManager(str(temp_template_dir), locale="en")
        
        planning_templates = manager.list_templates(category="planning")
        assert "plan" in planning_templates
        
        reporting_templates = manager.list_templates(category="reporting")
        assert "report" in reporting_templates
    
    def test_reload_templates(self, prompt_manager_with_template):
        """Test reloading templates clears cache."""
        # Load template to populate cache
        prompt_manager_with_template.load_template("test_template")
        assert len(prompt_manager_with_template._cache) > 0
        
        # Reload templates
        prompt_manager_with_template.reload_templates()
        assert len(prompt_manager_with_template._cache) == 0


class TestKoreanLocale:
    """Test Korean locale support."""
    
    def test_load_korean_template(self, temp_template_dir):
        """Test loading Korean template."""
        # Create Korean template
        planning_dir = temp_template_dir / "planning"
        planning_dir.mkdir()
        
        korean_yaml = """
name: "test_template_ko"
version: "1.0"
locale: "ko"
category: "planning"

system_prompt: |
  당신은 테스트 어시스턴트입니다.

user_prompt_template: |
  작업자: {worker_name} ({worker_role})
  틱: {tick}

sections: {}
validation_rules: []
variants: []
metadata: {}
"""
        (planning_dir / "test_template_ko.yaml").write_text(korean_yaml, encoding='utf-8')
        
        manager = PromptManager(str(temp_template_dir), locale="ko")
        template = manager.load_template("test_template")
        
        assert template.locale == "ko"
        assert "테스트 어시스턴트" in template.system_prompt
        assert "작업자" in template.user_prompt_template
    
    def test_korean_context_building(self, temp_template_dir):
        """Test building prompts with Korean context."""
        # Create Korean template
        planning_dir = temp_template_dir / "planning"
        planning_dir.mkdir()
        
        korean_yaml = """
name: "test_ko"
version: "1.0"
locale: "ko"
category: "planning"

system_prompt: "한국어 어시스턴트"

user_prompt_template: |
  이름: {name}
  역할: {role}

sections: {}
validation_rules: []
variants: []
metadata: {}
"""
        (planning_dir / "test_ko.yaml").write_text(korean_yaml, encoding='utf-8')
        
        manager = PromptManager(str(temp_template_dir), locale="ko")
        context = {
            "name": "김철수",
            "role": "개발자",
        }
        
        messages = manager.build_prompt("test", context)
        assert "김철수" in messages[1]["content"]
        assert "개발자" in messages[1]["content"]
