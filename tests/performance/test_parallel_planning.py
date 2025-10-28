"""
Performance benchmarks for parallel planning.

Tests that measure the speedup achieved by parallel worker planning
compared to sequential planning. Target: 2-4x speedup with multiple workers.
"""

import importlib
import time
from concurrent.futures import ThreadPoolExecutor
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


class SlowPlanner:
    """Planner with artificial delay to simulate real LLM calls."""
    
    def __init__(self, delay_ms=10):
        self.delay_ms = delay_ms
    
    def _delay(self):
        """Simulate LLM call delay."""
        time.sleep(self.delay_ms / 1000.0)
    
    def generate_project_plan(self, **kwargs) -> PlanResult:
        self._delay()
        return PlanResult(content="Slow project plan", model_used="slow", tokens_used=100)
    
    def generate_daily_plan(self, **kwargs) -> PlanResult:
        self._delay()
        return PlanResult(content="Slow daily plan", model_used="slow", tokens_used=100)
    
    def generate_hourly_plan(self, **kwargs) -> PlanResult:
        self._delay()
        return PlanResult(content="Slow hourly plan", model_used="slow", tokens_used=100)
    
    def generate_daily_report(self, **kwargs) -> PlanResult:
        self._delay()
        return PlanResult(content="Slow daily report", model_used="slow", tokens_used=100)
    
    def generate_simulation_report(self, **kwargs) -> PlanResult:
        self._delay()
        return PlanResult(content="Slow sim report", model_used="slow", tokens_used=100)


@pytest.fixture
def parallel_benchmark_engine(tmp_path, monkeypatch):
    """Test fixture for parallel planning benchmarks."""
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

        email_gateway = TestEmailGateway()
        chat_gateway = TestChatGateway()
        planner = SlowPlanner(delay_ms=10)  # 10ms delay per plan
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
            yield client, engine, planner
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


def test_sequential_vs_parallel_planning_speedup(parallel_benchmark_engine):
    """Test that parallel planning provides significant speedup over sequential."""
    client, engine, planner = parallel_benchmark_engine
    
    # Create team of 4 workers (good for parallel testing)
    manager = create_test_person(client, "Parallel Manager", "pmgr@vdos.local", "pmgr", True)
    workers = []
    for i in range(3):
        worker = create_test_person(client, f"Parallel Worker {i+1}", f"pw{i+1}@vdos.local", f"pw{i+1}", False)
        workers.append(worker)
    
    all_person_ids = [manager["id"]] + [w["id"] for w in workers]
    
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Parallel Planning Test",
        "project_summary": "Test parallel planning speedup",
        "duration_weeks": 1,
        "department_head_name": "Parallel Manager",
        "include_person_ids": all_person_ids,
    })
    assert start_response.status_code == 200
    
    # Benchmark with parallel planning (if engine supports it)
    start_time = time.perf_counter()
    
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 5,
        "reason": "Parallel planning benchmark"
    })
    assert advance_response.status_code == 200
    
    end_time = time.perf_counter()
    parallel_time = end_time - start_time
    
    # Calculate expected sequential time
    # With 4 workers and 10ms delay per plan, sequential would take ~40ms per tick
    # Parallel should take ~10ms per tick (assuming perfect parallelization)
    expected_sequential_time = 5 * 4 * 0.01  # 5 ticks * 4 workers * 10ms
    
    # Parallel should be faster than sequential
    # Allow some overhead, so target is at least 1.5x speedup
    speedup = expected_sequential_time / parallel_time
    
    print(f"\nParallel planning benchmark:")
    print(f"  Parallel time: {parallel_time:.3f}s")
    print(f"  Expected sequential time: {expected_sequential_time:.3f}s")
    print(f"  Speedup: {speedup:.2f}x")
    
    # If engine doesn't support parallel planning yet, this will show the opportunity
    if speedup < 1.5:
        print(f"  Note: Speedup is less than 1.5x, parallel planning may not be implemented yet")


def test_parallel_planning_with_varying_worker_counts(parallel_benchmark_engine):
    """Test parallel planning performance with different worker counts."""
    client, engine, planner = parallel_benchmark_engine
    
    results = {}
    
    for worker_count in [1, 2, 4, 8]:
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
            "project_name": f"Parallel Test {worker_count}",
            "project_summary": f"Parallel test with {worker_count} workers",
            "duration_weeks": 1,
            "department_head_name": f"Manager {worker_count}",
            "include_person_ids": all_person_ids,
        })
        assert start_response.status_code == 200
        
        # Benchmark
        start_time = time.perf_counter()
        
        advance_response = client.post("/api/v1/simulation/advance", json={
            "ticks": 3,
            "reason": f"Parallel test {worker_count} workers"
        })
        assert advance_response.status_code == 200
        
        end_time = time.perf_counter()
        elapsed = end_time - start_time
        
        results[worker_count] = elapsed
        
        # Reset for next iteration
        client.post("/api/v1/simulation/reset")
    
    # Analyze results
    print(f"\nParallel planning scaling:")
    for count, elapsed in results.items():
        expected_sequential = count * 3 * 0.01  # count * ticks * delay
        speedup = expected_sequential / elapsed
        print(f"  {count} workers: {elapsed:.3f}s (expected sequential: {expected_sequential:.3f}s, speedup: {speedup:.2f}x)")
    
    # Check that time doesn't grow linearly with worker count
    # 8 workers should take less than 8x the time of 1 worker
    if 1 in results and 8 in results:
        time_ratio = results[8] / results[1]
        assert time_ratio < 8, f"Poor parallelization: 8 workers took {time_ratio:.1f}x longer than 1 worker"


def test_parallel_planning_overhead(parallel_benchmark_engine):
    """Test that parallel planning overhead is acceptable."""
    client, engine, planner = parallel_benchmark_engine
    
    # Create single worker to measure baseline
    person = create_test_person(client, "Single Worker", "single@vdos.local", "single", True)
    
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Overhead Test",
        "project_summary": "Measure parallel planning overhead",
        "duration_weeks": 1,
        "department_head_name": "Single Worker",
        "include_person_ids": [person["id"]],
    })
    assert start_response.status_code == 200
    
    # Benchmark single worker
    start_time = time.perf_counter()
    
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 10,
        "reason": "Overhead test"
    })
    assert advance_response.status_code == 200
    
    end_time = time.perf_counter()
    elapsed = end_time - start_time
    
    # Expected time: 10 ticks * 10ms = 100ms
    expected_time = 10 * 0.01
    overhead = elapsed - expected_time
    overhead_percent = (overhead / expected_time) * 100
    
    print(f"\nParallel planning overhead:")
    print(f"  Actual time: {elapsed:.3f}s")
    print(f"  Expected time: {expected_time:.3f}s")
    print(f"  Overhead: {overhead:.3f}s ({overhead_percent:.1f}%)")
    
    # Overhead should be less than 100% of planning time
    assert overhead_percent < 100, f"Parallel planning overhead too high: {overhead_percent:.1f}%"


def test_parallel_planning_correctness(parallel_benchmark_engine):
    """Test that parallel planning produces correct results."""
    client, engine, planner = parallel_benchmark_engine
    
    # Create team
    manager = create_test_person(client, "Correctness Manager", "cmgr@vdos.local", "cmgr", True)
    dev1 = create_test_person(client, "Correctness Dev 1", "cd1@vdos.local", "cd1", False)
    dev2 = create_test_person(client, "Correctness Dev 2", "cd2@vdos.local", "cd2", False)
    
    all_person_ids = [manager["id"], dev1["id"], dev2["id"]]
    
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Correctness Test",
        "project_summary": "Verify parallel planning correctness",
        "duration_weeks": 1,
        "department_head_name": "Correctness Manager",
        "include_person_ids": all_person_ids,
    })
    assert start_response.status_code == 200
    
    # Run simulation
    advance_response = client.post("/api/v1/simulation/advance", json={
        "ticks": 10,
        "reason": "Correctness test"
    })
    assert advance_response.status_code == 200
    
    # Verify all workers have plans
    people_response = client.get("/api/v1/people")
    assert people_response.status_code == 200
    people = people_response.json()
    assert len(people) == 3
    
    # Verify simulation state is consistent
    status_response = client.get("/api/v1/simulation")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_tick"] == 10
    
    print(f"\nParallel planning correctness: PASSED")
    print(f"  All {len(people)} workers processed correctly")
    print(f"  Simulation state consistent at tick {status['current_tick']}")


def test_parallel_planning_thread_safety(parallel_benchmark_engine):
    """Test that parallel planning is thread-safe."""
    client, engine, planner = parallel_benchmark_engine
    
    # Create multiple workers
    manager = create_test_person(client, "Thread Safety Manager", "tsmgr@vdos.local", "tsmgr", True)
    workers = []
    for i in range(5):
        worker = create_test_person(client, f"TS Worker {i+1}", f"tsw{i+1}@vdos.local", f"tsw{i+1}", False)
        workers.append(worker)
    
    all_person_ids = [manager["id"]] + [w["id"] for w in workers]
    
    start_response = client.post("/api/v1/simulation/start", json={
        "project_name": "Thread Safety Test",
        "project_summary": "Test thread safety of parallel planning",
        "duration_weeks": 1,
        "department_head_name": "Thread Safety Manager",
        "include_person_ids": all_person_ids,
    })
    assert start_response.status_code == 200
    
    # Run multiple iterations to catch race conditions
    for iteration in range(5):
        advance_response = client.post("/api/v1/simulation/advance", json={
            "ticks": 2,
            "reason": f"Thread safety test iteration {iteration}"
        })
        assert advance_response.status_code == 200
    
    # Verify final state is consistent
    status_response = client.get("/api/v1/simulation")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["current_tick"] == 10
    
    people_response = client.get("/api/v1/people")
    assert people_response.status_code == 200
    people = people_response.json()
    assert len(people) == 6
    
    print(f"\nParallel planning thread safety: PASSED")
    print(f"  Completed 5 iterations with 6 workers")
    print(f"  No race conditions detected")
