# Communication Style Filter Configuration Guide

## Overview

The Communication Style Filter is a GPT-4o powered feature that transforms all generated messages to match each persona's unique writing style. This guide covers configuration, usage, and best practices.

## Quick Start

### Enable/Disable Filter

**Via Environment Variable** (initial setup only):
```bash
# In .env file
VDOS_STYLE_FILTER_ENABLED=true  # Enable by default
VDOS_STYLE_FILTER_ENABLED=false # Disable by default
```

**Note**: This environment variable is read only during database initialization in `simulation_state.py`. The value is parsed and stored in the `style_filter_config` table. Changing the environment variable after database initialization has no effect.

**Via Dashboard UI** (runtime control):
1. Open the simulation dashboard
2. Locate the "Communication Style Filter" checkbox in the control panel
3. Check to enable, uncheck to disable
4. Changes apply immediately to new messages

**Via API** (programmatic control):
```bash
# Enable filter
curl -X POST http://localhost:8015/api/v1/style-filter/config \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# Disable filter
curl -X POST http://localhost:8015/api/v1/style-filter/config \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

## Configuration Hierarchy

The style filter operates with two levels of control:

### 1. Global Toggle

Controls whether the filter is active for the entire simulation.

**Storage**: `style_filter_config` table (singleton row)

**Default**: Controlled by `VDOS_STYLE_FILTER_ENABLED` environment variable

**Control Methods**:
- Dashboard UI checkbox
- API: `POST /api/v1/style-filter/config`

**Behavior**:
- When disabled globally, NO messages are filtered
- When enabled globally, messages are filtered based on per-persona settings

### 2. Per-Persona Toggle

Controls whether the filter is active for a specific persona.

**Storage**: `people.style_filter_enabled` column

**Default**: `1` (enabled) for all personas

**Control Methods**:
- Persona dialog in dashboard UI
- API: Update persona with `style_filter_enabled` field

**Behavior**:
- Only applies when global filter is enabled
- Allows selective filtering for specific personas

## Filter Application Logic

A message is filtered if and only if:

```
✓ Global filter is enabled (style_filter_config.enabled = 1)
AND
✓ Per-persona filter is enabled (people.style_filter_enabled = 1)
AND
✓ Persona has valid style examples (people.style_examples != '[]')
```

**Example Scenarios**:

| Global | Per-Persona | Has Examples | Result |
|--------|-------------|--------------|--------|
| ✓ | ✓ | ✓ | **Filtered** |
| ✓ | ✓ | ✗ | Not filtered (no examples) |
| ✓ | ✗ | ✓ | Not filtered (persona disabled) |
| ✗ | ✓ | ✓ | Not filtered (global disabled) |
| ✗ | ✗ | ✗ | Not filtered |

## Style Examples Configuration

### Format

Style examples are stored as JSON arrays in the `people.style_examples` column:

```json
[
  {
    "type": "email",
    "content": "Example email message..."
  },
  {
    "type": "chat",
    "content": "Example chat message..."
  }
]
```

### Requirements

- **Minimum**: 3 examples (recommended)
- **Maximum**: 5 examples
- **Types**: Mix of "email" and "chat"
- **Length**: Minimum 20 characters per example
- **Content**: Should demonstrate:
  - Typical vocabulary and phrasing
  - Formality level
  - Sentence structure
  - Greeting/closing styles
  - Personality traits

### Generation Methods

#### 1. Automatic Generation (Recommended)

When creating a persona, style examples are automatically generated using GPT-4o based on:
- Role (e.g., "Senior Developer", "Project Manager")
- Personality traits (e.g., "friendly", "detail-oriented")
- Communication style (e.g., "concise", "formal")

**Via Dashboard**:
1. Create or edit persona
2. Fill in role, personality, and communication style
3. Click "Save" - examples are generated automatically
4. Review and edit if needed

**Via API**:
```bash
# Generate examples for persona attributes
curl -X POST http://localhost:8015/api/v1/personas/generate-style-examples \
  -H "Content-Type: application/json" \
  -d '{
    "role": "Senior Developer",
    "personality": "friendly, detail-oriented",
    "communication_style": "concise, technical",
    "locale": "en"
  }'
```

#### 2. Regeneration

Regenerate examples for an existing persona:

**Via Dashboard**:
1. Open persona dialog
2. Click "Regenerate with AI" button
3. New examples are generated and populated
4. Review and save

**Via API**:
```bash
curl -X POST http://localhost:8015/api/v1/people/123/regenerate-style-examples
```

#### 3. Manual Entry

Manually create or edit examples:

**Via Dashboard**:
1. Open persona dialog
2. Scroll to "Communication Style Examples" section
3. Enter or edit examples in text areas
4. Click "Save"

**Via API**:
```bash
curl -X PUT http://localhost:8015/api/v1/people/123 \
  -H "Content-Type: application/json" \
  -d '{
    "style_examples": "[{\"type\":\"email\",\"content\":\"...\"}]"
  }'
```

## Example Templates

### Formal Professional (English)

```json
[
  {
    "type": "email",
    "content": "Dear team, I wanted to provide an update on the project status. We have completed the initial phase and are proceeding according to schedule. Please let me know if you have any questions or concerns. Best regards,"
  },
  {
    "type": "chat",
    "content": "Good morning. I have reviewed the document and have a few suggestions. Would you be available for a brief discussion this afternoon?"
  },
  {
    "type": "email",
    "content": "Thank you for bringing this to my attention. I will investigate the issue and provide a detailed response by end of day."
  }
]
```

### Casual Friendly (English)

```json
[
  {
    "type": "email",
    "content": "Hey team! Quick update - we're making great progress on the project. Everything's on track and looking good. Let me know if you need anything!"
  },
  {
    "type": "chat",
    "content": "Hey! Just saw your message. Yeah, I can totally help with that. Give me like 10 mins?"
  },
  {
    "type": "email",
    "content": "Thanks for the heads up! I'll take a look and get back to you soon. Appreciate it!"
  }
]
```

### Formal Professional (Korean)

```json
[
  {
    "type": "email",
    "content": "안녕하세요 팀원 여러분, 프로젝트 진행 상황에 대해 간단히 공유드립니다. 현재 일정대로 잘 진행되고 있으며, 다음 주까지 1차 검토를 완료할 예정입니다. 궁금하신 점 있으시면 언제든 연락 주세요."
  },
  {
    "type": "chat",
    "content": "안녕하세요! 문서 검토 완료했습니다. 몇 가지 의견 있는데 오후에 잠깐 이야기 나눌 수 있을까요?"
  },
  {
    "type": "email",
    "content": "말씀해 주신 내용 확인했습니다. 자세히 검토해서 오늘 중으로 답변 드리겠습니다. 감사합니다."
  }
]
```

### Casual Friendly (Korean)

```json
[
  {
    "type": "email",
    "content": "안녕하세요! 프로젝트 진행 상황 공유드려요. 지금까지 순조롭게 진행되고 있고, 다음 주면 1차 완료될 것 같아요. 필요한 거 있으면 언제든 말씀해 주세요!"
  },
  {
    "type": "chat",
    "content": "방금 메시지 봤어요! 네, 도와드릴 수 있어요. 10분만 시간 주시면 될까요?"
  },
  {
    "type": "email",
    "content": "알려주셔서 감사해요! 확인해보고 곧 답변 드릴게요."
  }
]
```

## Testing and Validation

### Preview Filter

Test how the filter transforms messages before saving:

**Via Dashboard**:
1. Open persona dialog
2. Enter or generate style examples
3. Click "Preview Filter" button
4. Enter a sample message
5. View original vs filtered comparison

**Via API**:
```bash
curl -X POST http://localhost:8015/api/v1/personas/preview-filter \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I need to discuss the project timeline with you.",
    "style_examples": [...],
    "message_type": "email",
    "locale": "en"
  }'
```

### Validation Checklist

Before deploying personas with style examples:

- [ ] Each example is at least 20 characters
- [ ] Mix of email and chat examples
- [ ] Examples demonstrate consistent style
- [ ] Examples match persona's role and personality
- [ ] Examples are in correct locale (Korean/English)
- [ ] Preview filter produces expected results

## Performance and Cost

### Token Usage

- **Per transformation**: ~100-200 tokens
  - System prompt with examples: ~50-100 tokens
  - Original message: ~20-100 tokens
  - Response: ~20-100 tokens

### Cost Estimation

With GPT-4o pricing (~$0.015 per 1K tokens):
- 100 transformations ≈ $0.23
- 1,000 transformations ≈ $2.25
- 10,000 transformations ≈ $22.50

### Optimization Tips

1. **Selective Filtering**: Disable filter for personas where style consistency is less critical
2. **Monitor Metrics**: Use dashboard metrics to track token usage and costs
3. **Quality Examples**: Better examples = more consistent results = fewer regenerations
4. **Batch Operations**: Filter applies automatically during simulation - no manual intervention needed

## Monitoring

### Dashboard Metrics

The dashboard displays real-time filter metrics:

- **Transformations**: Total number of messages filtered
- **Tokens Used**: Total GPT-4o tokens consumed
- **Avg Latency**: Average transformation time
- **Estimated Cost**: Approximate API cost

### API Metrics

Query metrics programmatically:

```bash
curl http://localhost:8015/api/v1/style-filter/metrics
```

Response:
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

## Troubleshooting

### Filter Not Working

**Symptoms**: Messages are not being transformed

**Checklist**:
1. Check global filter is enabled: `GET /api/v1/style-filter/config`
2. Check persona filter is enabled: `people.style_filter_enabled = 1`
3. Verify persona has style examples: `people.style_examples != '[]'`
4. Check OpenAI API key is configured: `OPENAI_API_KEY` in `.env`
5. Review logs for API errors: `virtualoffice.log`

### Poor Quality Transformations

**Symptoms**: Filtered messages don't match expected style

**Solutions**:
1. **Improve Examples**: Add more specific, detailed examples
2. **Regenerate Examples**: Use "Regenerate with AI" for better examples
3. **Manual Editing**: Fine-tune examples to better represent desired style
4. **Preview Testing**: Use preview feature to validate before saving

### High Latency

**Symptoms**: Message generation is slow

**Solutions**:
1. **Check API Response Time**: Monitor GPT-4o API latency
2. **Reduce Example Count**: Use 3 examples instead of 5
3. **Selective Filtering**: Disable filter for less critical personas
4. **Network Issues**: Verify network connectivity to OpenAI API

### High Costs

**Symptoms**: Unexpected API costs

**Solutions**:
1. **Monitor Metrics**: Check dashboard for token usage
2. **Disable Filter**: Turn off globally if costs are concern
3. **Selective Filtering**: Enable only for key personas
4. **Optimize Examples**: Shorter examples = fewer tokens

## Best Practices

### 1. Start with AI Generation

Let GPT-4o generate initial examples based on persona attributes. This provides a good starting point that can be refined.

### 2. Review and Refine

Always review AI-generated examples and edit as needed to match your exact requirements.

### 3. Test Before Deployment

Use the preview feature to test how the filter transforms messages before running a full simulation.

### 4. Monitor Costs

Keep an eye on token usage and costs, especially for long-running simulations with many personas.

### 5. Selective Filtering

Not all personas need style filtering. Disable for personas where consistency is less critical.

### 6. Locale Consistency

Ensure style examples match the persona's locale setting (`VDOS_LOCALE`).

### 7. Regular Updates

Periodically review and update style examples as persona roles or communication needs evolve.

## Advanced Configuration

### Custom Prompt Templates

For advanced users, the filter prompt templates can be customized by modifying:
- `src/virtualoffice/sim_manager/style_filter/filter.py`
- Method: `_build_prompt_templates()`

### Database Direct Access

For bulk operations, you can directly modify the database:

```sql
-- Disable filter for all personas
UPDATE people SET style_filter_enabled = 0;

-- Enable filter for specific role
UPDATE people SET style_filter_enabled = 1 WHERE role = 'Project Manager';

-- Clear all style examples
UPDATE people SET style_examples = '[]';
```

**Warning**: Direct database modifications bypass validation. Use with caution.

## Related Documentation

- [Communication Style Filter Module](../modules/communication_style_filter.md)
- [Style Filter API Endpoints](../api/style_filter_endpoints.md)
- [API Configuration Standards](../../.kiro/steering/api-configuration.md)
- [Development Standards](../../.kiro/steering/development-standards.md)
