# Time Machine Replay Viewer - Design Document

**Status:** ✅ APPROVED - Ready for Implementation
**Date:** 2025-11-10
**Version:** 1.0

---

## 1. Overview

### Goal
Create a simple time-travel mechanism that allows:
- Jump to any previously generated tick
- Live feed pre-generated data to external projects via API
- Show clear indicator when in "replay mode" vs "live mode"
- Safety checks to prevent jumping beyond generated data
- Minimal UI - just jump controls and mode indicator

### Primary Use Case
**Live data feed to another project:** External systems can consume simulation data at controlled speed, jumping to specific time points as needed.

### Non-Goals (for v1)
- ❌ Fancy timeline visualization
- ❌ Continuous playback controls (VCR-style)
- ❌ Modifying past state
- ❌ Timeline branching
- ❌ Analytics/graphs

---

## 2. Approved Architecture Decisions ✅

### 2.1 UI Location
**✅ New "Replay" Tab + Dashboard Indicator**
- Add "Replay" tab in existing dashboard navigation
- Add replay mode indicator on main Dashboard tab
- Indicator shows: "🔄 REPLAY MODE - Viewing tick {N}" when in replay mode
- Simple toggle to switch between live and replay mode

### 2.2 Playback Controls
**✅ Minimal Jump-Only**
- No continuous playback controls (no play/pause/rewind buttons)
- Simple jump controls: Jump to Day/Hour/Minute
- Playback speed controlled ONLY via existing tick interval setting
- Use existing auto-tick mechanism for continuous forward movement

### 2.3 Data Loading Strategy
**✅ Hybrid Loading**
- Preload metadata on page load:
  - Max generated tick (safety boundary)
  - Total days simulated
  - Current live tick
- Stream detailed data (emails, chats) on demand when jumping
- No heavy prefetching - keep it lightweight

### 2.4 Data Priority
**✅ Emails and Chats are Most Important**
- Treat emails and chats as equivalent priority
- Plans are secondary (can be added later)
- Focus API responses on email/chat data

---

## 3. UI Design

### 3.1 Main Dashboard Indicator

```
┌────────────────────────────────────────────┐
│ Dashboard                                   │
├────────────────────────────────────────────┤
│                                             │
│ 🔄 REPLAY MODE - Viewing Day 2, 14:35      │  ← Only shown when in replay
│    [Return to Live Mode]                   │
│                                             │
│ Current Tick: 2,880 (Replay)               │
│ Max Generated: 3,547                       │
│ Auto-tick: Paused (Replay Mode)            │
│                                             │
└────────────────────────────────────────────┘
```

### 3.2 Replay Tab UI

```
┌────────────────────────────────────────────┐
│ [Dashboard] [Projects] [Replay] [Chat]     │  ← New "Replay" tab
├────────────────────────────────────────────┤
│                                             │
│ ┌─────────────────────────────────────────┐│
│ │ TIME MACHINE CONTROLS                   ││
│ │                                         ││
│ │ Current Mode: [● Live] [○ Replay]      ││
│ │                                         ││
│ │ Jump to Tick:                           ││
│ │   Day: [_2_]  Hour: [14_]  Min: [35_]  ││
│ │   Tick: [2,875_]                        ││
│ │                                         ││
│ │   [Jump to Time]  [Reset to Live]      ││
│ │                                         ││
│ │ Safety Info:                            ││
│ │   Max generated tick: 3,547 (Day 3)    ││
│ │   Current tick: 2,880                   ││
│ │   ⚠️ Cannot jump beyond Day 3           ││
│ │                                         ││
│ │ Playback Speed:                         ││
│ │   Controlled via Settings → Tick       ││
│ │   Interval (currently: 1000ms)          ││
│ └─────────────────────────────────────────┘│
│                                             │
│ ┌─────────────────────────────────────────┐│
│ │ CURRENT STATE (Tick 2,880)              ││
│ │                                         ││
│ │ [Emails] [Chats]                        ││
│ │                                         ││
│ │ Showing 15 emails at this tick...      ││
│ │                                         ││
│ └─────────────────────────────────────────┘│
└────────────────────────────────────────────┘
```

---

## 4. Core Features

### 4.1 Must-Have Features (v1)
- ✅ Jump to specific tick (with safety check)
- ✅ Jump by day/hour/minute
- ✅ Show replay mode indicator on dashboard
- ✅ Safety check: prevent jumping beyond max generated tick
- ✅ View emails at current tick
- ✅ View chats at current tick
- ✅ Toggle between live and replay mode
- ✅ Return to live mode button
- ✅ Display max generated tick info

### 4.2 Future Features (v2)
- 📊 Plans at current tick
- 🔍 Search/filter in time range
- 📈 Summary statistics
- 🏷️ Bookmarks for interesting moments
- 📥 Export time-range data

---

## 5. Data Model

### 5.1 Replay State (In-Memory)

```typescript
interface ReplayState {
  mode: 'live' | 'replay';
  current_tick: number;
  max_generated_tick: number;
  is_auto_tick_paused: boolean;
}
```

### 5.2 API Response Format

**Tick Data Response:**
```json
{
  "tick": 2880,
  "day": 2,
  "sim_time": "14:35",
  "is_replay": true,
  "data": {
    "emails": [
      {
        "id": 123,
        "sender": "jungjiwon@koreaitcom",
        "recipient": "leejungdu@example.co",
        "subject": "[Project LUMINA] 팀 미팅 요약",
        "body": "...",
        "sent_at": "2025-11-10 14:35:00"
      }
    ],
    "chats": [
      {
        "id": 456,
        "room_id": 1,
        "sender": "lee_jd",
        "body": "확인했습니다",
        "sent_at": "2025-11-10 14:35:00"
      }
    ]
  }
}
```

**Metadata Response:**
```json
{
  "max_generated_tick": 3547,
  "total_days": 3,
  "current_live_tick": 3547,
  "total_emails": 113,
  "total_chats": 243
}
```

---

## 6. API Design

### 6.1 New Endpoints

```
GET  /api/v1/replay/metadata
     Returns: Max generated tick, total days, current state

GET  /api/v1/replay/jump/{tick}
     Action: Jumps simulation to specified tick (with safety check)
     Returns: Success/failure + tick data

POST /api/v1/replay/jump
     Body: { "day": 2, "hour": 14, "minute": 35 }
     Action: Converts to tick and jumps
     Returns: Tick data at that time

GET  /api/v1/replay/current
     Returns: Data at current tick (emails, chats)

POST /api/v1/replay/mode
     Body: { "mode": "live" | "replay" }
     Action: Switches between live and replay mode

GET  /api/v1/replay/reset
     Action: Returns to live mode (current_tick = max_generated_tick)
     Returns: Success status
```

### 6.2 Safety Validation

**Before Jump:**
1. Query `SELECT MAX(tick) FROM worker_exchange_log` to get max generated tick
2. If requested_tick > max_generated_tick → return error
3. If requested_tick < 1 → return error
4. Otherwise → allow jump

---

## 7. Backend Implementation

### 7.1 New File: `replay_manager.py`

```python
class ReplayManager:
    def __init__(self, engine):
        self.engine = engine
        self.mode = 'live'

    def get_max_generated_tick(self) -> int:
        """Query database for highest tick with data."""
        # SELECT MAX(tick) FROM worker_exchange_log

    def jump_to_tick(self, tick: int) -> dict:
        """Jump to specific tick (with safety check)."""
        max_tick = self.get_max_generated_tick()
        if tick > max_tick:
            raise ValueError(f"Cannot jump to tick {tick}, max is {max_tick}")
        if tick < 1:
            raise ValueError("Tick must be >= 1")

        # Update engine's current_tick
        self.engine.set_current_tick(tick)
        self.mode = 'replay'

        return self.get_tick_data(tick)

    def get_tick_data(self, tick: int) -> dict:
        """Get emails and chats at specific tick."""
        # Query emails and chats from database

    def reset_to_live(self):
        """Return to live mode."""
        max_tick = self.get_max_generated_tick()
        self.engine.set_current_tick(max_tick)
        self.mode = 'live'
```

### 7.2 Database Queries

**Get max generated tick:**
```sql
SELECT MAX(tick) FROM worker_exchange_log;
```

**Get emails at tick:**
```sql
SELECT e.* FROM emails e
WHERE e.sent_at >= (
  SELECT MIN(created_at) FROM worker_exchange_log WHERE tick = ?
)
AND e.sent_at <= (
  SELECT MAX(created_at) FROM worker_exchange_log WHERE tick = ?
)
ORDER BY e.sent_at;
```

**Get chats at tick:**
```sql
SELECT c.* FROM chat_messages c
WHERE c.sent_at >= (
  SELECT MIN(created_at) FROM worker_exchange_log WHERE tick = ?
)
AND c.sent_at <= (
  SELECT MAX(created_at) FROM worker_exchange_log WHERE tick = ?
)
ORDER BY c.sent_at;
```

---

## 8. Frontend Implementation

### 8.1 New File: `replay.html`

```html
<div id="replay-tab">
  <div class="replay-controls">
    <h3>Time Machine Controls</h3>

    <div class="mode-toggle">
      <label>
        <input type="radio" name="mode" value="live" checked>
        Live Mode
      </label>
      <label>
        <input type="radio" name="mode" value="replay">
        Replay Mode
      </label>
    </div>

    <div class="jump-controls">
      <label>Day: <input type="number" id="jump-day" min="1"></label>
      <label>Hour: <input type="number" id="jump-hour" min="0" max="23"></label>
      <label>Minute: <input type="number" id="jump-minute" min="0" max="59"></label>
      <button id="btn-jump">Jump to Time</button>
    </div>

    <div class="safety-info">
      <p>Max generated tick: <span id="max-tick">-</span></p>
      <p>Current tick: <span id="current-tick">-</span></p>
    </div>

    <button id="btn-reset">Reset to Live Mode</button>
  </div>

  <div class="current-state">
    <h3>Current State</h3>
    <div class="tabs">
      <button class="tab active" data-tab="emails">Emails</button>
      <button class="tab" data-tab="chats">Chats</button>
    </div>
    <div id="state-content">
      <!-- Emails/chats will load here -->
    </div>
  </div>
</div>
```

### 8.2 Dashboard Indicator

```javascript
// Add to dashboard.js
function updateReplayIndicator() {
  fetch('/api/v1/replay/metadata')
    .then(r => r.json())
    .then(data => {
      if (data.is_replay) {
        showIndicator(`🔄 REPLAY MODE - Viewing tick ${data.current_tick}`);
      } else {
        hideIndicator();
      }
    });
}
```

---

## 9. Implementation Plan

### Phase 1: Backend Core ✅ COMPLETE
- [x] Design approved
- [x] Create `replay_manager.py`
- [x] Implement `get_max_generated_tick()`
- [x] Implement `jump_to_tick()` with safety check
- [x] Implement `get_tick_data()` queries
- [x] Add `set_current_tick()` method to engine
- [x] Unit tests for replay manager (tick conversion verified)

### Phase 2: API Endpoints ✅ COMPLETE
- [x] Add `/api/v1/replay/metadata` endpoint
- [x] Add `/api/v1/replay/jump/{tick}` endpoint (GET)
- [x] Add `/api/v1/replay/jump` endpoint (POST with day/hour/minute)
- [x] Add `/api/v1/replay/current` endpoint
- [x] Add `/api/v1/replay/mode` endpoint
- [x] Add `/api/v1/replay/reset` endpoint
- [x] Integration tests for API (test_replay_api.py)

### Phase 3: Frontend UI
- [ ] Create replay tab HTML
- [ ] Add replay controls (jump, reset)
- [ ] Add mode toggle
- [ ] Add dashboard indicator
- [ ] Wire up API calls
- [ ] Test UI interactions

### Phase 4: Polish & Testing
- [ ] Safety validation edge cases
- [ ] Error handling and user feedback
- [ ] Performance testing with large datasets
- [ ] Documentation
- [ ] User acceptance testing

---

## 10. Safety Requirements

### 10.1 Critical Safety Checks

1. **Max Tick Validation:**
   - MUST query database for actual max tick before every jump
   - MUST reject jumps beyond max tick with clear error message
   - MUST display max tick in UI at all times

2. **Tick Range Validation:**
   - MUST reject tick < 1
   - MUST reject tick > max_generated_tick
   - MUST validate day/hour/minute inputs convert to valid tick

3. **Mode Indicator:**
   - MUST show replay indicator when current_tick < max_generated_tick
   - MUST hide indicator when in live mode
   - MUST persist indicator across page refreshes

4. **External API Safety:**
   - MUST return `is_replay` flag in all API responses
   - MUST include max_generated_tick in metadata
   - MUST return error for invalid jump requests

---

## 11. External Integration

### 11.1 API Consumer Example

**External project can consume data like this:**

```python
import requests

base_url = "http://localhost:8050/api/v1"

# Get metadata
meta = requests.get(f"{base_url}/replay/metadata").json()
print(f"Max tick: {meta['max_generated_tick']}")

# Jump to Day 2
response = requests.post(
    f"{base_url}/replay/jump",
    json={"day": 2, "hour": 14, "minute": 0}
)
data = response.json()

# Get emails and chats at this tick
for email in data['data']['emails']:
    print(f"Email: {email['subject']}")

for chat in data['data']['chats']:
    print(f"Chat: {chat['body']}")

# Advance tick-by-tick
for tick in range(current_tick, max_tick, 10):
    data = requests.get(f"{base_url}/replay/jump/{tick}").json()
    process_data(data)
```

---

## 12. Testing Checklist

### 12.1 Backend Tests
- [ ] Test `get_max_generated_tick()` returns correct value
- [ ] Test jump to valid tick succeeds
- [ ] Test jump beyond max tick fails with error
- [ ] Test jump to tick < 1 fails with error
- [ ] Test `get_tick_data()` returns correct emails
- [ ] Test `get_tick_data()` returns correct chats
- [ ] Test day/hour/minute to tick conversion

### 12.2 API Tests
- [ ] Test `/replay/metadata` returns correct data
- [ ] Test `/replay/jump/{tick}` with valid tick
- [ ] Test `/replay/jump/{tick}` with invalid tick
- [ ] Test `/replay/jump` POST with day/hour/minute
- [ ] Test `/replay/reset` returns to live mode
- [ ] Test replay mode persists across requests

### 12.3 UI Tests
- [ ] Test jump button triggers API call
- [ ] Test safety warning shows for invalid jump
- [ ] Test dashboard indicator appears in replay mode
- [ ] Test dashboard indicator disappears in live mode
- [ ] Test reset button returns to live
- [ ] Test mode toggle switches correctly

---

## 13. Success Criteria

✅ **Feature is successful when:**

1. User can jump to any previously generated tick
2. Safety check prevents jumping beyond max tick
3. Dashboard clearly shows when in replay mode
4. External projects can consume tick data via API
5. Playback speed is controlled via tick interval
6. Emails and chats are correctly retrieved for any tick
7. Reset button returns to live mode instantly
8. No performance degradation on large datasets (10k+ ticks)

---

**Ready to start implementation? Let's build it! 🚀**
