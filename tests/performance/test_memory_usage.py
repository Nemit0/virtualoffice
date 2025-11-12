"""
Performance benchmarks for memory usage.

Tests that profile memory usage during long simulations to ensure
the refactored engine doesn't have memory leaks or excessive memory consumption.
"""

import importlib
import sys
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from virtualoffice.sim_manager.planner import PlanResult


@contextmanager
def _reload_db(tmp_path, monkeypatch):
    """Context manager to reload database with temporary path."""
    db_path = tmp_path / "vdos.db"
    monkeypatch.setenv("VDOS_DB_PATH", str(db_path))
    import virtualoffice.common.db as db_module
    importlib.reload(db_module)
    yield


def get_memory_usage_mb():
    """Get current memory usage in MB."""
    try:
        import psutil
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024
    except ImportError:
        # If psutil not available, use sys.getsizeof as rough estimate
        return sys.getsizeof({}) / 1024 / 1024


@pytest.fixture
def memory_benchmark_engine(tmp_path, monkeypatch):
    """Test fixture for memory benchmarking."""
    with _reload_db(tmp_path, monkeypatch):
        monkeypatch.setenv("VDOS_LOCALE", "en")
        
        # Reload modules
        email_app_module = importlib.import_module("virtualoffice.servers.email.app")
        chat_app_module = importlib.import_module("virtualoffice.servers.chat.app")
        sim_app_module = importlib.import_module("virtualoffice.sim_manager.app")
        sim_engine_module = importlib.import_module("virtualoffice.sim_manager.engine")

        importlib.reload(email_app_module)
        importlib.reload(chat_app_module)
        importlib.reload(sim_app_module)
        importlib.reload(sim_engine_module)

        if hasattr(email_app_module, "initialise"):
            email_app_module.initialise()
        if hasattr(chat_app_module, "initialise"):
            chat_app_module.initialise()

        email_http = TestClient(email_app_module.app)
        chat_http = TestClient(chat_app_module.app)

        SimulationEngine = sim_engine_module.SimulationEngine
        create_app = sim_app_module.create_app

        # Create minimal test gateways
        class TestEmailGateway:
            def ensure_mailbox(self, address: str, display_name: str | None = None) -> None:
                pass

            def send_email(self, sender: str, to, subject: str, body: str, cc=None, bcc=None, thread_id=None) -> dict:
                return {"message_id": "test-id"}

            def close(self) -> None:
                email_http.close()

        class TestChatGateway:
            def ensure_user(self, handle: str, display_name: str | None = None) -> None:
                pass

            def send_dm(self, sender: str, recipient: str, body: str) -> dict:
                return {"message_id": "test-id"}

            def close(self) -> None:
                chat_http.close()

        class MemoryPlanner:
            """Minimal planner for memory testing."""
            def generate_project_plan(self, **kwargs) -> PlanResult:
                return PlanResult(content="Memory test plan", model_used="memory", tokens_used=1)

            def generate_daily_plan(self, **kwargs) -> PlanResult:
                return PlanResult(content="Memory daily plan", model_used="memory", tokens_used=1)

            def generate_hourly_plan(self, **kwargs) -> PlanResult:
                return PlanResult(content="Memory hourly plan", model_used="memory", tokens_used=1)

            def generate_daily_report(self, **kwargs) -> PlanResult:
                return PlanResult(content="Memory report", model_used="memory", tokens_used=1)

            def generate_simulation_report(self, **kwargs) -> PlanResult:
                return PlanResult(content="Memory sim report", model_used="memory", tokens_used=1)

        email_gateway = TestEmailGateway()
        chat_gateway = TestChatGateway()
        planner = MemoryPlanner()
        engine = SimulationEngine(
            email_gateway=email_gateway,
            chat_gateway=chat_gateway,
            planner=planner,
            hours_per_day=8,
            tick_interval_seconds=0.001
        )
        app = create_app(engine)
        client = TestClient(app)
        try:
            yield client, engine
        finally:
            client.close()
            engine.close()


def create_test_person(client, name, email, handle, is_head=False):
    """Helper function to create a test person."""
    person_payload = {
        "name": name,
        "role": "Manager" if is_head else "Developer",
        "timezone": "UTC",
        "work_hours": "09:00-18:00",
        "break_frequency": "50/10 cadence",
        "communication_style": "Direct",
        "email_address": email,
        "chat_handle": handle,
        "skills": ["Management"] if is_head else ["Development"],
        "is_department_head": is_head,
        "personality": ["Organized"],
    }
    
    response = client.post("/api/v1/people", json=person_payload)
    assert response.status_code == 201
    return response.json()


def test_memory_usage_during_long_simulation(memory_benchmark_engine):
    """Test memory usage during extended simulation."""
    client, engine = memory_benchmark_engine
    
    # Create team
    manager = create_test_person(client, "Memory Manager", "mmgr@vdos.local", "mmgr", True)
    workers = []
    for i in range(3):
        worker = create_test_person(client, f"Memory Worker {i+1}", f"mw{i+1}@vdos.local", f"mw{i+1}", False)
        workers.append(worker)
    
    all_person_ids = [manager["id"]] + [w["id"] for w in workers]
    
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Memory Test",
        "project_summary": "Memory usage testing",
        "duration_weeks": 2,
        "department_head_name": "Memory Manager",
        "include_person_ids": all_person_ids,
    })
    assert start_response.status_code == 200
    
    # Measure initial memory
    initial_memory = get_memory_usage_mb()
    
    # Run simulation for 80 ticks (2 weeks)
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 80,
        "reason": "Memory usage test"
    })
    assert advance_response.status_code == 200
    
    # Measure final memory
    final_memory = get_memory_usage_mb()
    memory_increase = final_memory - initial_memory
    
    print(f"\nMemory usage during long simulation:")
    print(f"  Initial memory: {initial_memory:.2f} MB")
    print(f"  Final memory: {final_memory:.2f} MB")
    print(f"  Memory increase: {memory_increase:.2f} MB")
    
    # Memory increase should be reasonable (< 100 MB for 80 ticks with 4 workers)
    assert memory_increase < 100, f"Excessive memory usage: {memory_increase:.2f} MB increase"


def test_memory_leak_detection(memory_benchmark_engine):
    """Test for memory leaks by running multiple simulation cycles."""
    client, engine = memory_benchmark_engine
    
    # Create minimal setup
    person = create_test_person(client, "Leak Test", "leak@vdos.local", "leak", True)
    
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Leak Test",
        "project_summary": "Memory leak detection",
        "duration_weeks": 1,
        "department_head_name": "Leak Test",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200
    
    # Measure memory at different points
    memory_samples = []
    
    for cycle in range(5):
        memory_before = get_memory_usage_mb()
        
        # Run simulation
        advance_response = client.post("/api/v1/simulation/advance", json={
            "ticks": 10,
            "reason": f"Leak test cycle {cycle}"
        })
        assert advance_response.status_code == 200
        
        memory_after = get_memory_usage_mb()
        memory_samples.append(memory_after - memory_before)
    
    # Check that memory increase is not growing with each cycle
    # Later cycles should not use significantly more memory than early cycles
    avg_early = sum(memory_samples[:2]) / 2
    avg_late = sum(memory_samples[3:]) / 2
    
    print(f"\nMemory leak detection:")
    print(f"  Memory samples: {[f'{m:.2f}' for m in memory_samples]} MB")
    print(f"  Average early cycles: {avg_early:.2f} MB")
    print(f"  Average late cycles: {avg_late:.2f} MB")
    
    # Late cycles should not use more than 2x the memory of early cycles
    if avg_early > 0:
        ratio = avg_late / avg_early
        assert ratio < 2.0, f"Possible memory leak: late cycles use {ratio:.2f}x more memory"
        print(f"  Memory growth ratio: {ratio:.2f}x")


def test_memory_usage_with_multiple_workers(memory_benchmark_engine):
    """Test that memory usage scales reasonably with worker count."""
    client, engine = memory_benchmark_engine
    
    memory_by_worker_count = {}
    
    for worker_count in [1, 3, 5]:
        # Reset simulation
        client.post("/api/v1/simulation/reset")
        
        # Create workers
        manager = create_test_person(
            client,
            f"Scale Manager {worker_count}",
            f"smgr{worker_count}@vdos.local",
            f"smgr{worker_count}",
            True
        )
        
        workers = []
        for i in range(worker_count - 1):
            worker = create_test_person(
                client,
                f"Scale Worker {worker_count}-{i+1}",
                f"sw{worker_count}-{i+1}@vdos.local",
                f"sw{worker_count}-{i+1}",
                False
            )
            workers.append(worker)
        
        all_person_ids = [manager["id"]] + [w["id"] for w in workers]
        
        start_response = client.post("/api/v1/simulation/start", json={
            "project_name": f"Scale Test {worker_count}",
            "project_summary": f"Memory scaling test with {worker_count} workers",
            "duration_weeks": 1,
            "department_head_name": f"Scale Manager {worker_count}",
            "include_person_ids": all_person_ids,
        })
        assert start_response.status_code == 200
        
        # Measure memory
        memory_before = get_memory_usage_mb()
        
        advance_response = client.post("/api/v1/simulation/advance", json={
            "ticks": 20,
            "reason": f"Memory scaling test {worker_count} workers"
        })
        assert advance_response.status_code == 200
        
        memory_after = get_memory_usage_mb()
        memory_increase = memory_after - memory_before
        
        memory_by_worker_count[worker_count] = memory_increase
    
    print(f"\nMemory usage scaling:")
    for count, memory in memory_by_worker_count.items():
        print(f"  {count} workers: {memory:.2f} MB increase")
    
    # Check that memory scales reasonably (not exponentially)
    # 5 workers should use less than 10x the memory of 1 worker
    if 1 in memory_by_worker_count and 5 in memory_by_worker_count:
        if memory_by_worker_count[1] > 0:
            scaling_factor = memory_by_worker_count[5] / memory_by_worker_count[1]
            assert scaling_factor < 10, f"Poor memory scaling: 5 workers use {scaling_factor:.1f}x more memory"
            print(f"  Scaling factor (5 vs 1): {scaling_factor:.2f}x")


def test_memory_cleanup_after_reset(memory_benchmark_engine):
    """Test that memory is properly cleaned up after simulation reset."""
    client, engine = memory_benchmark_engine
    
    # Create setup
    manager = create_test_person(client, "Cleanup Manager", "cmgr@vdos.local", "cmgr", True)
    workers = []
    for i in range(3):
        worker = create_test_person(client, f"Cleanup Worker {i+1}", f"cw{i+1}@vdos.local", f"cw{i+1}", False)
        workers.append(worker)
    
    all_person_ids = [manager["id"]] + [w["id"] for w in workers]
    
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Cleanup Test",
        "project_summary": "Memory cleanup testing",
        "duration_weeks": 1,
        "department_head_name": "Cleanup Manager",
        "include_person_ids": all_person_ids,
    })
    assert start_response.status_code == 200
    
    # Measure memory before simulation
    memory_before_sim = get_memory_usage_mb()
    
    # Run simulation
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 40,
        "reason": "Cleanup test"
    })
    assert advance_response.status_code == 200
    
    # Measure memory after simulation
    memory_after_sim = get_memory_usage_mb()
    
    # Reset simulation
    reset_response = client.post("/api/v1/simulation/reset")
    assert reset_response.status_code == 200
    
    # Measure memory after reset
    memory_after_reset = get_memory_usage_mb()
    
    sim_memory_increase = memory_after_sim - memory_before_sim
    reset_memory_decrease = memory_after_sim - memory_after_reset
    cleanup_percentage = (reset_memory_decrease / sim_memory_increase * 100) if sim_memory_increase > 0 else 0
    
    print(f"\nMemory cleanup after reset:")
    print(f"  Memory before simulation: {memory_before_sim:.2f} MB")
    print(f"  Memory after simulation: {memory_after_sim:.2f} MB")
    print(f"  Memory after reset: {memory_after_reset:.2f} MB")
    print(f"  Simulation memory increase: {sim_memory_increase:.2f} MB")
    print(f"  Reset memory decrease: {reset_memory_decrease:.2f} MB")
    print(f"  Cleanup percentage: {cleanup_percentage:.1f}%")
    
    # At least 50% of simulation memory should be cleaned up
    # (Some memory may remain due to Python's memory management)
    assert cleanup_percentage > 50 or sim_memory_increase < 1, \
        f"Insufficient memory cleanup: only {cleanup_percentage:.1f}% cleaned up"
