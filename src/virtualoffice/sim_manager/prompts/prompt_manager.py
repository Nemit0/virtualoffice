"""
Prompt template management system.

Provides loading, caching, validation, and construction of LLM prompts
from YAML template files with support for versioning and A/B testing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml


class PromptTemplateError(Exception):
    """Base exception for prompt template errors."""

    pass


@dataclass
class PromptTemplate:
    """
    Represents a prompt template loaded from YAML.

    Attributes:
        name: Template identifier (e.g., "hourly_planning_en")
        version: Template version (e.g., "1.0", "latest")
        locale: Language/locale code (e.g., "en", "ko")
        category: Template category (e.g., "planning", "reporting")
        system_prompt: LLM system message content
        user_prompt_template: User message template with variable placeholders
        sections: Reusable template sections with their own templates
        validation_rules: List of validation requirements
        variants: Alternative template versions for A/B testing
        metadata: Additional template metadata
    """

    name: str
    version: str
    locale: str
    category: str
    system_prompt: str
    user_prompt_template: str
    sections: dict[str, dict[str, Any]] = field(default_factory=dict)
    validation_rules: list[str] = field(default_factory=list)
    variants: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class PromptManager:
    """
    Manages prompt templates with caching and validation.

    Loads YAML templates from a directory structure, caches them for performance,
    and provides methods to build prompts with context substitution.
    """

    def __init__(self, template_dir: str, locale: str = "en"):
        """
        Initialize the prompt manager.

        Args:
            template_dir: Path to directory containing template files
            locale: Default locale for template loading (e.g., "en", "ko")
        """
        self.template_dir = Path(template_dir)
        self.locale = locale.strip().lower() or "en"
        self._cache: dict[str, PromptTemplate] = {}

        if not self.template_dir.exists():
            raise PromptTemplateError(f"Template directory does not exist: {self.template_dir}")

    def load_template(self, name: str, version: str = "latest") -> PromptTemplate:
        """
        Load a template from disk or cache.

        Args:
            name: Template name (without locale suffix or extension)
            version: Template version (currently only "latest" supported)

        Returns:
            Loaded and validated PromptTemplate

        Raises:
            PromptTemplateError: If template not found or invalid
        """
        # Build cache key
        cache_key = f"{name}_{self.locale}_{version}"

        # Return cached template if available
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Build template filename with locale
        template_filename = f"{name}_{self.locale}.yaml"

        # Search for template in category subdirectories
        template_path = None
        for category_dir in ["planning", "reporting", "communication"]:
            candidate = self.template_dir / category_dir / template_filename
            if candidate.exists():
                template_path = candidate
                break

        # Also check root template directory
        if template_path is None:
            candidate = self.template_dir / template_filename
            if candidate.exists():
                template_path = candidate

        if template_path is None:
            # List available templates for helpful error message
            available = self.list_templates()
            raise PromptTemplateError(
                f"Template '{name}' not found for locale '{self.locale}'. "
                f"Available templates: {', '.join(available)}"
            )

        # Load and parse YAML
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            raise PromptTemplateError(f"Failed to load template from {template_path}: {e}") from e

        # Validate required fields
        required_fields = ["name", "version", "locale", "category", "system_prompt", "user_prompt_template"]
        missing = [field for field in required_fields if field not in data]
        if missing:
            raise PromptTemplateError(f"Template {template_path} missing required fields: {', '.join(missing)}")

        # Create template object
        template = PromptTemplate(
            name=data["name"],
            version=data["version"],
            locale=data["locale"],
            category=data["category"],
            system_prompt=data["system_prompt"],
            user_prompt_template=data["user_prompt_template"],
            sections=data.get("sections", {}),
            validation_rules=data.get("validation_rules", []),
            variants=data.get("variants", []),
            metadata=data.get("metadata", {}),
        )

        # Cache and return
        self._cache[cache_key] = template
        return template

    def build_prompt(
        self, template_name: str, context: dict[str, Any], variant: str | None = None
    ) -> list[dict[str, str]]:
        """
        Build a prompt from a template with context substitution.

        Args:
            template_name: Name of template to use
            context: Dictionary of variables for substitution
            variant: Optional variant name for A/B testing

        Returns:
            List of message dicts with 'role' and 'content' keys

        Raises:
            PromptTemplateError: If template not found or context invalid
        """
        # Load template
        template = self.load_template(template_name)

        # Validate context has required variables
        self.validate_context(template, context)

        # Use variant if specified
        system_prompt = template.system_prompt
        user_template = template.user_prompt_template

        if variant:
            variant_data = next((v for v in template.variants if v.get("name") == variant), None)
            if variant_data:
                system_prompt = variant_data.get("system_prompt", system_prompt)
                user_template = variant_data.get("user_prompt_template", user_template)

        # Build sections first
        rendered_sections = {}
        for section_name, section_data in template.sections.items():
            section_template = section_data.get("template", "")
            required_vars = section_data.get("required_variables", [])

            # Check section has required variables
            missing = [var for var in required_vars if var not in context]
            if missing:
                raise PromptTemplateError(f"Section '{section_name}' missing required variables: {', '.join(missing)}")

            # Render section
            try:
                rendered_sections[section_name] = section_template.format(**context)
            except KeyError as e:
                raise PromptTemplateError(f"Section '{section_name}' references undefined variable: {e}") from e

        # Add rendered sections to context
        full_context = {**context, **rendered_sections}

        # Render user prompt
        try:
            user_content = user_template.format(**full_context)
        except KeyError as e:
            raise PromptTemplateError(
                f"Template '{template_name}' references undefined variable: {e}. "
                f"Provided context keys: {', '.join(context.keys())}"
            ) from e

        # Build messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        return messages

    def validate_context(self, template: PromptTemplate, context: dict[str, Any]) -> bool:
        """
        Validate that context contains all required variables.

        Args:
            template: Template to validate against
            context: Context dictionary to validate

        Returns:
            True if valid

        Raises:
            PromptTemplateError: If validation fails
        """
        # Extract variables from user_prompt_template
        import re

        pattern = r"\{(\w+)\}"
        template_vars = set(re.findall(pattern, template.user_prompt_template))

        # Remove section names from required vars (they'll be rendered separately)
        section_names = set(template.sections.keys())
        template_vars = template_vars - section_names

        # Check section templates for their required variables
        for section_data in template.sections.values():
            section_template = section_data.get("template", "")
            section_vars = set(re.findall(pattern, section_template))
            template_vars.update(section_vars)

        # Check for missing variables
        missing = template_vars - set(context.keys())
        if missing:
            raise PromptTemplateError(
                f"Template '{template.name}' missing required context variables: "
                f"{', '.join(sorted(missing))}. "
                f"Provided: {', '.join(sorted(context.keys()))}"
            )

        return True

    def get_best_variant(self, template_name: str) -> str:
        """
        Get the best performing variant for a template.

        This is a placeholder for future A/B testing integration.
        Currently returns "default" or the first variant name.

        Args:
            template_name: Name of template

        Returns:
            Variant name to use
        """
        try:
            template = self.load_template(template_name)
            if template.variants:
                return template.variants[0].get("name", "default")
        except PromptTemplateError:
            pass

        return "default"

    def list_templates(self, category: str | None = None) -> list[str]:
        """
        List available templates.

        Args:
            category: Optional category filter (e.g., "planning", "reporting")

        Returns:
            List of template names (without locale suffix or extension)
        """
        templates = set()

        # Search directories
        search_dirs = []
        if category:
            search_dirs.append(self.template_dir / category)
        else:
            search_dirs.append(self.template_dir)
            for subdir in ["planning", "reporting", "communication"]:
                search_dirs.append(self.template_dir / subdir)

        # Find YAML files
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            for yaml_file in search_dir.glob("*.yaml"):
                # Extract template name (remove locale suffix and extension)
                name = yaml_file.stem
                if name.endswith(f"_{self.locale}"):
                    name = name[: -len(f"_{self.locale}")]
                templates.add(name)

        return sorted(templates)

    def reload_templates(self) -> None:
        """
        Clear the template cache, forcing reload on next access.

        Useful for development or when templates are updated at runtime.
        """
        self._cache.clear()
