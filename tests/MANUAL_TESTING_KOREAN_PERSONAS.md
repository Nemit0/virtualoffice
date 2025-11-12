# Manual Testing Guide: Korean Personas with Communication Style Filter

This guide provides step-by-step instructions for manually testing the communication style filter with Korean personas to verify style consistency, filter toggle functionality, and metrics tracking accuracy.

## Prerequisites

- VDOS application running with all services started
- OpenAI API key configured in `.env` file
- Dashboard accessible at `http://127.0.0.1:8015`

## Test Scenario 1: Create Korean Persona with Distinct Communication Style

### Objective
Verify that Korean personas can be created with AI-generated style examples that reflect distinct communication styles.

### Steps

1. **Open Dashboard**
   - Navigate to `http://127.0.0.1:8015` in your browser
   - Verify all services are running (green status indicators)

2. **Create New Korean Persona**
   - Click "Add Person" button
   - Fill in persona details:
     - Name: `김민수`
     - Role: `시니어 소프트웨어 엔지니어`
     - Email: `minsu.kim@vdos.local`
     - Chat Handle: `minsu_kim`
     - Personality: `["분석적", "협력적", "꼼꼼한"]`
     - Skills: `["Python", "시스템 설계", "코드 리뷰"]`
     - Communication Style: `기술적이고 명확하며, 공손하지만 간결한 스타일`

3. **Generate Style Examples**
   - Click "Generate with AI" button in the style examples section
   - Wait for GPT-4o to generate 5 examples (3 email, 2 chat)
   - Verify examples are in Korean
   - Verify examples reflect the specified communication style

4. **Review Generated Examples**
   - Check that email examples are formal and technical
   - Check that chat examples are more concise but still professional
   - Verify all examples are at least 20 characters long
   - Verify Korean characters are present in all examples

5. **Save Persona**
   - Click "Save" button
   - Verify persona appears in the persona list
   - Verify style examples are saved

### Expected Results

- ✅ Persona created successfully with Korean name and role
- ✅ 5 style examples generated (3 email, 2 chat)
- ✅ All examples in Korean language
- ✅ Examples reflect "technical and clear" communication style
- ✅ Examples show appropriate formality levels

### Verification Queries

```sql
-- Check persona was created
SELECT id, name, role, communication_style FROM people WHERE name = '김민수';

-- Check style examples were saved
SELECT style_examples FROM people WHERE name = '김민수';

-- Verify filter is enabled
SELECT style_filter_enabled FROM people WHERE name = '김민수';
```

---

## Test Scenario 2: Generate Multiple Messages and Verify Style Consistency

### Objective
Verify that the style filter consistently applies the persona's communication style across multiple messages.

### Steps

1. **Start Simulation**
   - Create a simple project with the Korean persona
   - Configure simulation for 1 business day
   - Enable auto-tick with 50ms interval
   - Start simulation

2. **Monitor Message Generation**
   - Watch the simulation logs for email and chat messages
   - Note the original message content (if logged)
   - Note the styled message content

3. **Collect Sample Messages**
   - Let simulation run for at least 2 hours (simulated time)
   - Collect at least 5 email messages
   - Collect at least 5 chat messages

4. **Analyze Style Consistency**
   - Review each message for:
     - Korean language usage
     - Technical terminology appropriate to role
     - Consistent formality level
     - Personality traits evident in writing
     - Similar sentence structure and tone

5. **Compare with Style Examples**
   - Open persona dialog and review style examples
   - Compare generated messages with examples
   - Verify messages match the style demonstrated in examples

### Expected Results

- ✅ All messages generated in Korean
- ✅ Consistent technical vocabulary across messages
- ✅ Appropriate formality level maintained
- ✅ Personality traits ("analytical", "collaborative") evident
- ✅ Messages feel like they're from the same person

### Sample Analysis Checklist

For each message, verify:
- [ ] Uses Korean language
- [ ] Matches formality level of examples
- [ ] Includes technical terms when appropriate
- [ ] Shows personality traits
- [ ] Maintains consistent tone

---

## Test Scenario 3: Test Filter Toggle During Active Simulation

### Objective
Verify that the filter can be toggled on/off during an active simulation and that the change takes effect immediately.

### Steps

1. **Start Simulation with Filter Enabled**
   - Create project with Korean persona
   - Verify filter toggle is ON in dashboard
   - Start simulation
   - Let run for 1 hour (simulated time)

2. **Collect Baseline Messages**
   - Note 3-5 messages generated with filter enabled
   - Observe the styled, personality-rich messages

3. **Disable Filter Mid-Simulation**
   - Click filter toggle to OFF
   - Verify status changes to "Disabled"
   - Continue simulation without restarting

4. **Collect Messages with Filter Disabled**
   - Note next 3-5 messages generated
   - Observe the plain, unfiltered messages

5. **Re-enable Filter**
   - Click filter toggle to ON
   - Verify status changes to "Enabled"
   - Continue simulation

6. **Collect Messages with Filter Re-enabled**
   - Note next 3-5 messages generated
   - Verify styled messages resume

7. **Compare Message Sets**
   - Compare filtered vs unfiltered messages
   - Verify clear difference in style and personality

### Expected Results

- ✅ Filter toggle updates immediately without restart
- ✅ Filtered messages show distinct personality and style
- ✅ Unfiltered messages are plain and generic
- ✅ Re-enabling filter restores styled messages
- ✅ No errors or crashes during toggle

### Comparison Table

| Aspect | Filter Enabled | Filter Disabled | Filter Re-enabled |
|--------|---------------|-----------------|-------------------|
| Language | Korean | Korean | Korean |
| Personality | Strong | Minimal | Strong |
| Formality | Consistent | Generic | Consistent |
| Technical Terms | Appropriate | Basic | Appropriate |
| Tone | Distinctive | Neutral | Distinctive |

---

## Test Scenario 4: Verify Metrics Tracking Accuracy

### Objective
Verify that the filter metrics accurately track transformations, token usage, latency, and costs.

### Steps

1. **Reset Metrics**
   - Start fresh simulation or clear database
   - Verify metrics display shows zeros

2. **Run Simulation with Known Message Count**
   - Configure simulation for 2 hours (simulated time)
   - Estimate expected message count (e.g., 10 emails, 15 chats)
   - Start simulation with filter enabled

3. **Monitor Metrics in Real-Time**
   - Refresh dashboard periodically
   - Watch transformation count increase
   - Note token usage accumulation
   - Observe average latency

4. **Verify Transformation Count**
   - Count actual messages sent (from logs or database)
   - Compare with metrics display
   - Verify counts match

5. **Verify Token Usage**
   - Check metrics display for total tokens
   - Verify tokens > 0 for each transformation
   - Verify reasonable token counts (50-150 per message)

6. **Verify Latency Tracking**
   - Check average latency in metrics
   - Verify latency is reasonable (< 5 seconds)
   - Check for any outliers or errors

7. **Verify Cost Estimation**
   - Check estimated cost in metrics
   - Calculate expected cost: (tokens / 1,000,000) × $6.25
   - Verify calculation is accurate

8. **Check Persona-Specific Metrics**
   - Open persona dialog
   - View metrics for specific persona
   - Verify counts match global metrics for that persona

### Expected Results

- ✅ Transformation count matches actual message count
- ✅ Token usage is tracked for each transformation
- ✅ Average latency is reasonable (< 2 seconds typical)
- ✅ Cost estimation is accurate
- ✅ Persona-specific metrics are correct
- ✅ Metrics update in real-time

### Metrics Verification Queries

```sql
-- Check total transformations
SELECT COUNT(*) FROM style_filter_metrics;

-- Check transformations by message type
SELECT message_type, COUNT(*) 
FROM style_filter_metrics 
GROUP BY message_type;

-- Check total tokens used
SELECT SUM(tokens_used) FROM style_filter_metrics;

-- Check average latency
SELECT AVG(latency_ms) FROM style_filter_metrics;

-- Check success rate
SELECT 
    COUNT(*) as total,
    SUM(success) as successful,
    (SUM(success) * 100.0 / COUNT(*)) as success_rate
FROM style_filter_metrics;

-- Check persona-specific metrics
SELECT 
    persona_id,
    COUNT(*) as transformations,
    SUM(tokens_used) as total_tokens,
    AVG(latency_ms) as avg_latency
FROM style_filter_metrics
GROUP BY persona_id;
```

---

## Test Scenario 5: Test Different Korean Persona Types

### Objective
Verify that the filter works correctly with different Korean persona types (manager, engineer, designer, etc.) and produces appropriately different styles.

### Steps

1. **Create Multiple Korean Personas**
   
   **Persona 1: Manager**
   - Name: `박지영`
   - Role: `프로젝트 매니저`
   - Communication Style: `리더십 있고 동기부여적이며, 명확한 지시를 제공`
   
   **Persona 2: Junior Engineer**
   - Name: `이준호`
   - Role: `주니어 개발자`
   - Communication Style: `공손하고 배우려는 자세, 질문이 많음`
   
   **Persona 3: Designer**
   - Name: `최수진`
   - Role: `UX 디자이너`
   - Communication Style: `창의적이고 사용자 중심적, 시각적 설명 선호`

2. **Generate Style Examples for Each**
   - Use AI generation for all three personas
   - Review examples to ensure they reflect different styles

3. **Run Simulation with All Three**
   - Create project with all three personas
   - Run simulation for 4 hours (simulated time)
   - Collect messages from each persona

4. **Compare Communication Styles**
   - Analyze manager's messages: leadership, direction-giving
   - Analyze junior's messages: questions, politeness, learning
   - Analyze designer's messages: creativity, user focus

5. **Verify Style Differentiation**
   - Confirm each persona has distinct voice
   - Verify styles match their roles and personalities
   - Check that filter maintains consistency per persona

### Expected Results

- ✅ Each persona has distinct communication style
- ✅ Manager messages show leadership and clarity
- ✅ Junior messages show politeness and questions
- ✅ Designer messages show creativity and user focus
- ✅ Styles remain consistent within each persona
- ✅ Styles are clearly different between personas

---

## Test Scenario 6: Test Filter with Mixed Korean-English Content

### Objective
Verify that the filter handles mixed Korean-English content appropriately (common in technical communications).

### Steps

1. **Create Bilingual Persona**
   - Name: `강태희`
   - Role: `테크 리드`
   - Communication Style: `기술적 용어는 영어로, 설명은 한국어로 사용`
   - Generate style examples that mix Korean and English

2. **Review Generated Examples**
   - Verify examples contain both Korean and English
   - Check that technical terms are in English
   - Check that explanations are in Korean

3. **Run Simulation**
   - Generate messages with technical content
   - Verify mixed language usage is maintained
   - Check that filter preserves technical English terms

4. **Analyze Message Quality**
   - Verify technical terms remain in English
   - Verify Korean grammar is correct
   - Verify natural code-switching between languages

### Expected Results

- ✅ Style examples contain mixed Korean-English
- ✅ Technical terms preserved in English
- ✅ Korean explanations are natural
- ✅ Code-switching is appropriate and natural
- ✅ Filter maintains bilingual style consistently

---

## Test Scenario 7: Performance and Error Handling

### Objective
Verify that the filter performs well under load and handles errors gracefully.

### Steps

1. **Test High-Volume Scenario**
   - Create 5 Korean personas
   - Run simulation with high message frequency
   - Monitor metrics for performance issues

2. **Check Latency Under Load**
   - Verify average latency stays < 2 seconds
   - Check for any latency spikes > 5 seconds
   - Monitor for timeout errors

3. **Test API Failure Handling**
   - Temporarily disable OpenAI API (invalid key)
   - Run simulation
   - Verify fallback to original messages
   - Check that simulation continues without crashing

4. **Test Network Issues**
   - Simulate network latency
   - Verify retry logic works
   - Check error logging

5. **Verify Error Recovery**
   - Re-enable API
   - Verify filter resumes normal operation
   - Check that no data was lost

### Expected Results

- ✅ Filter handles high message volume
- ✅ Latency remains acceptable under load
- ✅ API failures don't crash simulation
- ✅ Fallback to original messages works
- ✅ Errors are logged appropriately
- ✅ Filter recovers after errors

---

## Reporting Results

After completing manual testing, document your findings:

### Test Summary Template

```markdown
## Korean Persona Style Filter - Manual Test Results

**Test Date:** [Date]
**Tester:** [Name]
**VDOS Version:** [Version]

### Scenario 1: Create Korean Persona
- Status: ✅ Pass / ❌ Fail
- Notes: [Any observations]

### Scenario 2: Style Consistency
- Status: ✅ Pass / ❌ Fail
- Sample Messages: [Include 2-3 examples]
- Notes: [Observations about consistency]

### Scenario 3: Filter Toggle
- Status: ✅ Pass / ❌ Fail
- Notes: [Toggle behavior observations]

### Scenario 4: Metrics Accuracy
- Status: ✅ Pass / ❌ Fail
- Metrics Data: [Include key metrics]
- Notes: [Accuracy observations]

### Scenario 5: Different Persona Types
- Status: ✅ Pass / ❌ Fail
- Notes: [Style differentiation observations]

### Scenario 6: Mixed Language
- Status: ✅ Pass / ❌ Fail
- Notes: [Bilingual handling observations]

### Scenario 7: Performance & Errors
- Status: ✅ Pass / ❌ Fail
- Performance Data: [Latency, throughput]
- Notes: [Error handling observations]

### Issues Found
1. [Issue description]
2. [Issue description]

### Recommendations
1. [Recommendation]
2. [Recommendation]
```

---

## Troubleshooting

### Issue: Style examples not generating
- **Check:** OpenAI API key is configured
- **Check:** Internet connection is working
- **Check:** API key has sufficient credits
- **Solution:** Verify `.env` file has `OPENAI_API_KEY` set

### Issue: Messages not being filtered
- **Check:** Filter toggle is enabled
- **Check:** Persona has style examples
- **Check:** Persona filter is enabled
- **Solution:** Verify filter configuration in database

### Issue: Metrics not updating
- **Check:** Metrics batch size setting
- **Check:** Database connection
- **Solution:** Manually flush metrics or restart simulation

### Issue: Korean characters displaying incorrectly
- **Check:** Database encoding (should be UTF-8)
- **Check:** Browser encoding
- **Solution:** Ensure UTF-8 encoding throughout stack

---

## Success Criteria

The manual testing is considered successful if:

1. ✅ Korean personas can be created with AI-generated style examples
2. ✅ Generated messages consistently reflect persona's communication style
3. ✅ Filter toggle works during active simulation
4. ✅ Metrics accurately track transformations, tokens, and costs
5. ✅ Different persona types produce distinctly different styles
6. ✅ Mixed Korean-English content is handled appropriately
7. ✅ Filter performs well under load and handles errors gracefully
8. ✅ No crashes or data loss during testing
9. ✅ User experience is smooth and intuitive
10. ✅ Documentation is clear and accurate

---

## Additional Notes

- Save screenshots of key UI states for documentation
- Record sample messages for future reference
- Document any unexpected behavior
- Note any performance bottlenecks
- Suggest UI/UX improvements based on testing experience
