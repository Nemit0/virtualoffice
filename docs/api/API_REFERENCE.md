# VDOS API Reference

This document provides comprehensive API documentation for all VDOS services.

## Base URLs

- **Email Server**: `http://127.0.0.1:8000`
- **Chat Server**: `http://127.0.0.1:8001`  
- **Simulation Manager**: `http://127.0.0.1:8015`

All simulation endpoints are prefixed with `/api/v1`.

## Simulation Manager API

### Simulation Control

#### Start Simulation
```http
POST /api/v1/simulation/start
Content-Type: application/json

{
  "project_name": "Dashboard MVP",
  "project_summary": "Build a metrics dashboard for team productivity",
  "duration_weeks": 2,
  "include_person_ids": [1, 2, 3],
  "exclude_person_ids": [],
  "department_head_name": "Alice Johnson",
  "model_hint": "gpt-4o",
  "random_seed": 12345
}
```

**Response:**
```json
{
  "is_running": true,
  "current_tick": 0,
  "sim_time": "Day 1 09:00",
  "project_name": "Dashboard MVP",
  "participants": ["Alice Johnson", "Bob Smith"]
}
```

#### Stop Simulation
```http
POST /api/v1/simulation/stop
```

**Response:**
```json
{
  "is_running": false,
  "current_tick": 1440,
  "sim_time": "Day 3 09:00",
  "final_stats": {
    "emails_sent": 45,
    "chat_messages_sent": 123,
    "total_tokens": 15420
  }
}
```

#### Get Simulation State
```http
GET /api/v1/simulation
```

**Response:**
```json
{
  "is_running": true,
  "current_tick": 720,
  "sim_time": "Day 2 09:00",
  "project_name": "Dashboard MVP",
  "participants": ["Alice Johnson", "Bob Smith"],
  "auto_tick": false
}
```

#### Get Auto-Pause Status
```http
GET /api/v1/simulation/auto-pause/status
```

**Response Model**: `AutoPauseStatusResponse`

**Response (enabled with active projects):**
```json
{
  "auto_pause_enabled": true,
  "should_pause": false,
  "active_projects_count": 2,
  "future_projects_count": 1,
  "current_week": 2,
  "current_tick": 90,
  "current_day": 9,
  "reason": "2 active project(s) in week 2: Dashboard MVP, Mobile App",
  "error": null
}
```

**Response (enabled, should pause):**
```json
{
  "auto_pause_enabled": true,
  "should_pause": true,
  "active_projects_count": 0,
  "future_projects_count": 0,
  "current_week": 3,
  "current_tick": 135,
  "current_day": 14,
  "reason": "All 2 project(s) completed, no future projects (week 3, tick 135)",
  "error": null
}
```

**Response (disabled):**
```json
{
  "auto_pause_enabled": false,
  "should_pause": false,
  "active_projects_count": 0,
  "future_projects_count": 0,
  "current_week": 0,
  "reason": "Auto-pause on project end is disabled",
  "error": null
}
```

**Response (error case):**
```json
{
  "auto_pause_enabled": true,
  "should_pause": false,
  "active_projects_count": 0,
  "future_projects_count": 0,
  "current_week": 0,
  "current_tick": 0,
  "current_day": 0,
  "error": "Database connection failed",
  "reason": "Failed to check project status: Database connection failed"
}
```

#### Toggle Auto-Pause Setting
```http
POST /api/v1/simulation/auto-pause/toggle
Content-Type: application/json

{
  "enabled": true
}
```

**Request Model**: `AutoPauseToggleRequest`
**Response Model**: `AutoPauseStatusResponse`

**Response:**
```json
{
  "auto_pause_enabled": true,
  "should_pause": false,
  "active_projects_count": 2,
  "future_projects_count": 1,
  "current_week": 2,
  "current_tick": 90,
  "current_day": 9,
  "reason": "2 active project(s) in week 2: Dashboard MVP, Mobile App",
  "error": null
}
```

**Error Response:**
```json
{
  "detail": "Failed to toggle auto-pause: Database connection failed"
}
```

#### Legacy Auto-Pause Status (Deprecated)
```http
GET /api/v1/simulation/auto-pause-status
```

**Status**: Deprecated - Use `GET /api/v1/simulation/auto-pause/status` instead

**Response**: Raw dictionary format (unstructured)

### Auto-Pause Integration Testing

The auto-pause functionality includes comprehensive integration tests that validate:

- **Complete workflow testing**: End-to-end auto-pause triggering when projects complete
- **Manual toggle operations**: Runtime configuration changes and state persistence
- **Multi-project scenarios**: Overlapping timelines and future project detection
- **API endpoint validation**: Request/response handling and error cases
- **Error handling**: Edge cases and recovery scenarios

**Test Coverage**:
- Project lifecycle calculations with accurate week/tick conversions
- Auto-tick integration with intelligent stopping behavior
- Session-level configuration persistence across API calls
- Multi-project timeline scenarios (overlapping, sequential, gaps)
- Future project detection preventing premature auto-pause
- Comprehensive API endpoint testing with validation
- Error handling and graceful degradation

**Test Files**:
- `tests/test_auto_pause_integration.py` - Complete integration test suite
- `tests/test_auto_pause_unit.py` - Unit tests for individual components
- `tests/test_auto_pause_workflow_integration.py` - Workflow-specific tests

#### Advance Simulation
```http
POST /api/v1/simulation/advance
Content-Type: application/json

{
  "ticks": 480,
  "reason": "manual advance"
}
```

**Response:**
```json
{
  "current_tick": 1200,
  "sim_time": "Day 3 09:00", 
  "emails_sent": 12,
  "chat_messages_sent": 28,
  "events_processed": 3,
  "plans_generated": 5
}
```

### People Management

#### Create Person
```http
POST /api/v1/people
Content-Type: application/json

{
  "name": "Alice Johnson",
  "role": "Senior Developer",
  "timezone": "Asia/Seoul",
  "work_hours": "09:00-18:00",
  "break_frequency": "50/10 cadence",
  "communication_style": "Direct, async",
  "email_address": "alice@vdos.local",
  "chat_handle": "alice",
  "is_department_head": false,
  "skills": ["Python", "FastAPI", "React"],
  "personality": ["Analytical", "Collaborative"],
  "objectives": ["Deliver high-quality code", "Mentor junior developers"],
  "metrics": ["Code review turnaround", "Bug resolution time"],
  "schedule": [
    {"start": "09:00", "end": "10:00", "activity": "Stand-up & triage"},
    {"start": "10:00", "end": "12:00", "activity": "Deep work"}
  ],
  "planning_guidelines": ["Focus on code quality", "Communicate blockers early"],
  "event_playbook": {
    "client_change": ["Assess impact", "Update estimates", "Communicate to team"]
  },
  "statuses": ["Working", "Away", "OffDuty"]
}
```

**Response:**
```json
{
  "id": 1,
  "name": "Alice Johnson",
  "role": "Senior Developer",
  "email_address": "alice@vdos.local",
  "chat_handle": "alice",
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### List People
```http
GET /api/v1/people
```

**Response:**
```json
[
  {
    "id": 1,
    "name": "Alice Johnson",
    "role": "Senior Developer",
    "email_address": "alice@vdos.local",
    "chat_handle": "alice",
    "is_department_head": false
  }
]
```

#### Get Person
```http
GET /api/v1/people/{id}
```

#### Generate Persona with AI
```http
POST /api/v1/personas/generate
Content-Type: application/json

{
  "prompt": "Full stack developer with React and Python experience"
}
```

**Locale Behavior:**
- Respects `VDOS_LOCALE` environment variable
- `VDOS_LOCALE=en` (default): Generates English personas with English names
- `VDOS_LOCALE=ko`: Generates Korean personas with Korean names and content

**Response (English locale):**
```json
{
  "persona": {
    "name": "Alex Chen",
    "role": "Full Stack Developer",
    "timezone": "UTC",
    "work_hours": "09:00-17:00",
    "break_frequency": "50/10 cadence",
    "communication_style": "Async",
    "email_address": "alex.chen@vdos.local",
    "chat_handle": "alexchen",
    "is_department_head": false,
    "skills": ["Python", "React", "PostgreSQL"],
    "personality": ["Analytical", "Collaborative"],
    "schedule": [
      {"start": "09:00", "end": "10:00", "activity": "Daily standup"}
    ]
  },
  "tokens_used": 450
}
```

**Response (Korean locale with `VDOS_LOCALE=ko`):**
```json
{
  "persona": {
    "name": "김지훈",
    "role": "풀스택 개발자",
    "timezone": "Asia/Seoul",
    "work_hours": "09:00-18:00",
    "break_frequency": "50/10 cadence",
    "communication_style": "비동기",
    "email_address": "kim.dev@vdos.local",
    "chat_handle": "kimdev",
    "is_department_head": false,
    "skills": ["Python", "React", "PostgreSQL"],
    "personality": ["분석적", "협력적"],
    "schedule": [
      {"start": "09:00", "end": "10:00", "activity": "일일 스탠드업"}
    ]
  },
  "tokens_used": 480
}
```

**Notes:**
- Requires `OPENAI_API_KEY` environment variable
- Uses GPT-4o for persona generation
- Generated persona can be directly used with `POST /api/v1/people`
- Korean locale ensures authentic Korean workplace terminology and names

#### Get Daily Reports
```http
GET /api/v1/people/{id}/daily-reports?limit=10
```

**Response:**
```json
[
  {
    "id": 1,
    "person_id": 1,
    "day_index": 1,
    "schedule_outline": "09:00-10:00 Stand-up\n10:00-12:00 Feature development",
    "report": "Completed user authentication module. Started dashboard layout.",
    "model_used": "gpt-4o",
    "tokens_used": 245,
    "created_at": "2024-01-15T18:00:00Z"
  }
]
```

#### Get Plans
```http
GET /api/v1/people/{id}/plans?plan_type=hourly&limit=5
```

**Response:**
```json
[
  {
    "id": 1,
    "person_id": 1,
    "tick": 540,
    "plan_type": "hourly",
    "content": "09:00-10:00 Review pull requests\n10:00-11:00 Implement user service",
    "model_used": "gpt-4o",
    "tokens_used": 180,
    "created_at": "2024-01-15T09:00:00Z"
  }
]
```

### Events

#### Inject Event
```http
POST /api/v1/events
Content-Type: application/json

{
  "type": "client_change",
  "target_ids": [1, 2],
  "at_tick": 720,
  "payload": {
    "change": "Add multi-factor authentication",
    "impact": "2 additional days of work",
    "priority": "high"
  }
}
```

**Response:**
```json
{
  "id": 1,
  "type": "client_change",
  "target_ids": [1, 2],
  "at_tick": 720,
  "payload": {
    "change": "Add multi-factor authentication",
    "impact": "2 additional days of work", 
    "priority": "high"
  },
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### List Events
```http
GET /api/v1/events?limit=20
```

### Export/Import

#### Export Personas
```http
GET /api/v1/export/personas
```

**Response:**
```json
{
  "export_type": "personas",
  "export_timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0",
  "personas": [
    {
      "name": "Alice Johnson",
      "role": "Senior Developer",
      "timezone": "UTC",
      "work_hours": "09:00-17:00",
      "break_frequency": "50/10 cadence",
      "communication_style": "Async",
      "email_address": "alice@vdos.local",
      "chat_handle": "alice",
      "is_department_head": false,
      "team_name": "Engineering",
      "skills": ["Python", "FastAPI"],
      "personality": ["Analytical", "Collaborative"],
      "objectives": ["Deliver quality code"],
      "metrics": ["Code review time"],
      "planning_guidelines": ["Focus on testing"],
      "schedule": [
        {"start": "09:00", "end": "10:00", "activity": "Planning"}
      ],
      "event_playbook": {},
      "statuses": ["Working", "Away"]
    }
  ]
}
```

#### Import Personas
```http
POST /api/v1/import/personas
Content-Type: application/json

{
  "export_type": "personas",
  "export_timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0",
  "personas": [
    {
      "name": "Bob Smith",
      "role": "Designer",
      "timezone": "UTC",
      "work_hours": "09:00-17:00",
      "break_frequency": "50/10 cadence",
      "communication_style": "Visual",
      "email_address": "bob@vdos.local",
      "chat_handle": "bob",
      "is_department_head": false,
      "team_name": "Design",
      "skills": ["UI/UX", "Figma"],
      "personality": ["Creative", "Detail-oriented"],
      "objectives": ["Create intuitive interfaces"],
      "metrics": ["User satisfaction"],
      "planning_guidelines": ["User-first approach"],
      "schedule": [
        {"start": "09:00", "end": "10:00", "activity": "Design review"}
      ],
      "event_playbook": {},
      "statuses": ["Working", "Away"]
    }
  ]
}
```

**Response:**
```json
{
  "imported_count": 1,
  "skipped_count": 0,
  "total_processed": 1,
  "errors": [],
  "message": "Successfully imported 1 personas, skipped 0"
}
```

#### Export Projects
```http
GET /api/v1/export/projects
```

**Response:**
```json
{
  "export_type": "projects",
  "export_timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0",
  "projects": [
    {
      "project_name": "Dashboard MVP",
      "project_summary": "Build a metrics dashboard for team productivity",
      "start_week": 1,
      "duration_weeks": 2,
      "assigned_person_ids": []
    }
  ]
}
```

#### Import Projects
```http
POST /api/v1/import/projects
Content-Type: application/json

{
  "export_type": "projects",
  "export_timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0",
  "projects": [
    {
      "project_name": "Mobile App",
      "project_summary": "Develop mobile companion app",
      "start_week": 3,
      "duration_weeks": 4,
      "assigned_person_ids": [1, 2, 3]
    }
  ]
}
```

**Response:**
```json
{
  "validated_projects": [
    {
      "project_name": "Mobile App",
      "project_summary": "Develop mobile companion app",
      "start_week": 3,
      "duration_weeks": 4,
      "assigned_person_ids": [1, 2, 3]
    }
  ],
  "valid_count": 1,
  "error_count": 0,
  "total_processed": 1,
  "errors": [],
  "message": "Validated 1 projects, 0 errors found"
}
```

### Chat Monitoring

#### Monitor Chat Messages for Person
```http
GET /api/v1/monitor/chat/messages/{person_id}?scope=all&limit=50&since_id=0
```

**Parameters:**
- `person_id` (path): ID of the person to monitor
- `scope` (query): Filter scope - `all`, `dms`, or `rooms` (default: `all`)
- `limit` (query): Maximum number of messages to return (default: 50)
- `since_id` (query): Return messages with ID greater than this value (default: 0)

**Response:**
```json
{
  "dms": [
    {
      "id": 1,
      "sender": "alice",
      "recipient": "bob",
      "body": "Can you review the auth PR?",
      "sent_at": "2024-01-15T14:30:00Z"
    }
  ],
  "rooms": [
    {
      "id": 2,
      "room_id": 1,
      "room_slug": "dashboard-team",
      "sender": "alice",
      "body": "Authentication module is ready!",
      "mentions": ["bob"],
      "sent_at": "2024-01-15T14:35:00Z"
    }
  ]
}
```

#### Monitor Room Messages
```http
GET /api/v1/monitor/chat/room/{room_slug}/messages?limit=50&since_id=0
```

**Parameters:**
- `room_slug` (path): Slug identifier of the room
- `limit` (query): Maximum number of messages to return (default: 50)
- `since_id` (query): Return messages with ID greater than this value (default: 0)

**Response:**
```json
[
  {
    "id": 2,
    "room_id": 1,
    "sender": "alice",
    "body": "Authentication module is ready for testing!",
    "mentions": ["bob", "charlie"],
    "sent_at": "2024-01-15T14:30:00Z"
  },
  {
    "id": 3,
    "room_id": 1,
    "sender": "bob",
    "body": "Great! I'll test it now.",
    "mentions": [],
    "sent_at": "2024-01-15T14:32:00Z"
  }
]
```

### Reports and Analytics

#### Get Simulation Reports
```http
GET /api/v1/simulation/reports
```

**Response:**
```json
[
  {
    "id": 1,
    "total_ticks": 2400,
    "report": "Project completed successfully. Team delivered dashboard with authentication.",
    "model_used": "gpt-4o",
    "tokens_used": 320,
    "created_at": "2024-01-20T18:00:00Z"
  }
]
```

#### Get Token Usage
```http
GET /api/v1/simulation/token-usage
```

**Response:**
```json
{
  "total_tokens": 15420,
  "per_model": {
    "gpt-4o": 12340,
    "gpt-4o-mini": 3080
  },
  "by_operation": {
    "project_planning": 2500,
    "daily_planning": 4200,
    "hourly_planning": 6800,
    "daily_reports": 1920
  }
}
```

#### Get Volume Metrics (v2.0)
```http
GET /api/v1/simulation/volume-metrics
```

**Purpose:** Monitor email and chat volume for debugging and validating the Email Volume Reduction system (v2.0).

**Response:**
```json
{
  "day_index": 2,
  "current_tick": 960,
  "total_emails_today": 45,
  "total_chats_today": 78,
  "avg_emails_per_person": 3.75,
  "avg_chats_per_person": 6.5,
  "json_communication_rate": 0.65,
  "inbox_reply_rate": 0.35,
  "threading_rate": 0.32,
  "daily_limits_hit": [
    {
      "person_id": 3,
      "channel": "email",
      "limit": 50
    }
  ],
  "emails_by_person": {
    "1": 4,
    "2": 3,
    "3": 50,
    "4": 5
  },
  "chats_by_person": {
    "1": 8,
    "2": 6,
    "3": 12,
    "4": 7
  }
}
```

**Response Fields:**
- `day_index`: Current simulation day (0-indexed)
- `current_tick`: Current simulation tick
- `total_emails_today`: Total emails sent today across all personas
- `total_chats_today`: Total chats sent today across all personas
- `avg_emails_per_person`: Average emails per active persona today
- `avg_chats_per_person`: Average chats per active persona today
- `json_communication_rate`: Ratio of JSON communications (from hourly plans) to total
- `inbox_reply_rate`: Ratio of inbox-driven replies to total communications
- `threading_rate`: Email threading rate (from quality metrics)
- `daily_limits_hit`: List of personas that reached daily limits (safety net)
- `emails_by_person`: Email count per person ID
- `chats_by_person`: Chat count per person ID

**Use Cases:**
- Monitor email volume reduction effectiveness (target: 80-85% reduction)
- Verify daily limits are working (50 emails/day, 100 chats/day per persona)
- Track JSON communication rate (target: 40-50%)
- Track inbox reply rate (target: ~30%)
- Debug volume spikes or unexpected patterns
- Validate Email Volume Reduction v2.0 implementation

**Related Configuration:**
- `VDOS_ENABLE_AUTO_FALLBACK` - Enable/disable automatic fallback (default: false)
- `VDOS_ENABLE_INBOX_REPLIES` - Enable inbox-driven replies (default: true)
- `VDOS_INBOX_REPLY_PROBABILITY` - Reply probability 0.0-1.0 (default: 0.65)
- `VDOS_MAX_EMAILS_PER_DAY` - Daily email limit per persona (default: 50)
- `VDOS_MAX_CHATS_PER_DAY` - Daily chat limit per persona (default: 100)

## Email Server API

### Send Email
```http
POST /emails/send
Content-Type: application/json

{
  "sender": "alice@vdos.local",
  "recipients": ["bob@vdos.local"],
  "cc": [],
  "bcc": [],
  "subject": "Dashboard progress update",
  "body": "Hi Bob,\n\nThe authentication module is complete. Ready for your review.\n\nBest,\nAlice",
  "thread_id": "dashboard-auth-123"
}
```

**Response:**
```json
{
  "id": 1,
  "sender": "alice@vdos.local",
  "subject": "Dashboard progress update",
  "thread_id": "dashboard-auth-123",
  "sent_at": "2024-01-15T14:30:00Z"
}
```

### Get Mailbox Emails
```http
GET /mailboxes/{address}/emails?limit=20&since_id=0
```

**Response:**
```json
[
  {
    "id": 1,
    "sender": "bob@vdos.local",
    "subject": "Re: Dashboard progress update",
    "body": "Great work Alice! I'll review this afternoon.",
    "thread_id": "dashboard-auth-123",
    "sent_at": "2024-01-15T15:00:00Z"
  }
]
```

### Save Draft
```http
POST /mailboxes/{address}/drafts
Content-Type: application/json

{
  "subject": "Weekly status update",
  "body": "Draft content here...",
  "recipients": ["team@vdos.local"]
}
```

### Get Drafts
```http
GET /mailboxes/{address}/drafts
```

## Chat Server API

### Create User
```http
PUT /users/{handle}
Content-Type: application/json

{
  "display_name": "Alice Johnson"
}
```

**Response:**
```json
{
  "handle": "alice",
  "display_name": "Alice Johnson",
  "created_at": "2024-01-15T10:00:00Z"
}
```

### Create Room
```http
POST /rooms
Content-Type: application/json

{
  "slug": "dashboard-team",
  "name": "Dashboard Team",
  "is_dm": false,
  "participants": ["alice", "bob", "charlie"]
}
```

**Response:**
```json
{
  "id": 1,
  "slug": "dashboard-team",
  "name": "Dashboard Team",
  "is_dm": false,
  "created_at": "2024-01-15T10:00:00Z"
}
```

### Post Message to Room
```http
POST /rooms/{room_slug}/messages
Content-Type: application/json

{
  "sender": "alice",
  "body": "Authentication module is ready for testing!",
  "mentions": ["bob", "charlie"]
}
```

**Response:**
```json
{
  "id": 1,
  "room_slug": "dashboard-team",
  "sender": "alice",
  "body": "Authentication module is ready for testing!",
  "mentions": ["bob", "charlie"],
  "sent_at": "2024-01-15T14:30:00Z"
}
```

### Send Direct Message
```http
POST /dms
Content-Type: application/json

{
  "sender": "alice",
  "recipient": "bob",
  "body": "Can you review the auth PR when you have a moment?"
}
```

**Response:**
```json
{
  "id": 1,
  "sender": "alice",
  "recipient": "bob",
  "body": "Can you review the auth PR when you have a moment?",
  "room_slug": "dm:alice:bob",
  "sent_at": "2024-01-15T14:30:00Z"
}
```

### Get User Rooms
```http
GET /users/{handle}/rooms
```

**Response:**
```json
[
  {
    "id": 1,
    "slug": "project-alpha",
    "name": "Project Alpha",
    "is_dm": false,
    "participants": ["alice", "bob", "charlie"],
    "created_at": "2024-01-15T10:00:00Z"
  }
]
```

### Get User Direct Messages
```http
GET /users/{handle}/dms
```

**Response:**
```json
[
  {
    "id": 1,
    "sender": "bob",
    "recipient": "alice", 
    "body": "Sure, I'll take a look today",
    "room_slug": "dm:alice:bob",
    "sent_at": "2024-01-15T14:32:00Z"
  }
]
```

### Get Room Messages
```http
GET /rooms/{room_slug}/messages?limit=50&since_id=0
```

**Response:**
```json
[
  {
    "id": 1,
    "room_slug": "project-alpha",
    "sender": "alice",
    "body": "Hey team, let's start the project discussion",
    "sent_at": "2024-01-15T14:30:00Z"
  }
]
```

### Get DM History
```http
GET /dm/{handle1}/{handle2}?limit=50
```

## Error Responses

All APIs use standard HTTP status codes:

- `200 OK` - Success
- `201 Created` - Resource created successfully
- `400 Bad Request` - Invalid request data
- `404 Not Found` - Resource not found
- `422 Unprocessable Entity` - Validation error
- `500 Internal Server Error` - Server error

**Error Response Format:**
```json
{
  "detail": "Validation error message",
  "errors": [
    {
      "field": "email_address",
      "message": "Invalid email format"
    }
  ]
}
```

## Rate Limits

- Hourly planning: Maximum 10 plans per person per minute
- Contact cooldown: Minimum 10 ticks between same sender/recipient pairs
- Token usage: Monitored but not limited (depends on OpenAI API limits)

## Authentication

Currently, VDOS APIs do not require authentication. This is suitable for development and testing environments. For production use, consider adding API key authentication or other security measures.

## WebSocket Support

VDOS currently uses HTTP REST APIs only. Real-time updates are achieved through polling. WebSocket support may be added in future versions for real-time simulation monitoring.