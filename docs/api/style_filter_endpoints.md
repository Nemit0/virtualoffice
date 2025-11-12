# Style Filter API Endpoints

## Overview

The Style Filter API provides endpoints for managing the communication style filter feature, which transforms generated messages to match each persona's unique writing style using GPT-4o.

**Base URL**: `/api/v1`

## Configuration

### Environment Variables

The style filter can be configured using the following environment variable:

**VDOS_STYLE_FILTER_ENABLED**
- **Purpose**: Sets the default state of the style filter when initializing a new database
- **Default**: `true`
- **Valid Values**: `true`, `false`, `1`, `0`, `yes`, `no`, `on`, `off`
- **Example**: `VDOS_STYLE_FILTER_ENABLED=true`

**Important Notes**:
- This variable only affects the initial database setup
- After initialization, use the API endpoints or dashboard UI to control filter state
- Changing this variable after database creation has no effect

### Filter Control Hierarchy

The style filter operates with two levels of control:

1. **Global Toggle** (via `style_filter_config` table)
   - Controls filter for entire simulation
   - Managed via API: `POST /api/v1/style-filter/config`
   - When disabled, no messages are filtered

2. **Per-Persona Toggle** (via `people.style_filter_enabled` column)
   - Controls filter for individual personas
   - Default: enabled for all personas
   - Only applies when global filter is enabled

**Filter Application Logic**:
```
Message is filtered IF:
  Global filter enabled (style_filter_config.enabled = 1)
  AND Per-persona filter enabled (people.style_filter_enabled = 1)
  AND Persona has valid style examples
```

## Endpoints

### Configuration Management

#### Get Filter Configuration

Retrieves the current global style filter configuration.

**Endpoint**: `GET /style-filter/config`

**Response**:
```json
{
  "enabled": true,
  "updated_at": "2025-10-30T10:30:00Z"
}
```

**Status Codes**:
- `200 OK`: Configuration retrieved successfully
- `500 Internal Server Error`: Database error

**Example**:
```bash
curl http://localhost:8015/api/v1/style-filter/config
```

---

#### Update Filter Configuration

Updates the global style filter configuration. When disabled, no messages will be transformed regardless of per-persona settings.

**Endpoint**: `POST /style-filter/config`

**Request Body**:
```json
{
  "enabled": true
}
```

**Response**:
```json
{
  "enabled": true,
  "updated_at": "2025-10-30T10:30:00Z",
  "message": "Style filter enabled"
}
```

**Status Codes**:
- `200 OK`: Configuration updated successfully
- `500 Internal Server Error`: Database error

**Example**:
```bash
curl -X POST http://localhost:8015/api/v1/style-filter/config \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

**Configuration Behavior**:
- The global filter toggle affects all personas immediately
- When disabled globally, no messages are filtered even if per-persona filter is enabled
- When enabled globally, messages are filtered only for personas with `style_filter_enabled=1`
- Initial default value is controlled by `VDOS_STYLE_FILTER_ENABLED` environment variable
- Runtime changes persist in the database and survive service restarts

---

### Metrics and Monitoring

#### Get Filter Metrics

Retrieves aggregated metrics for all style filter transformations in the current session.

**Endpoint**: `GET /style-filter/metrics`

**Response**:
```json
{
  "total_transformations": 156,
  "successful_transformations": 154,
  "total_tokens": 45230,
  "average_latency_ms": 342.5,
  "estimated_cost_usd": 0.2827,
  "by_message_type": {
    "email": 98,
    "chat": 58
  }
}
```

**Response Fields**:
- `total_transformations`: Total number of transformation attempts
- `successful_transformations`: Number of successful transformations
- `total_tokens`: Total GPT-4o tokens consumed
- `average_latency_ms`: Average transformation time in milliseconds
- `estimated_cost_usd`: Estimated API cost (GPT-4o pricing: $6.25 per 1M tokens average)
- `by_message_type`: Breakdown of transformations by type (email/chat)

**Status Codes**:
- `200 OK`: Metrics retrieved successfully (returns empty metrics if no transformations)

**Example**:
```bash
curl http://localhost:8015/api/v1/style-filter/metrics
```

**Notes**:
- Returns empty metrics structure if `style_filter_metrics` table doesn't exist
- Metrics are session-wide and persist across simulation runs
- Cost estimation uses GPT-4o pricing: $2.50 per 1M input tokens, $10 per 1M output tokens (averaged to $6.25)

---

### Style Example Management

#### Regenerate Style Examples

Regenerates style examples for an existing persona using GPT-4o. The new examples replace the existing ones in the database.

**Endpoint**: `POST /people/{person_id}/regenerate-style-examples`

**Path Parameters**:
- `person_id` (integer): ID of the persona

**Response**:
```json
{
  "style_examples": "[{\"type\":\"email\",\"content\":\"안녕하세요, 프로젝트 진행 상황을 공유드립니다...\"},{\"type\":\"chat\",\"content\":\"네, 확인했습니다!\"}]",
  "message": "Successfully regenerated style examples for person 1"
}
```

**Status Codes**:
- `200 OK`: Examples regenerated successfully
- `404 Not Found`: Person not found
- `400 Bad Request`: Generation failed (validation error)
- `500 Internal Server Error`: Unexpected error

**Example**:
```bash
curl -X POST http://localhost:8015/api/v1/people/1/regenerate-style-examples
```

**Notes**:
- Requires valid OpenAI API key
- Uses GPT-4o model for generation
- Generates 10 examples (5 email, 5 chat) by default
- Examples are validated before saving (minimum 50 characters each)
- Locale-aware generation based on `VDOS_LOCALE` environment variable

---

#### Generate Style Examples from Attributes

Generates style examples for a persona based on provided attributes without requiring an existing person_id. Used during persona creation.

**Endpoint**: `POST /personas/generate-style-examples`

**Request Body**:
```json
{
  "name": "김철수",
  "role": "시니어 개발자",
  "personality": "꼼꼼함, 협력적",
  "communication_style": "명확하고 간결한 커뮤니케이션"
}
```

**Response**:
```json
{
  "style_examples": [
    {
      "type": "email",
      "content": "안녕하세요, 프로젝트 진행 상황을 공유드립니다. 현재 개발이 순조롭게 진행되고 있습니다."
    },
    {
      "type": "chat",
      "content": "네, 확인했습니다! 바로 처리하겠습니다."
    }
  ],
  "message": "Successfully generated style examples"
}
```

**Status Codes**:
- `200 OK`: Examples generated successfully
- `500 Internal Server Error`: Generation failed

**Example**:
```bash
curl -X POST http://localhost:8015/api/v1/personas/generate-style-examples \
  -H "Content-Type: application/json" \
  -d '{
    "name": "김철수",
    "role": "시니어 개발자",
    "personality": "꼼꼼함, 협력적",
    "communication_style": "명확하고 간결한 커뮤니케이션"
  }'
```

**Notes**:
- Does not require existing persona in database
- Returns examples as array of objects (not JSON string)
- Useful for preview during persona creation
- Personality can be comma-separated string or array

---

#### Preview Filter Transformation

Previews how the style filter would transform a message using provided style examples. Useful for testing and validating style examples before saving.

**Endpoint**: `POST /personas/preview-filter`

**Request Body**:
```json
{
  "message": "Please review the attached document and provide feedback.",
  "style_examples": [
    {
      "type": "email",
      "content": "안녕하세요, 검토 부탁드립니다. 첨부 파일 확인 후 피드백 주시면 감사하겠습니다."
    },
    {
      "type": "email",
      "content": "팀원 여러분께, 오늘 회의에서 논의된 내용을 정리해서 보내드립니다."
    }
  ],
  "message_type": "email"
}
```

**Request Fields**:
- `message` (string, required): The message to transform
- `style_examples` (array, required): Array of style example objects with `type` and `content`
- `message_type` (string, required): Type of message ("email" or "chat")

**Response**:
```json
{
  "original_message": "Please review the attached document and provide feedback.",
  "filtered_message": "안녕하세요, 첨부된 문서를 검토하시고 피드백 주시면 감사하겠습니다.",
  "tokens_used": 120,
  "message": "Filter preview successful"
}
```

**Status Codes**:
- `200 OK`: Preview successful
- `400 Bad Request`: Invalid request (missing fields, invalid examples)
- `500 Internal Server Error`: Transformation failed

**Example**:
```bash
curl -X POST http://localhost:8015/api/v1/personas/preview-filter \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Please review the attached document.",
    "style_examples": [
      {"type": "email", "content": "안녕하세요, 검토 부탁드립니다..."}
    ],
    "message_type": "email"
  }'
```

**Notes**:
- Requires at least one valid style example
- Uses GPT-4o for transformation
- Randomly samples 3 examples if more than 3 provided
- Locale-aware based on `VDOS_LOCALE` environment variable
- Does not save results to database

---

## Error Handling

All endpoints follow consistent error response format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

Common error scenarios:
- **500 Internal Server Error**: Database connection issues, GPT API failures
- **404 Not Found**: Persona not found (regenerate endpoint)
- **400 Bad Request**: Invalid request body, validation failures

## Authentication

Currently, no authentication is required for these endpoints. In production deployments, consider adding:
- API key authentication
- Rate limiting
- IP whitelisting

## Rate Limiting

No rate limiting is currently enforced. Consider implementing rate limits for:
- Style example generation (GPT API calls)
- Filter preview (GPT API calls)
- Metrics queries (database load)

## Performance Considerations

### Token Usage
- Example generation: ~500-800 tokens per request
- Filter preview: ~100-200 tokens per request
- Regenerate examples: ~500-800 tokens per request

### Latency
- Configuration endpoints: < 50ms (database only)
- Metrics endpoint: < 100ms (database aggregation)
- Generation endpoints: 2-4 seconds (GPT API call)
- Preview endpoint: 300-500ms (GPT API call)

### Cost Estimation
- GPT-4o pricing: $2.50 per 1M input tokens, $10 per 1M output tokens
- Average cost per generation: ~$0.004-0.006
- Average cost per preview: ~$0.0006-0.0012

## Integration Examples

### Python

```python
import requests

# Get filter configuration
response = requests.get("http://localhost:8015/api/v1/style-filter/config")
config = response.json()
print(f"Filter enabled: {config['enabled']}")

# Update filter configuration
response = requests.post(
    "http://localhost:8015/api/v1/style-filter/config",
    json={"enabled": False}
)
print(response.json()["message"])

# Get metrics
response = requests.get("http://localhost:8015/api/v1/style-filter/metrics")
metrics = response.json()
print(f"Total transformations: {metrics['total_transformations']}")
print(f"Estimated cost: ${metrics['estimated_cost_usd']:.4f}")

# Regenerate examples for persona
response = requests.post(
    "http://localhost:8015/api/v1/people/1/regenerate-style-examples"
)
result = response.json()
print(result["message"])
```

### JavaScript

```javascript
// Get filter configuration
const config = await fetch('http://localhost:8015/api/v1/style-filter/config')
  .then(res => res.json());
console.log(`Filter enabled: ${config.enabled}`);

// Update filter configuration
const updateResult = await fetch('http://localhost:8015/api/v1/style-filter/config', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ enabled: true })
}).then(res => res.json());
console.log(updateResult.message);

// Get metrics
const metrics = await fetch('http://localhost:8015/api/v1/style-filter/metrics')
  .then(res => res.json());
console.log(`Total transformations: ${metrics.total_transformations}`);
console.log(`Estimated cost: $${metrics.estimated_cost_usd.toFixed(4)}`);

// Preview filter
const preview = await fetch('http://localhost:8015/api/v1/personas/preview-filter', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    message: 'Please review this.',
    style_examples: [
      { type: 'email', content: '검토 부탁드립니다...' }
    ],
    message_type: 'email'
  })
}).then(res => res.json());
console.log(`Filtered: ${preview.filtered_message}`);
```

## See Also

- [Communication Style Filter Module Documentation](../modules/communication_style_filter.md)
- [Style Filter Design Document](../../.kiro/specs/persona-communication-style-filter/design.md)
- [Simulation Manager API Documentation](./simulation_manager.md)
