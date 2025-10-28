# WorkerRegistry

Location: `src/virtualoffice/sim_manager/core/worker_registry.py`

Manages `VirtualWorker` lifecycle and hides lazy imports to avoid circular dependencies.

Responsibilities
- Determine if the configured planner supports `generate_with_messages`
- Create `VirtualWorker` instances for personas on demand
- Keep a cache `workers: dict[person_id, VirtualWorker]`

Key Methods
- `supports_virtual_workers() -> bool`
- `sync_workers(people: Sequence[PersonRead]) -> None`
- `ensure_worker(person: PersonRead) -> None`

Notes
- Reconstructs `WorkerPersona` from `PersonRead`
- Converts `schedule` into `ScheduleBlock` for VirtualWorker construction

