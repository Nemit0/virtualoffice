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

### Create Room
```http
POST /rooms
Content-Type: application/json

{
  "slug": "dashboard-team",
  "name": "Dashboard Team",
  "is_dm": false
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
POST /rooms/{room_id}/messages
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
  "room_id": 1,
  "sender": "alice",
  "body": "Authentication module is ready for testing!",
  "mentions": ["bob", "charlie"],
  "sent_at": "2024-01-15T14:30:00Z"
}
```

### Send Direct Message
```http
POST /dm
Content-Type: application/json

{
  "sender": "alice",
  "recipient": "bob",
  "body": "Can you review the auth PR when you have a moment?"
}
```

### Get Room Messages
```http
GET /rooms/{room_id}/messages?limit=50&since_id=0
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