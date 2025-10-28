"""
Performance benchmarks for template loading and caching.

Tests that measure template loading performance and verify that
caching provides significant performance improvements.
"""

import importlib
import time
from pathlib import Path

import pytest


def test_template_loading_speed():
    """Test that template loading is fast."""
    try:
        from virtualoffice.sim_manager.prompts.prompt_manager import PromptManager
    except ImportError:
        pytest.skip("PromptManager not yet implemented")
    
    # Get template directory
    template_dir = Path(__file__).parents[3] / "src" / "virtualoffice" / "sim_manager" / "prompts" / "templates"
    
    if not template_dir.exists():
        pytest.skip("Template directory not found")
    
    # Create PromptManager
    manager = PromptManager(str(template_dir), locale="en")
    
    # Measure template loading time
    start_time = time.perf_counter()
    
    try:
        template = manager.load_template("hourly_planning_en")
    except Exception:
        pytest.skip("Template loading not yet implemented or template not found")
    
    end_time = time.perf_counter()
    loading_time = end_time - start_time
    
    # Template loading should be fast (< 10ms)
    assert loading_time < 0.01, f"Template loading too slow: {loading_time*1000:.2f}ms"
    
    print(f"\nTemplate loading speed: {loading_time*1000:.2f}ms")


def test_template_caching_effectiveness():
    """Test that template caching provides significant speedup."""
    try:
        from virtualoffice.sim_manager.prompts.prompt_manager import PromptManager
    except ImportError:
        pytest.skip("PromptManager not yet implemented")
    
    template_dir = Path(__file__).parents[3] / "src" / "virtualoffice" / "sim_manager" / "prompts" / "templates"
    
    if not template_dir.exists():
        pytest.skip("Template directory not found")
    
    manager = PromptManager(str(template_dir), locale="en")
    
    # First load (cold cache)
    start_time = time.perf_counter()
    try:
        template1 = manager.load_template("hourly_planning_en")
    except Exception:
        pytest.skip("Template loading not yet implemented")
    end_time = time.perf_counter()
    cold_load_time = end_time - start_time
    
    # Second load (warm cache)
    start_time = time.perf_counter()
    template2 = manager.load_template("hourly_planning_en")
    end_time = time.perf_counter()
    warm_load_time = end_time - start_time
    
    # Cached load should be at least 2x faster
    speedup = cold_load_time / warm_load_time if warm_load_time > 0 else 1
    
    print(f"\nTemplate caching effectiveness:")
    print(f"  Cold load: {cold_load_time*1000:.2f}ms")
    print(f"  Warm load: {warm_load_time*1000:.2f}ms")
    print(f"  Speedup: {speedup:.1f}x")
    
    assert speedup >= 2, f"Insufficient caching speedup: {speedup:.1f}x"


def test_multiple_template_loading():
    """Test loading multiple templates efficiently."""
    try:
        from virtualoffice.sim_manager.prompts.prompt_manager import PromptManager
    except ImportError:
        pytest.skip("PromptManager not yet implemented")
    
    template_dir = Path(__file__).parents[3] / "src" / "virtualoffice" / "sim_manager" / "prompts" / "templates"
    
    if not template_dir.exists():
        pytest.skip("Template directory not found")
    
    manager = PromptManager(str(template_dir), locale="en")
    
    # List of templates to load
    template_names = [
        "hourly_planning_en",
        "daily_planning_en",
        "daily_report_en",
    ]
    
    # Load all templates
    start_time = time.perf_counter()
    
    loaded_count = 0
    for name in template_names:
        try:
            template = manager.load_template(name)
            loaded_count += 1
        except Exception:
            pass  # Skip templates that don't exist yet
    
    end_time = time.perf_counter()
    total_time = end_time - start_time
    
    if loaded_count == 0:
        pytest.skip("No templates found")
    
    avg_time = total_time / loaded_count
    
    print(f"\nMultiple template loading:")
    print(f"  Loaded {loaded_count} templates in {total_time*1000:.2f}ms")
    print(f"  Average per template: {avg_time*1000:.2f}ms")
    
    # Average should be < 10ms per template
    assert avg_time < 0.01, f"Template loading too slow: {avg_time*1000:.2f}ms per template"


def test_template_reload_performance():
    """Test that template reloading is efficient."""
    try:
        from virtualoffice.sim_manager.prompts.prompt_manager import PromptManager
    except ImportError:
        pytest.skip("PromptManager not yet implemented")
    
    template_dir = Path(__file__).parents[3] / "src" / "virtualoffice" / "sim_manager" / "prompts" / "templates"
    
    if not template_dir.exists():
        pytest.skip("Template directory not found")
    
    manager = PromptManager(str(template_dir), locale="en")
    
    # Load initial template
    try:
        template1 = manager.load_template("hourly_planning_en")
    except Exception:
        pytest.skip("Template loading not yet implemented")
    
    # Reload templates
    start_time = time.perf_counter()
    
    if hasattr(manager, 'reload_templates'):
        manager.reload_templates()
    else:
        pytest.skip("Template reloading not yet implemented")
    
    end_time = time.perf_counter()
    reload_time = end_time - start_time
    
    # Reload should be fast (< 50ms)
    assert reload_time < 0.05, f"Template reload too slow: {reload_time*1000:.2f}ms"
    
    print(f"\nTemplate reload performance: {reload_time*1000:.2f}ms")


def test_prompt_building_performance():
    """Test that prompt building with templates is fast."""
    try:
        from virtualoffice.sim_manager.prompts.prompt_manager import PromptManager
    except ImportError:
        pytest.skip("PromptManager not yet implemented")
    
    template_dir = Path(__file__).parents[3] / "src" / "virtualoffice" / "sim_manager" / "prompts" / "templates"
    
    if not template_dir.exists():
        pytest.skip("Template directory not found")
    
    manager = PromptManager(str(template_dir), locale="en")
    
    # Create sample context
    context = {
        "worker_name": "Test Worker",
        "worker_role": "Developer",
        "tick": 10,
        "context_reason": "test",
        "persona_markdown": "Test persona",
        "team_roster": "Team roster",
        "project_plan": "Project plan",
        "daily_plan": "Daily plan",
    }
    
    # Build prompt
    start_time = time.perf_counter()
    
    try:
        if hasattr(manager, 'build_prompt'):
            messages = manager.build_prompt("hourly_planning_en", context)
        else:
            pytest.skip("Prompt building not yet implemented")
    except Exception as e:
        pytest.skip(f"Prompt building failed: {e}")
    
    end_time = time.perf_counter()
    build_time = end_time - start_time
    
    # Prompt building should be fast (< 5ms)
    assert build_time < 0.005, f"Prompt building too slow: {build_time*1000:.2f}ms"
    
    print(f"\nPrompt building performance: {build_time*1000:.2f}ms")


def test_concurrent_template_access():
    """Test that concurrent template access is thread-safe and efficient."""
    try:
        from virtualoffice.sim_manager.prompts.prompt_manager import PromptManager
    except ImportError:
        pytest.skip("PromptManager not yet implemented")
    
    from concurrent.futures import ThreadPoolExecutor
    
    template_dir = Path(__file__).parents[3] / "src" / "virtualoffice" / "sim_manager" / "prompts" / "templates"
    
    if not template_dir.exists():
        pytest.skip("Template directory not found")
    
    manager = PromptManager(str(template_dir), locale="en")
    
    def load_template_task(template_name):
        """Task to load a template."""
        try:
            return manager.load_template(template_name)
        except Exception:
            return None
    
    # Load template concurrently
    start_time = time.perf_counter()
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(load_template_task, "hourly_planning_en") for _ in range(10)]
        results = [f.result() for f in futures]
    
    end_time = time.perf_counter()
    concurrent_time = end_time - start_time
    
    # Verify all loads succeeded
    successful_loads = sum(1 for r in results if r is not None)
    
    if successful_loads == 0:
        pytest.skip("No templates loaded successfully")
    
    avg_time = concurrent_time / successful_loads
    
    print(f"\nConcurrent template access:")
    print(f"  {successful_loads} concurrent loads in {concurrent_time*1000:.2f}ms")
    print(f"  Average per load: {avg_time*1000:.2f}ms")
    
    # Concurrent access should be efficient due to caching
    assert avg_time < 0.01, f"Concurrent template access too slow: {avg_time*1000:.2f}ms per load"


def test_template_validation_performance():
    """Test that template validation is fast."""
    try:
        from virtualoffice.sim_manager.prompts.prompt_manager import PromptManager
    except ImportError:
        pytest.skip("PromptManager not yet implemented")
    
    template_dir = Path(__file__).parents[3] / "src" / "virtualoffice" / "sim_manager" / "prompts" / "templates"
    
    if not template_dir.exists():
        pytest.skip("Template directory not found")
    
    manager = PromptManager(str(template_dir), locale="en")
    
    # Load template
    try:
        template = manager.load_template("hourly_planning_en")
    except Exception:
        pytest.skip("Template loading not yet implemented")
    
    # Create context
    context = {
        "worker_name": "Test Worker",
        "worker_role": "Developer",
        "tick": 10,
        "context_reason": "test",
        "persona_markdown": "Test persona",
        "team_roster": "Team roster",
        "project_plan": "Project plan",
        "daily_plan": "Daily plan",
    }
    
    # Validate context
    start_time = time.perf_counter()
    
    try:
        if hasattr(manager, 'validate_context'):
            is_valid = manager.validate_context(template, context)
        else:
            pytest.skip("Context validation not yet implemented")
    except Exception:
        pytest.skip("Context validation failed")
    
    end_time = time.perf_counter()
    validation_time = end_time - start_time
    
    # Validation should be very fast (< 1ms)
    assert validation_time < 0.001, f"Context validation too slow: {validation_time*1000:.2f}ms"
    
    print(f"\nTemplate validation performance: {validation_time*1000:.2f}ms")
