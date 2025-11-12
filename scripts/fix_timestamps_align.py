#!/usr/bin/env python3
import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


def parse_iso(ts: str) -> datetime:
    """Parse common timestamp formats into aware UTC datetime when possible.

    Accepts:
    - 'YYYY-MM-DDTHH:MM:SS(.us)+00:00' (ISO)
    - 'YYYY-MM-DD HH:MM:SS(.us)' (assumed UTC)
    - trailing 'Z' forms treated as UTC
    """
    s = (ts or "").strip()
    if not s:
        raise ValueError("empty timestamp")
    # Normalize Z to +00:00
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        # try replacing space with T
        s2 = s.replace(" ", "T")
        dt = datetime.fromisoformat(s2)

    # If naive, assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fmt_utc(dt: datetime) -> str:
    """Format datetime as ISO string with +00:00 offset."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("Z", "+00:00")


def in_hours(local_dt: datetime, work_hours: str) -> bool:
    """Return True if local datetime's time falls within work_hours ("HH:MM-HH:MM")."""
    try:
        start_s, end_s = work_hours.split("-")
        sh, sm = map(int, start_s.split(":"))
        eh, em = map(int, end_s.split(":"))
    except Exception:
        sh, sm, eh, em = 9, 0, 17, 0
    t = local_dt.time()
    return (t.hour, t.minute) >= (sh, sm) and (t.hour, t.minute) < (eh, em)


def tz_offset_for(tz_name: str) -> int:
    """Return integer hour offset from UTC for a timezone name at current time.
    Fallback for common zones.
    """
    if ZoneInfo is not None:
        try:
            now = datetime.now(timezone.utc)
            # Convert now UTC to local tz and compute offset hours
            loc = now.astimezone(ZoneInfo(tz_name))
            off = (loc.utcoffset() or timedelta()).total_seconds() / 3600.0
            return int(round(off))
        except Exception:
            pass
    # Fallback mapping
    fallback = {
        "Asia/Seoul": 9,
        "UTC": 0,
        "Etc/UTC": 0,
        "Europe/London": 0,  # ignoring DST
        "America/New_York": -5,  # ignoring DST
        "America/Los_Angeles": -8,  # ignoring DST
    }
    return fallback.get(tz_name, 0)


def collect_people(con: sqlite3.Connection) -> Tuple[Dict[int, dict], Dict[str, int], Dict[str, int]]:
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, name, chat_handle, email_address, work_hours, timezone FROM people"
    ).fetchall()
    people: Dict[int, dict] = {}
    by_chat: Dict[str, int] = {}
    by_email: Dict[str, int] = {}
    for r in rows:
        d = dict(r)
        people[d["id"]] = d
        if d.get("chat_handle"):
            by_chat[(d["chat_handle"] or "").lower()] = d["id"]
        if d.get("email_address"):
            by_email[(d["email_address"] or "").lower()] = d["id"]
    return people, by_chat, by_email


def compute_best_offset(ts_list: List[str], work_hours: str, tz_name: str) -> Tuple[int, int]:
    """Search -12..+12 hour offsets to maximize in-hours messages.

    Returns (best_offset_hours, score)
    """
    best_off = 0
    best_score = -1
    tz_off = tz_offset_for(tz_name)
    for off in range(-12, 13):
        good = 0
        for ts in ts_list:
            try:
                dt = parse_iso(ts)
            except Exception:
                continue
            # Apply UTC shift (fix) then view in local tz
            dt_shifted = dt + timedelta(hours=off)
            dt_local = dt_shifted + timedelta(hours=tz_off)
            if in_hours(dt_local, work_hours):
                good += 1
        if good > best_score:
            best_score = good
            best_off = off
    return best_off, best_score


def plan_offsets(
    con: sqlite3.Connection,
    people: Dict[int, dict],
    by_chat: Dict[str, int],
    by_email: Dict[str, int],
    mode: str,
    uniform_offset: int,
) -> Tuple[Dict[int, int], List[Tuple[str, int]], List[Tuple[str, int]]]:
    con.row_factory = sqlite3.Row
    chat_rows = con.execute("SELECT id, sender, sent_at FROM chat_messages").fetchall()
    email_rows = con.execute("SELECT id, sender, sent_at FROM emails").fetchall()

    # Gather timestamps per person
    ts_by_pid: Dict[int, List[str]] = {pid: [] for pid in people}
    for r in chat_rows:
        pid = by_chat.get((r["sender"] or "").lower())
        if pid is not None and r["sent_at"]:
            ts_by_pid[pid].append(r["sent_at"])
    for r in email_rows:
        pid = by_email.get((r["sender"] or "").lower())
        if pid is not None and r["sent_at"]:
            ts_by_pid[pid].append(r["sent_at"])

    # Decide offset per person
    per_person_offset: Dict[int, int] = {}
    for pid, pdata in people.items():
        ts_list = ts_by_pid.get(pid) or []
        if not ts_list:
            per_person_offset[pid] = 0
            continue
        if mode == "uniform":
            per_person_offset[pid] = uniform_offset
        else:
            off, _ = compute_best_offset(ts_list, pdata.get("work_hours") or "09:00-17:00", pdata.get("timezone") or "UTC")
            per_person_offset[pid] = off

    # Build updates
    chat_updates: List[Tuple[str, int]] = []
    for r in chat_rows:
        pid = by_chat.get((r["sender"] or "").lower())
        if pid is None:
            continue
        off = per_person_offset.get(pid, 0)
        if off == 0:
            continue
        try:
            dt = parse_iso(r["sent_at"]) + timedelta(hours=off)
            chat_updates.append((fmt_utc(dt), r["id"]))
        except Exception:
            continue

    email_updates: List[Tuple[str, int]] = []
    for r in email_rows:
        pid = by_email.get((r["sender"] or "").lower())
        if pid is None:
            continue
        off = per_person_offset.get(pid, 0)
        if off == 0:
            continue
        try:
            dt = parse_iso(r["sent_at"]) + timedelta(hours=off)
            email_updates.append((fmt_utc(dt), r["id"]))
        except Exception:
            continue

    return per_person_offset, chat_updates, email_updates


def score_projection(
    con: sqlite3.Connection,
    people: Dict[int, dict],
    by_chat: Dict[str, int],
    by_email: Dict[str, int],
    per_person_offset: Dict[int, int],
) -> dict:
    con.row_factory = sqlite3.Row
    chat_rows = con.execute("SELECT sender, sent_at FROM chat_messages").fetchall()
    email_rows = con.execute("SELECT sender, sent_at FROM emails").fetchall()

    def score(rows, lookup):
        total = 0
        known = 0
        outside = 0
        for r in rows:
            total += 1
            pid = lookup.get((r["sender"] or "").lower())
            if pid is None:
                continue
            known += 1
            off = per_person_offset.get(pid, 0)
            try:
                dt = parse_iso(r["sent_at"]) + timedelta(hours=off)
            except Exception:
                continue
            tz_name = people[pid].get("timezone") or "UTC"
            tz_off = tz_offset_for(tz_name)
            dt_local = dt + timedelta(hours=tz_off)
            if not in_hours(dt_local, people[pid].get("work_hours") or "09:00-17:00"):
                outside += 1
        return {"total": total, "known": known, "projected_outside": outside}

    return {
        "chat": score(chat_rows, by_chat),
        "email": score(email_rows, by_email),
    }


def apply_updates(con: sqlite3.Connection, chat_updates: List[Tuple[str, int]], email_updates: List[Tuple[str, int]]):
    cur = con.cursor()
    if chat_updates:
        cur.executemany("UPDATE chat_messages SET sent_at=? WHERE id=?", chat_updates)
    if email_updates:
        cur.executemany("UPDATE emails SET sent_at=? WHERE id=?", email_updates)
    con.commit()


def main():
    ap = argparse.ArgumentParser(description="Fix misaligned message timestamps to match local work hours")
    ap.add_argument("--db", default="src/virtualoffice/vdos.db", help="Path to SQLite DB")
    ap.add_argument("--mode", choices=["auto", "uniform"], default="auto", help="Offset selection mode")
    ap.add_argument("--uniform-offset", type=int, default=9, help="Uniform hour offset when mode=uniform")
    ap.add_argument("--apply", action="store_true", help="Apply updates (otherwise dry-run)")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)

    people, by_chat, by_email = collect_people(con)
    per_person_offset, chat_updates, email_updates = plan_offsets(
        con, people, by_chat, by_email, args.mode, args.uniform_offset
    )

    projection = score_projection(con, people, by_chat, by_email, per_person_offset)

    report = {
        "mode": args.mode,
        "uniform_offset": args.uniform_offset,
        "per_person_offset": per_person_offset,
        "planned_chat_updates": len(chat_updates),
        "planned_email_updates": len(email_updates),
        "projection": projection,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.apply:
        apply_updates(con, chat_updates, email_updates)
        print("Applied updates.")
    else:
        print("Dry-run only. No changes applied.")


if __name__ == "__main__":
    main()

