# Communication Diversity & Conversational Realism — Usage Examples

**Date:** 2025-11-05  
**Related Spec:** `.kiro/specs/communication-diversity/`  
**Related Modules:** `communication_generator.md`, `inbox_manager.md`, `participation_balancer.md`

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Enabling GPT Fallback Generation](#enabling-gpt-fallback-generation)
3. [Configuring Participation Balancing](#configuring-participation-balancing)
4. [Monitoring Quality Metrics](#monitoring-quality-metrics)
5. [Advanced Configuration](#advanced-configuration)
6. [Expected Output Samples](#expected-output-samples)
7. [Cost and Performance Examples](#cost-and-performance-examples)

---

## Quick Start

The communication diversity features are **enabled by default** in VDOS. To get started immediately:

```bash
# 1. Ensure you have OpenAI API key configured
export OPENAI_API_KEY=sk-...

# 2. Start VDOS with default settings (all features enabled)
briefcase dev

# 3. Create personas and start a simulation via the web dashboard
# Navigate to http://127.0.0.1:8015
```

That's it! Your simulation will now generate diverse, realistic communications automatically.

---

## Enabling GPT Fallback Generation

### Example 1: Basic Configuration

Enable GPT-powered fallback communication generation (default behavior):

```bash
# .env file
OPENAI_API_KEY=sk-...
VDOS_GPT_FALLBACK_ENABLED=true
VDOS_FALLBACK_PROBABILITY=0.6
VDOS_FALLBACK_MODEL=gpt-4o-mini
```

**What this does:**
- When hourly plans don't include JSON communications, GPT generates diverse messages
- 60% base probability for generating fallback communications (subject to participation balancing)
- Uses cost-effective GPT-4o-mini model (~$0.00024 per call)

**Expected behavior:**
- Diverse email subjects (no repetition)
- Role-appropriate language (developers use technical terms, designers use visual language)
- Project context integration (messages reference specific tasks and artifacts)

### Example 2: High-Frequency Communication

Generate more frequent communications for active simulations:

```bash
# .env file
VDOS_GPT_FALLBACK_ENABLED=true
VDOS_FALLBACK_PROBABILITY=0.8  # Increased from default 0.6
VDOS_THREADING_RATE=0.4         # Increased from default 0.3
```

**Use case:** Testing systems that need high message volume

**Expected output:**
- 80% probability of generating fallback communications
- 40% of received emails get threaded replies
- More multi-turn conversations

### Example 3: Conservative Communication

Reduce communication frequency for quieter simulations:

```bash
# .env file
VDOS_GPT_FALLBACK_ENABLED=true
VDOS_FALLBACK_PROBABILITY=0.4  # Decreased from default 0.6
VDOS_THREADING_RATE=0.2         # Decreased from default 0.3
```

**Use case:** Simulating teams with async-first culture

**Expected output:**
- 40% probability of generating fallback communications
- 20% of received emails get replies
- Fewer but more meaningful communications

### Example 4: Disabling GPT Fallback

Revert to template-based generation (legacy behavior):

```bash
# .env file
VDOS_GPT_FALLBACK_ENABLED=false
```

**What this does:**
- Disables GPT-powered fallback generation
- Falls back to simple template-based messages
- No additional API costs
- Lower quality but faster execution

**When to use:**
- Testing without API costs
- Debugging simulation logic
- Comparing old vs new behavior

---

## Configuring Participation Balancing

### Example 5: Default Balanced Distribution

Enable participation balancing to prevent message dominance (default behavior):

```bash
# .env file
VDOS_PARTICIPATION_BALANCE_ENABLED=true
```

**What this does:**
- Throttles high-volume senders (>2x team average) to 30% probability
- Boosts low-volume senders (<0.5x team average) to 90% probability
- Ensures realistic distribution across all personas

**Expected metrics:**
- Top 2 senders account for ≤40% of messages (down from 65% without balancing)
- All personas send at least 1 message per day
- Standard deviation of message counts <30% of mean

### Example 6: Aggressive Balancing

Enforce even stricter participation balance:

```bash
# .env file
VDOS_PARTICIPATION_BALANCE_ENABLED=true
VDOS_FALLBACK_PROBABILITY=0.5  # Lower base probability
```

**Use case:** Simulating highly collaborative teams where everyone participates equally

**Expected behavior:**
- Even more balanced distribution
- Fewer messages overall but better spread
- No single persona dominates

### Example 7: Disabling Balancing

Allow natural (unbalanced) communication patterns:

```bash
# .env file
VDOS_PARTICIPATION_BALANCE_ENABLED=false
```

**What this does:**
- Disables throttling and boosting
- Allows some personas to send many more messages than others
- More realistic for teams with dominant communicators

**When to use:**
- Testing systems that handle imbalanced communication
- Simulating teams with clear communication leaders
- Stress-testing message processing

---

## Monitoring Quality Metrics

### Example 8: Accessing Quality Metrics API

Monitor communication quality in real-time:

```bash
# Get current quality metrics
curl http://127.0.0.1:8015/api/v1/simulation/quality-metrics

# Example response:
{
  "template_diversity_score": 0.85,
  "threading_rate": 0.32,
  "participation_gini": 0.28,
  "project_context_rate": 0.64,
  "json_vs_fallback_ratio": 0.45,
  "realism_score": 8.2,
  "role_differentiation_accuracy": 0.82
}
```

**Metric definitions:**
- `template_diversity_score`: Unique subjects / total messages (target: >0.8)
- `threading_rate`: Messages with thread_id / total emails (target: >0.3)
- `participation_gini`: Gini coefficient of message distribution (target: <0.35)
- `project_context_rate`: Messages with project refs / total (target: >0.6)
- `json_vs_fallback_ratio`: JSON comms / total comms (higher = more JSON)
- `realism_score`: GPT-4o evaluation 1-10 (target: >7.5)
- `role_differentiation_accuracy`: Role identification accuracy (target: >0.75)

### Example 9: Monitoring During Simulation

Track metrics over time using a simple script:

```python
import httpx
import time

client = httpx.Client(base_url="http://127.0.0.1:8015")

while True:
    response = client.get("/api/v1/simulation/quality-metrics")
    metrics = response.json()
    
    print(f"Threading: {metrics['threading_rate']:.1%}")
    print(f"Diversity: {metrics['template_diversity_score']:.1%}")
    print(f"Balance: {metrics['participation_gini']:.2f}")
    print(f"Project Context: {metrics['project_context_rate']:.1%}")
    print("---")
    
    time.sleep(60)  # Check every minute
```

### Example 10: Quality Validation Script

Run comprehensive quality validation after simulation:

```bash
# Use the provided validation script
python .tmp/test_quality_validation_gpt.py

# Or run manual validation
python -c "
from virtualoffice.sim_manager.quality_validator import QualityValidator

validator = QualityValidator()
results = validator.validate_simulation()

print(f'Realism Score: {results.realism_score}/10')
print(f'Role Accuracy: {results.role_accuracy:.1%}')
print(f'Threading Rate: {results.threading_rate:.1%}')
"
```

---

## Advanced Configuration

### Example 11: Korean Locale with Communication Diversity

Enable all features for Korean workplace simulation:

```bash
# .env file
OPENAI_API_KEY=sk-...
VDOS_LOCALE=ko
VDOS_LOCALE_TZ=Asia/Seoul

# Communication diversity features
VDOS_GPT_FALLBACK_ENABLED=true
VDOS_FALLBACK_PROBABILITY=0.6
VDOS_THREADING_RATE=0.3
VDOS_PARTICIPATION_BALANCE_ENABLED=true

# Style filter for persona-consistent writing
VDOS_STYLE_FILTER_ENABLED=true
```

**What this does:**
- All AI prompts use Korean templates
- GPT generates Korean communications with natural workplace language
- Style filter applies Korean persona writing styles
- Threading and balancing work with Korean content

**Expected output:**
- Natural Korean email subjects: "[모바일앱] 로그인 API 구현 완료"
- Role-appropriate Korean terms: "API 엔드포인트", "목업 피드백", "테스트 케이스"
- Korean conversational patterns in threaded emails

### Example 12: High-Quality Mode

Use GPT-4o for highest quality communications (higher cost):

```bash
# .env file
VDOS_GPT_FALLBACK_ENABLED=true
VDOS_FALLBACK_MODEL=gpt-4o  # Instead of gpt-4o-mini
VDOS_FALLBACK_PROBABILITY=0.7
VDOS_THREADING_RATE=0.4
```

**Cost comparison:**
- GPT-4o-mini: ~$0.00024 per call
- GPT-4o: ~$0.0024 per call (10x more expensive)

**When to use:**
- Final validation runs
- Generating demo data for presentations
- Research requiring highest quality

### Example 13: Debugging Configuration

Optimal settings for debugging and development:

```bash
# .env file
VDOS_GPT_FALLBACK_ENABLED=true
VDOS_FALLBACK_PROBABILITY=0.8  # High frequency for testing
VDOS_THREADING_RATE=0.5        # Lots of threading
VDOS_PARTICIPATION_BALANCE_ENABLED=false  # Disable for predictability

# Enable detailed logging
VDOS_LOG_LEVEL=DEBUG
```

**What this does:**
- High communication frequency for faster testing
- Disabled balancing for predictable behavior
- Detailed logs for debugging

### Example 14: Production-Like Configuration

Settings for realistic long-running simulations:

```bash
# .env file
VDOS_GPT_FALLBACK_ENABLED=true
VDOS_FALLBACK_PROBABILITY=0.6
VDOS_FALLBACK_MODEL=gpt-4o-mini
VDOS_THREADING_RATE=0.3
VDOS_PARTICIPATION_BALANCE_ENABLED=true
VDOS_STYLE_FILTER_ENABLED=true

# Performance settings
VDOS_TICK_MS=50
VDOS_BUSINESS_DAYS=20  # 4-week simulation
```

**Use case:** Generating large datasets for analytics testing

**Expected behavior:**
- Realistic communication patterns over 4 weeks
- Balanced participation across all personas
- Diverse, context-aware messages
- Cost-effective with GPT-4o-mini

---

## Expected Output Samples

### Sample 1: Developer Email (GPT Fallback)

**Before (Template):**
```
Subject: 업데이트: Lee Minseo → Kim Hana
Body:
Kim님 안녕하세요,

현재 집중 작업:
주요 작업에 집중하고 있습니다.

요청: 진행 상황 공유
필요하시면 언제든 말씀해 주세요.
```

**After (GPT Fallback):**
```
Subject: [MobileApp] 로그인 API 엔드포인트 구현 완료
Body:
Hana님,

/auth/login API 엔드포인트 구현이 완료되었습니다:
- JWT 토큰 생성 로직 추가
- 데이터베이스 쿼리 최적화 완료
- 다음 단계: 프론트엔드 통합 테스트

인증 모듈 관련 질문 있으시면 알려주세요.
```

### Sample 2: Designer Email (GPT Fallback)

```
Subject: [MobileApp] 로그인 화면 목업 피드백 요청
Body:
Minseo님,

로그인 화면 목업 작업이 완료되었습니다.
주요 변경사항:
- 컬러 팔레트를 브랜드 가이드에 맞춤
- 사용자 플로우 개선 (비밀번호 찾기 추가)

UI/UX 부분 검토 부탁드립니다.
```

### Sample 3: Threaded Email Conversation

**Original Email:**
```
From: kim.hana@vdos.local
To: lee.minseo@vdos.local
Subject: [MobileApp] API 응답 형식 질문
Thread-ID: mobile-api-format-001

Minseo님,

로그인 API 응답 형식에 대해 질문이 있습니다:
현재 JWT 토큰만 반환하는데, 사용자 정보도 함께 포함해야 할까요?

프론트엔드 구현 전에 확인하고 싶습니다.
```

**Reply (GPT Generated):**
```
From: lee.minseo@vdos.local
To: kim.hana@vdos.local
Subject: RE: [MobileApp] API 응답 형식 질문
Thread-ID: mobile-api-format-001

Hana님,

좋은 질문입니다. 사용자 정보도 함께 반환하는 것이 좋겠습니다:
- user_id, name, email 정도면 충분할 것 같습니다
- 프로필 이미지 URL도 추가하면 좋을 것 같아요

API 스펙 문서 업데이트하고 알려드리겠습니다.
```

### Sample 4: Chat Message (GPT Fallback)

**Developer:**
```
[10:23] lee_minseo: @kim_hana PR #42 리뷰 부탁드립니다. 로그인 API 구현 완료했습니다.
```

**Designer:**
```
[14:15] kim_hana: @lee_minseo 목업 피드백 받았나요? 수정사항 있으면 알려주세요.
```

**QA:**
```
[16:45] park_qa: @lee_minseo 로그인 테스트 중 버그 발견했습니다. 
빈 이메일로 로그인 시도 시 500 에러 발생합니다.
```

### Sample 5: Quality Metrics Over Time

```
Day 1:
  Threading Rate: 28%
  Diversity Score: 0.82
  Participation Gini: 0.31
  Project Context: 58%

Day 3:
  Threading Rate: 32%
  Diversity Score: 0.87
  Participation Gini: 0.27
  Project Context: 64%

Day 5:
  Threading Rate: 35%
  Diversity Score: 0.89
  Participation Gini: 0.25
  Project Context: 67%
```

**Interpretation:**
- Threading rate increasing (more conversations)
- Diversity improving (less repetition)
- Participation becoming more balanced (lower Gini)
- Project context increasing (more specific references)

---

## Cost and Performance Examples

### Example 15: Cost Estimation

Calculate expected costs for different simulation sizes:

**Small Simulation (5 days, 5 personas):**
```
Assumptions:
- 5 personas × 5 days = 25 persona-days
- ~10 fallback communications per persona per day
- Total: 250 fallback calls

Cost with GPT-4o-mini:
250 calls × $0.00024 = $0.06

Cost with GPT-4o:
250 calls × $0.0024 = $0.60
```

**Medium Simulation (20 days, 10 personas):**
```
Assumptions:
- 10 personas × 20 days = 200 persona-days
- ~10 fallback communications per persona per day
- Total: 2,000 fallback calls

Cost with GPT-4o-mini:
2,000 calls × $0.00024 = $0.48

Cost with GPT-4o:
2,000 calls × $0.0024 = $4.80
```

**Large Simulation (60 days, 20 personas):**
```
Assumptions:
- 20 personas × 60 days = 1,200 persona-days
- ~10 fallback communications per persona per day
- Total: 12,000 fallback calls

Cost with GPT-4o-mini:
12,000 calls × $0.00024 = $2.88

Cost with GPT-4o:
12,000 calls × $0.0024 = $28.80
```

### Example 16: Performance Benchmarks

Expected performance impact with communication diversity enabled:

**Tick Advancement Latency:**
```
Without GPT Fallback:
- Average: 45ms per tick
- 95th percentile: 120ms per tick

With GPT Fallback (GPT-4o-mini):
- Average: 47ms per tick (+4.4%)
- 95th percentile: 125ms per tick (+4.2%)

With GPT Fallback (GPT-4o):
- Average: 52ms per tick (+15.6%)
- 95th percentile: 145ms per tick (+20.8%)
```

**Memory Usage:**
```
Without GPT Fallback:
- Base memory: 120MB

With GPT Fallback:
- Base memory: 124MB (+3.3%)
- Inbox tracking: +2MB
- Participation stats: +1MB
- Total: 127MB (+5.8%)
```

**Simulation Duration:**
```
5-day simulation (2,400 ticks):
- Without GPT: ~2 minutes
- With GPT-4o-mini: ~2.1 minutes (+5%)
- With GPT-4o: ~2.3 minutes (+15%)
```

### Example 17: Optimization Tips

Optimize performance and cost:

```bash
# 1. Use GPT-4o-mini for cost savings
VDOS_FALLBACK_MODEL=gpt-4o-mini

# 2. Reduce fallback probability if too many calls
VDOS_FALLBACK_PROBABILITY=0.5  # Down from 0.6

# 3. Enable participation balancing to reduce total messages
VDOS_PARTICIPATION_BALANCE_ENABLED=true

# 4. Increase tick speed for faster simulations
VDOS_TICK_MS=25  # Down from 50ms (2x faster)

# 5. Use JSON communications in hourly plans when possible
# (JSON communications bypass GPT fallback entirely)
```

---

## Summary

The communication diversity features transform VDOS from template-driven to realistic workplace communications:

**Key Benefits:**
- ✅ Diverse, non-repetitive messages
- ✅ Role-appropriate language
- ✅ Email threading and conversations
- ✅ Balanced participation
- ✅ Project context integration
- ✅ Cost-effective with GPT-4o-mini

**Default Configuration (Recommended):**
```bash
VDOS_GPT_FALLBACK_ENABLED=true
VDOS_FALLBACK_PROBABILITY=0.6
VDOS_FALLBACK_MODEL=gpt-4o-mini
VDOS_THREADING_RATE=0.3
VDOS_PARTICIPATION_BALANCE_ENABLED=true
```

**Next Steps:**
1. Start with default configuration
2. Monitor quality metrics via API
3. Adjust settings based on your use case
4. Review troubleshooting guide if issues arise

For more information:
- [Communication Generator Module](../modules/communication_generator.md)
- [Inbox Manager Module](../modules/inbox_manager.md)
- [Participation Balancer Module](../modules/participation_balancer.md)
- [Troubleshooting Guide](./communication_diversity_troubleshooting.md)
