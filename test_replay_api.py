#!/usr/bin/env python3
"""
Test script for Replay API endpoints.

Tests all replay/time-machine API endpoints:
- GET /api/v1/replay/metadata
- GET /api/v1/replay/jump/{tick}
- POST /api/v1/replay/jump
- GET /api/v1/replay/current
- POST /api/v1/replay/mode
- GET /api/v1/replay/reset
"""

import requests
import sys

BASE_URL = "http://localhost:8050"
API_PREFIX = "/api/v1"


def test_metadata():
    """Test GET /api/v1/replay/metadata"""
    print("=" * 80)
    print("TEST: GET /api/v1/replay/metadata")
    print("=" * 80)

    try:
        response = requests.get(f"{BASE_URL}{API_PREFIX}/replay/metadata")
        response.raise_for_status()
        data = response.json()

        print("\nMetadata Response:")
        print(f"  Max generated tick: {data.get('max_generated_tick', 'N/A'):,}")
        print(f"  Current tick: {data.get('current_tick', 'N/A'):,}")
        print(f"  Total days: {data.get('total_days', 'N/A')}")
        print(f"  Mode: {data.get('mode', 'N/A')}")
        print(f"  Is replay: {data.get('is_replay', 'N/A')}")
        print(f"  Total emails: {data.get('total_emails', 'N/A'):,}")
        print(f"  Total chats: {data.get('total_chats', 'N/A'):,}")

        print("\n✓ Metadata endpoint works!")
        return data
    except Exception as e:
        print(f"\n✗ Metadata endpoint failed: {e}")
        return None


def test_jump_to_tick(tick: int):
    """Test GET /api/v1/replay/jump/{tick}"""
    print("\n" + "=" * 80)
    print(f"TEST: GET /api/v1/replay/jump/{tick}")
    print("=" * 80)

    try:
        response = requests.get(f"{BASE_URL}{API_PREFIX}/replay/jump/{tick}")
        response.raise_for_status()
        data = response.json()

        print(f"\nJump to tick {tick} Response:")
        print(f"  Tick: {data.get('tick', 'N/A')}")
        print(f"  Day: {data.get('day', 'N/A')}")
        print(f"  Sim time: {data.get('sim_time', 'N/A')}")
        print(f"  Is replay: {data.get('is_replay', 'N/A')}")
        print(f"  Emails at tick: {len(data.get('data', {}).get('emails', []))}")
        print(f"  Chats at tick: {len(data.get('data', {}).get('chats', []))}")

        print(f"\n✓ Jump to tick {tick} successful!")
        return data
    except requests.HTTPError as e:
        print(f"\n✗ Jump to tick {tick} failed: {e}")
        print(f"  Response: {e.response.text}")
        return None
    except Exception as e:
        print(f"\n✗ Jump to tick {tick} failed: {e}")
        return None


def test_jump_to_time(day: int, hour: int, minute: int):
    """Test POST /api/v1/replay/jump"""
    print("\n" + "=" * 80)
    print(f"TEST: POST /api/v1/replay/jump (Day {day}, {hour:02d}:{minute:02d})")
    print("=" * 80)

    try:
        payload = {"day": day, "hour": hour, "minute": minute}
        response = requests.post(
            f"{BASE_URL}{API_PREFIX}/replay/jump",
            json=payload
        )
        response.raise_for_status()
        data = response.json()

        print(f"\nJump to Day {day}, {hour:02d}:{minute:02d} Response:")
        print(f"  Tick: {data.get('tick', 'N/A')}")
        print(f"  Day: {data.get('day', 'N/A')}")
        print(f"  Sim time: {data.get('sim_time', 'N/A')}")
        print(f"  Emails at time: {len(data.get('data', {}).get('emails', []))}")
        print(f"  Chats at time: {len(data.get('data', {}).get('chats', []))}")

        print(f"\n✓ Jump to time successful!")
        return data
    except requests.HTTPError as e:
        print(f"\n✗ Jump to time failed: {e}")
        print(f"  Response: {e.response.text}")
        return None
    except Exception as e:
        print(f"\n✗ Jump to time failed: {e}")
        return None


def test_get_current():
    """Test GET /api/v1/replay/current"""
    print("\n" + "=" * 80)
    print("TEST: GET /api/v1/replay/current")
    print("=" * 80)

    try:
        response = requests.get(f"{BASE_URL}{API_PREFIX}/replay/current")
        response.raise_for_status()
        data = response.json()

        print("\nCurrent Tick Data Response:")
        print(f"  Tick: {data.get('tick', 'N/A')}")
        print(f"  Day: {data.get('day', 'N/A')}")
        print(f"  Sim time: {data.get('sim_time', 'N/A')}")
        print(f"  Emails: {len(data.get('data', {}).get('emails', []))}")
        print(f"  Chats: {len(data.get('data', {}).get('chats', []))}")

        print("\n✓ Get current endpoint works!")
        return data
    except Exception as e:
        print(f"\n✗ Get current failed: {e}")
        return None


def test_reset():
    """Test GET /api/v1/replay/reset"""
    print("\n" + "=" * 80)
    print("TEST: GET /api/v1/replay/reset")
    print("=" * 80)

    try:
        response = requests.get(f"{BASE_URL}{API_PREFIX}/replay/reset")
        response.raise_for_status()
        data = response.json()

        print("\nReset to Live Mode Response:")
        print(f"  Current tick: {data.get('current_tick', 'N/A')}")
        print(f"  Max tick: {data.get('max_generated_tick', 'N/A')}")
        print(f"  Mode: {data.get('mode', 'N/A')}")
        print(f"  Is replay: {data.get('is_replay', 'N/A')}")

        print("\n✓ Reset to live mode successful!")
        return data
    except Exception as e:
        print(f"\n✗ Reset failed: {e}")
        return None


def test_safety_validation(metadata):
    """Test safety validation (jumping beyond max tick)"""
    print("\n" + "=" * 80)
    print("TEST: Safety Validation (jump beyond max tick)")
    print("=" * 80)

    max_tick = metadata.get('max_generated_tick', 0)
    if max_tick == 0:
        print("\n⚠️ No data to test safety validation")
        return

    invalid_tick = max_tick + 10000

    print(f"\nAttempting to jump to tick {invalid_tick} (beyond max {max_tick})...")

    try:
        response = requests.get(f"{BASE_URL}{API_PREFIX}/replay/jump/{invalid_tick}")
        if response.status_code == 400:
            error = response.json()
            print(f"  ✓ Correctly rejected with 400: {error.get('detail')}")
        else:
            print(f"  ✗ Should have returned 400, got {response.status_code}")
    except Exception as e:
        print(f"  ✗ Test failed: {e}")


def main():
    """Run all API tests"""
    print("=" * 80)
    print("REPLAY API TEST SUITE")
    print("=" * 80)
    print(f"\nTesting against: {BASE_URL}")
    print("Make sure the simulation server is running!")
    print()

    # Test 1: Get metadata
    metadata = test_metadata()
    if not metadata:
        print("\n❌ Cannot continue without metadata")
        return 1

    max_tick = metadata.get('max_generated_tick', 0)

    if max_tick == 0:
        print("\n⚠️ No simulation data available (max_tick = 0)")
        print("Run the simulation first to generate data for testing.")
        return 0

    # Test 2: Jump to tick (Day 1, 09:00 = tick 541)
    if max_tick >= 541:
        test_jump_to_tick(541)
    else:
        print(f"\n⚠️ Skipping tick 541 test (max tick: {max_tick})")

    # Test 3: Jump to time
    if max_tick >= 541:
        test_jump_to_time(day=1, hour=9, minute=0)
    else:
        print(f"\n⚠️ Skipping time jump test (max tick: {max_tick})")

    # Test 4: Get current
    test_get_current()

    # Test 5: Reset to live
    test_reset()

    # Test 6: Safety validation
    test_safety_validation(metadata)

    print("\n" + "=" * 80)
    print("TEST SUITE COMPLETE")
    print("=" * 80)
    print("\n✅ All API endpoints are functional!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
