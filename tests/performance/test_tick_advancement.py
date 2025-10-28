"""
Performance benchmarks for tick advancement.

Tests that measure the speed of tick advancement to ensure
no performance regression in the refactored engine.
"""

import importlib
import time
from contextlib import contextmanager
from pathlib import Path

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


@pytest.fixture
def benchmark_engine(tmp_path, monkeypatch):
    """Test fixture for performance benchmarking."""
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

        class FastPlanner:
            """Minimal planner for performance testing."""
            def generate_project_plan(self, **kwargs) -> PlanResult:
                return PlanResult(content="Fast plan", model_used="fast", tokens_used=1)

            def generate_daily_plan(self, **kwargs) -> PlanResult:
                return PlanResult(content="Fast daily", model_used="fast", tokens_used=1)

            def generate_hourly_plan(self, **kwargs) -> PlanResult:
                return PlanResult(content="Fast hourly", model_used="fast", tokens_used=1)

            def generate_daily_report(self, **kwargs) -> PlanResult:
                return PlanResult(content="Fast report", model_used="fast", tokens_used=1)

            def generate_simulation_report(self, **kwargs) -> PlanResult:
                return PlanResult(content="Fast sim report", model_used="fast", tokens_used=1)

        email_gateway = TestEmailGateway()
        chat_gateway = TestChatGateway()
        planner = FastPlanner()
        engine = SimulationEngine(
            email_gateway=email_gateway,
            chat_gateway=chat_gateway,
            planner=planner,
            hours_per_day=8,
            tick_interval_seconds=0.001  # Very fast for benchmarking
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


def test_single_tick_advancement_speed(benchmark_engine):
    """Benchmark single tick advancement speed."""
    client, engine = benchmark_engine
    
    # Create minimal setup
    person = create_test_person(client, "Benchmark User", "bench@vdos.local", "bench", True)
    
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Benchmark Project",
        "project_summary": "Performance testing",
        "duration_weeks": 1,
        "department_head_name": "Benchmark User",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200
    
    # Benchmark single tick advancement
    iterations = 10
    start_time = time.perf_counter()
    
    for i in range(iterations):
        advance_response = client.post("/api/v1/simulation/advance", json={
            "ticks": 1,
            "reason": f"Benchmark iteration {i}"
        })
        assert advance_response.status_code == 200
    
    end_time = time.perf_counter()
    elapsed = end_time - start_time
    avg_per_tick = elapsed / iterations
    
    # Target: < 100ms per tick (should be much faster with minimal planner)
    assert avg_per_tick < 0.1, f"Tick advancement too slow: {avg_per_tick:.3f}s per tick"
    
    print(f"\nSingle tick advancement: {avg_per_tick*1000:.2f}ms per tick")


def test_bulk_tick_advancement_speed(benchmark_engine):
    """Benchmark bulk tick advancement speed."""
    client, engine = benchmark_engine
    
    # Create minimal setup
    person = create_test_person(client, "Bulk Benchmark", "bulk@vdos.local", "bulk", True)
    
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Bulk Benchmark",
        "project_summary": "Bulk performance testing",
        "duration_weeks": 1,
        "department_head_name": "Bulk Benchmark",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200
    
    # Benchmark bulk advancement (40 ticks = 1 week)
    start_time = time.perf_counter()
    
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 40,
        "reason": "Bulk benchmark"
    })
    assert advance_response.status_code == 200
    
    end_time = time.perf_counter()
    elapsed = end_time - start_time
    avg_per_tick = elapsed / 40
    
    # Target: < 50ms per tick for bulk operations
    assert avg_per_tick < 0.05, f"Bulk tick advancement too slow: {avg_per_tick:.3f}s per tick"
    
    print(f"\nBulk tick advancement (40 ticks): {elapsed:.2f}s total, {avg_per_tick*1000:.2f}ms per tick")


def test_multi_worker_tick_advancement(benchmark_engine):
    """Benchmark tick advancement with multiple workers."""
    client, engine = benchmark_engine
    
    # Create team of 5 workers
    manager = create_test_person(client, "Team Manager", "mgr@vdos.local", "mgr", True)
    workers = []
    for i in range(4):
        worker = create_test_person(client, f"Worker {i+1}", f"w{i+1}@vdos.local", f"w{i+1}", False)
        workers.append(worker)
    
    all_person_ids = [manager["id"]] + [w["id"] for w in workers]
    
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Multi-Worker Benchmark",
        "project_summary": "Multi-worker performance testing",
        "duration_weeks": 1,
        "department_head_name": "Team Manager",
        "include_person_ids": all_person_ids,
    })
    assert start_response.status_code == 200
    
    # Benchmark with 5 workers
    start_time = time.perf_counter()
    
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 20,
        "reason": "Multi-worker benchmark"
    })
    assert advance_response.status_code == 200
    
    end_time = time.perf_counter()
    elapsed = end_time - start_time
    avg_per_tick = elapsed / 20
    
    # Target: < 200ms per tick with 5 workers
    assert avg_per_tick < 0.2, f"Multi-worker tick advancement too slow: {avg_per_tick:.3f}s per tick"
    
    print(f"\nMulti-worker (5 workers, 20 ticks): {elapsed:.2f}s total, {avg_per_tick*1000:.2f}ms per tick")


def test_tick_advancement_scaling(benchmark_engine):
    """Test that tick advancement scales linearly with worker count."""
    client, engine = benchmark_engine
    
    results = {}
    
    for worker_count in [1, 3, 5]:
        # Create workers
        manager = create_test_person(
            client, 
            f"Manager {worker_count}", 
            f"mgr{worker_count}@vdos.local", 
            f"mgr{worker_count}", 
            True
        )
        
        workers = []
        for i in range(worker_count - 1):
            worker = create_test_person(
                client,
                f"Worker {worker_count}-{i+1}",
                f"w{worker_count}-{i+1}@vdos.local",
                f"w{worker_count}-{i+1}",
                False
            )
            workers.append(worker)
        
        all_person_ids = [manager["id"]] + [w["id"] for w in workers]
        
        start_response = client.post("/api/v1/simulation/start", json={
            "project_name": f"Scaling Test {worker_count}",
            "project_summary": f"Scaling test with {worker_count} workers",
            "duration_weeks": 1,
            "department_head_name": f"Manager {worker_count}",
            "include_person_ids": all_person_ids,
        })
        assert start_response.status_code == 200
        
        # Benchmark
        start_time = time.perf_counter()
        
        advance_response = client.post("/api/v1/simulation/advance", json={
            "ticks": 10,
            "reason": f"Scaling test {worker_count} workers"
        })
        assert advance_response.status_code == 200
        
        end_time = time.perf_counter()
        elapsed = end_time - start_time
        
        results[worker_count] = elapsed
        
        # Reset for next iteration
        client.post("/api/v1/simulation/reset")
    
    # Check that scaling is reasonable (not exponential)
    # 5 workers should take less than 10x the time of 1 worker
    if 1 in results and 5 in results:
        scaling_factor = results[5] / results[1]
        assert scaling_factor < 10, f"Poor scaling: 5 workers took {scaling_factor:.1f}x longer than 1 worker"
        
        print(f"\nScaling results:")
        for count, elapsed in results.items():
            print(f"  {count} workers: {elapsed:.3f}s for 10 ticks")
        print(f"  Scaling factor (5 vs 1): {scaling_factor:.2f}x")


def test_event_processing_performance(benchmark_engine):
    """Benchmark event processing performance."""
    client, engine = benchmark_engine
    
    # Create setup
    person = create_test_person(client, "Event Test", "event@vdos.local", "event", True)
    
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Event Test",
        "project_summary": "Event processing performance",
        "duration_weeks": 1,
        "department_head_name": "Event Test",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200
    
    # Inject multiple events
    event_count = 10
    for i in range(event_count):
        event_response = client.post("/api/v1/events", json={
            "event_type": "client_request",
            "description": f"Test event {i}",
            "target_person_id": person["id"],
            "tick": i + 5,
        })
        assert event_response.status_code == 201
    
    # Benchmark processing events
    start_time = time.perf_counter()
    
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 20,
        "reason": "Event processing benchmark"
    })
    assert advance_response.status_code == 200
    
    end_time = time.perf_counter()
    elapsed = end_time - start_time
    
    # Target: < 100ms per tick even with events
    avg_per_tick = elapsed / 20
    assert avg_per_tick < 0.1, f"Event processing too slow: {avg_per_tick:.3f}s per tick"
    
    print(f"\nEvent processing ({event_count} events, 20 ticks): {elapsed:.2f}s total, {avg_per_tick*1000:.2f}ms per tick")
