#!/usr/bin/env python3
"""
Analyze duplicate email issue by checking worker plans for duplicate scheduled communications
"""
import sqlite3
import re
from pathlib import Path
from collections import Counter

# Find most recent simulation DB
sim_outputs = Path("simulation_output")
if not sim_outputs.exists():
    print("No simulation_output directory found")
    exit(1)

# Get most recent simulation directory
recent_dirs = sorted([d for d in sim_outputs.iterdir() if d.is_dir()], key=lambda x: x.name, reverse=True)
if not recent_dirs:
    print("No simulation directories found")
    exit(1)

recent_sim = recent_dirs[0]
db_path = recent_sim / "vdos.db"

if not db_path.exists():
    print(f"No database found in {recent_sim}")
    exit(1)

print(f"Analyzing: {recent_sim.name}")
print(f"Database: {db_path}\n")

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Get worker plans
plans = conn.execute("""
    SELECT p.id, p.person_id, p.tick, p.plan_type, p.content, pe.name, pe.email_address
    FROM worker_plans p
    JOIN people pe ON p.person_id = pe.id
    WHERE p.plan_type = 'hourly'
    ORDER BY p.person_id, p.tick
""").fetchall()

print(f"Total hourly plans: {len(plans)}\n")

# Parse scheduled communications from each plan
email_re = re.compile(
    r"^Email\s+at\s+(\d{2}:\d{2})\s+to\s+([^:]+?)"
    r"(?:\s+cc\s+([^:]+?))?"
    r"(?:\s+bcc\s+([^:]+?))?\s*:\s*(.*)$",
    re.I | re.MULTILINE,
)

# Track: (person_id, tick, email_content) -> count
scheduled_emails = []
person_tick_emails = {}

for plan in plans:
    person_id = plan['person_id']
    tick = plan['tick']
    content = plan['content']
    name = plan['name']

    # Find "Scheduled Communications" section
    if "Scheduled Communications" not in content:
        continue

    lines = content.split('\n')
    in_section = False
    comm_lines = []

    for line in lines:
        if "Scheduled Communications" in line:
            in_section = True
            continue
        if in_section:
            if line.strip() and not line.strip().startswith(('#', '**', '-', '*')):
                if line.strip().startswith(('Email at', 'Chat at', 'Reply at')):
                    comm_lines.append(line.strip())

    # Parse emails
    for line in comm_lines:
        m = email_re.match(line)
        if m:
            time = m.group(1)
            to = m.group(2).strip()
            subject_body = m.group(5).strip()

            # Create a key for this email
            email_key = (person_id, tick, to, subject_body)
            scheduled_emails.append(email_key)

            # Track per person per tick
            if person_id not in person_tick_emails:
                person_tick_emails[person_id] = {}
            if tick not in person_tick_emails[person_id]:
                person_tick_emails[person_id][tick] = []
            person_tick_emails[person_id][tick].append((to, subject_body))

# Count duplicates
counter = Counter(scheduled_emails)
duplicates = [(k, count) for k, count in counter.items() if count > 1]

print(f"Scheduled emails analysis:")
print(f"  Total scheduled emails: {len(scheduled_emails)}")
print(f"  Unique emails: {len(counter)}")
print(f"  Duplicate patterns: {len(duplicates)}\n")

if duplicates:
    print(f"Top 10 duplicate patterns:")
    for (person_id, tick, to, subject_body), count in sorted(duplicates, key=lambda x: x[1], reverse=True)[:10]:
        person_name = conn.execute("SELECT name FROM people WHERE id = ?", (person_id,)).fetchone()['name']
        print(f"  [{count}x] {person_name} @ tick {tick} to {to[:30]}")
        print(f"       Subject/Body: {subject_body[:80]}...")
        print()

# Check if same email appears in multiple hourly plans for same person/tick
print("\nChecking if duplicates come from multiple planning calls:")
duplicate_planning_calls = 0
for person_id, ticks in person_tick_emails.items():
    for tick, emails in ticks.items():
        email_counter = Counter(emails)
        for email, count in email_counter.items():
            if count > 1:
                duplicate_planning_calls += 1
                person_name = conn.execute("SELECT name FROM people WHERE id = ?", (person_id,)).fetchone()['name']
                print(f"  {person_name} scheduled same email {count} times at tick {tick}")

if duplicate_planning_calls == 0:
    print("  No duplicates found within individual planning calls")
    print("  => Duplicates likely come from deduplication not being applied correctly")
else:
    print(f"\n  Found {duplicate_planning_calls} cases of duplicate scheduling in same planning call")
    print("  => Need to add deduplication to _ingest_scheduled_comms()")

conn.close()
