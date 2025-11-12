# PeopleRepository

Location: `src/virtualoffice/sim_manager/core/people_repository.py`

Database access layer for people and their schedules.

Responsibilities
- List/get/insert/delete people
- Map DB rows ↔ `PersonRead` models (including `ScheduleBlockIn`)
- Read schedules for a person
- Coerce legacy empty arrays for `skills`/`personality` to safe defaults

Key Methods
- `list_people() -> list[PersonRead]`
- `get_person(person_id: int) -> PersonRead`
- `find_by_name(name: str) -> PersonRead | None`
- `delete_by_name(name: str) -> bool`
- `insert(payload: PersonCreate, persona_markdown: str, schedule_blocks: list) -> int`

