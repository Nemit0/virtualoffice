# Chat Server API Reference

## Overview

The Chat Server provides real-time messaging capabilities for the VDOS simulation, supporting both room-based conversations and direct messages between personas. It runs on port 8001 by default and integrates with the Simulation Manager for monitoring and data access.

**Base URL**: `http://127.0.0.1:8001`  
**API Version**: v1  
**Content-Type**: `application/json`

## Authentication

Currently, the Chat Server operates without authentication in the simulation environment. All endpoints are publicly accessible.

## Core Concepts

### Rooms
- **Project Rooms**: Automatically created for each simulation project
- **General Rooms**: Created manually or through simulation events
- **DM Rooms**: Special rooms for direct messages between two participants

### Messages
- **Room Messages**: Sent to all room participants
- **Direct Messages**: Private messages between two users
- **Mentions**: Messages can mention specific users with @username syntax

### Users
- **Auto-provisioning**: Users are automatically created when referenced
- **Chat Handles**: Each persona has a unique chat handle for identification

## Endpoints

### Room Management

#### Create Room
```http
POST /rooms
Content-Type: application/json

{
  "name": "project-alpha",
  "participants": ["alice", "bob"],
  "slug": "project-alpha"
}
```

**Response:**
```json
{
  "slug": "project-alpha",
  "name": "project-alpha", 
  "participants": ["alice", "bob"],
  "is_dm": false,
  "created_at": "2025-10-23T10:00:00Z"
}
```

#### Get User's Rooms
```http
GET /users/{handle}/rooms
```

**Example:**
```http
GET /users/alice/rooms
```

**Response:**
```json
[
  {
    "slug": "project-alpha",
    "name": "project-alpha",
    "participants": ["alice", "bob", "charlie"],
    "is_dm": false,
    "created_at": "2025-10-23T09:00:00Z"
  },
  {
    "slug": "dm:alice:bob", 
    "name": "bob",
    "participants": ["alice", "bob"],
    "is_dm": true,
    "created_at": "2025-10-23T09:30:00Z"
  }
]
```

### Message Management

#### Send Room Message
```http
POST /rooms/{room_slug}/messages
Content-Type: application/json

{
  "sender": "alice",
  "body": "Hey team, let's discuss the project requirements."
}
```

**Response:**
```json
{
  "id": 1,
  "room_slug": "project-alpha",
  "sender": "alice",
  "body": "Hey team, let's discuss the project requirements.",
  "sent_at": "2025-10-23T10:00:00Z",
  "mentions": []
}
```

#### Get Room Messages
```http
GET /rooms/{room_slug}/messages?since_id=0&since_timestamp=&before_timestamp=&limit=100
```

**Query Parameters:**
- `since_id` (optional): Only return messages with ID greater than this value (for polling new messages).
- `since_timestamp` (optional): Only return messages sent after this ISO timestamp.
- `before_timestamp` (optional): Only return messages sent on or before this ISO timestamp (for replay mode).
- `limit` (optional): Maximum number of messages to return (chronological order).

**Example:**
```http
GET /rooms/project-alpha/messages?limit=50
```

**Response:**
```json
[
  {
    "id": 1,
    "room_slug": "project-alpha",
    "sender": "alice",
    "body": "Hey team, let's discuss the project requirements.",
    "sent_at": "2025-10-23T10:00:00Z",
    "mentions": []
  },
  {
    "id": 2,
    "room_slug": "project-alpha", 
    "sender": "bob",
    "body": "Sounds good! I've been reviewing the specs.",
    "sent_at": "2025-10-23T10:01:00Z",
    "mentions": []
  }
]
```

#### Send Direct Message
```http
POST /dms
Content-Type: application/json

{
  "sender": "alice",
  "recipient": "bob",
  "body": "Can we chat privately about the timeline?"
}
```

**Response:**
```json
{
  "id": 3,
  "sender": "alice",
  "recipient": "bob", 
  "body": "Can we chat privately about the timeline?",
  "sent_at": "2025-10-23T10:05:00Z",
  "room_slug": "dm:alice:bob"
}
```

**Notes:**
- The server automatically creates a DM room with slug `dm:{handle1}:{handle2}` (handles sorted alphabetically and normalized to lowercase).
- If the DM room already exists, the message is appended to that room.

#### Get User Direct Messages

```http
GET /users/{handle}/dms?since_id=0&since_timestamp=&before_timestamp=&limit=100
```

**Query Parameters:**
- `since_id` (optional): Only return messages with ID greater than this value.
- `since_timestamp` (optional): Only return messages sent after this ISO timestamp.
- `before_timestamp` (optional): Only return messages sent on or before this ISO timestamp (for replay/scrollback).
- `limit` (optional): Maximum number of messages to return (chronological order).

**Example:**
```http
GET /users/alice/dms?since_id=50&limit=100
```

**Response:**
```json
[
  {
    "id": 51,
    "room_slug": "dm:alice:bob",
    "sender": "bob",
    "body": "Can we review the auth flow later today?",
    "sent_at": "2025-10-23T10:07:00Z"
  }
]
```

### User Management

#### Create or Update User
```http
PUT /users/{handle}
Content-Type: application/json

{
  "display_name": "Alice Johnson"
}
```

**Description:**
- Creates a user if it does not exist, or updates the `display_name` if the user already exists.
- User handles are normalised to lowercase and trimmed.

**Response:**
```json
{
  "handle": "alice",
  "display_name": "Alice Johnson"
}
```

## Simulation Manager Integration

The Chat Server integrates with the Simulation Manager (port 8015) to provide monitoring and aggregated data access.

### Monitor Chat Messages
```http
GET /api/v1/monitor/chat/messages/{person_id}?scope=all&limit=100
```

**Parameters:**
- `person_id`: Simulation persona ID
- `scope`: `all`, `rooms`, `dms`
- `limit`: Maximum number of messages (default: 100)

**Response:**
```json
{
  "rooms": [
    {
      "id": 1,
      "room_slug": "project-alpha",
      "sender": "alice",
      "body": "Message content",
      "sent_at": "2025-10-23T10:00:00Z"
    }
  ],
  "dms": [
    {
      "id": 2,
      "sender": "alice",
      "recipient": "bob",
      "body": "DM content", 
      "sent_at": "2025-10-23T10:01:00Z",
      "room_slug": "dm:alice:bob"
    }
  ]
}
```

### Monitor Room Messages
```http
GET /api/v1/monitor/chat/room/{room_slug}/messages?limit=100
```

**Response:**
```json
[
  {
    "id": 1,
    "room_slug": "project-alpha",
    "sender": "alice", 
    "body": "Message content",
    "sent_at": "2025-10-23T10:00:00Z",
    "tick": 1450
  }
]
```

## Data Models

### Room Model
```typescript
interface Room {
  slug: string;           // Unique room identifier
  name: string;           // Display name
  participants: string[]; // Array of user handles
  is_dm: boolean;         // True for direct message rooms
  created_at: string;     // ISO timestamp
}
```

### Message Model
```typescript
interface Message {
  id: number;             // Unique message ID
  room_slug?: string;     // Room identifier (for room messages)
  sender: string;         // Sender's handle
  recipient?: string;     // Recipient's handle (for DMs)
  body: string;           // Message content
  sent_at: string;        // ISO timestamp
  mentions?: string[];    // Mentioned user handles
  tick?: number;          // Simulation tick (when available)
}
```

### User Model
```typescript
interface User {
  handle: string;         // Unique user handle
  display_name?: string;  // Optional display name
  created_at: string;     // ISO timestamp
  last_seen?: string;     // Last activity timestamp
}
```

## Error Responses

### Standard Error Format
```json
{
  "detail": "Error description",
  "error_code": "ERROR_CODE",
  "timestamp": "2025-10-23T10:00:00Z"
}
```

### Common Error Codes

#### 400 Bad Request
```json
{
  "detail": "Invalid request format",
  "error_code": "INVALID_REQUEST"
}
```

#### 404 Not Found
```json
{
  "detail": "Room not found",
  "error_code": "ROOM_NOT_FOUND"
}
```

#### 422 Validation Error
```json
{
  "detail": [
    {
      "loc": ["body", "sender"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

## Usage Examples

### Basic Chat Flow
```python
import httpx

# Create a room
room_data = {
    "name": "project-alpha",
    "participants": ["alice", "bob"],
    "slug": "project-alpha"
}
response = httpx.post("http://127.0.0.1:8001/rooms", json=room_data)
room = response.json()

# Send a message
message_data = {
    "sender": "alice",
    "body": "Hello team!"
}
response = httpx.post(
    f"http://127.0.0.1:8001/rooms/{room['slug']}/messages",
    json=message_data
)
message = response.json()

# Get messages
response = httpx.get(f"http://127.0.0.1:8001/rooms/{room['slug']}/messages")
messages = response.json()
```

### Direct Message Flow
```python
# Send a direct message
dm_data = {
    "sender": "alice",
    "recipient": "bob", 
    "body": "Private message"
}
response = httpx.post("http://127.0.0.1:8001/dms", json=dm_data)
dm = response.json()

# Get user's rooms (includes DM rooms)
response = httpx.get("http://127.0.0.1:8001/users/alice/rooms")
rooms = response.json()
```

### Monitoring via Simulation Manager
```python
# Get all chat messages for a persona
response = httpx.get(
    "http://127.0.0.1:8015/api/v1/monitor/chat/messages/1?scope=all&limit=100"
)
chat_data = response.json()

# Get specific room messages
response = httpx.get(
    "http://127.0.0.1:8015/api/v1/monitor/chat/room/project-alpha/messages"
)
room_messages = response.json()
```

## Integration with Dashboard

The chat client interface in the web dashboard uses these APIs to provide:

- **Conversation List**: Fetches rooms and DMs via `/users/{handle}/rooms` and monitoring endpoints
- **Message Display**: Loads messages via room-specific endpoints
- **Real-time Updates**: Polls monitoring endpoints every 3 seconds during simulation
- **Search**: Client-side filtering of conversations and messages

### Dashboard API Usage
```javascript
// Fetch user conversations
const rooms = await fetch(`http://127.0.0.1:8001/users/${handle}/rooms`);
const messages = await fetch(`http://127.0.0.1:8015/api/v1/monitor/chat/messages/${personId}?scope=all`);

// Load specific conversation
const roomMessages = await fetch(`http://127.0.0.1:8015/api/v1/monitor/chat/room/${slug}/messages`);
```

## Performance Considerations

### Message Limits
- Default limit: 100 messages per request
- Maximum limit: 500 messages per request
- Use pagination for large conversations

### Caching
- Room metadata is cached by the dashboard
- Message lists are cached with 15-30 second TTL
- Auto-refresh during simulation reduces cache duration

### Rate Limiting
Currently no rate limiting is implemented, but consider:
- 100 requests per minute per client
- Burst allowance of 20 requests
- WebSocket upgrade for real-time features

## Future Enhancements

### Planned Features
- **WebSocket Support**: Real-time message delivery
- **Message Threading**: Reply-to-message functionality  
- **File Attachments**: Image and document sharing
- **Message Reactions**: Emoji reactions to messages
- **Read Receipts**: Track message read status
- **Message Search**: Server-side message content search
- **User Presence**: Online/offline status tracking

### API Versioning
Future API versions will be available at:
- `/v2/rooms` - Enhanced room management
- `/v2/messages` - Threading and reactions support
- `/v2/users` - Presence and status features

## Troubleshooting

### Common Issues

#### Room Creation Fails
- Ensure all participants exist as users
- Check that room slug is unique
- Verify JSON format is correct

#### Messages Not Appearing
- Check that sender exists in room participants
- Verify room slug is correct
- Ensure message body is not empty

#### DM Room Not Found
- DM rooms are auto-created on first message
- Room slug format: `dm:sender:recipient` (alphabetical order)
- Both users must exist in the system

### Debug Endpoints

The current Chat Server implementation does not expose additional debug-specific endpoints beyond the core APIs above. For troubleshooting, use:
- Standard chat endpoints to inspect stored data (rooms, messages, DMs)
- Simulation Manager monitoring endpoints under `/api/v1/monitor/chat/...`
- Application logs from the Chat Server process

## Related Documentation

- [Simulation Manager API](sim-manager-api.md) - Integration endpoints
- [Architecture Overview](../architecture.md) - System design
- [Chat Client Interface](../modules/chat-client.md) - Dashboard integration
- [Virtual Workers](../modules/virtual-workers.md) - How personas use chat
