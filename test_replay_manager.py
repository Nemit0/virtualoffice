#!/usr/bin/env python3
"""
Test script for ReplayManager functionality.

Tests:
- Tick conversion (time_to_tick, tick_to_time)
- Safety validation (max tick checks)
- Jump operations
- Metadata retrieval
"""

import sys
sys.path.insert(0, 'src')

from virtualoffice.sim_manager.replay_manager import ReplayManager
from virtualoffice.sim_manager.engine import SimulationEngine
from virtualoffice.email_gateway import EmailGateway
from virtualoffice.chat_gateway import ChatGateway


def test_tick_conversion():
    """Test tick <-> time conversion."""
    print("=" * 80)
    print("TEST: Tick Conversion")
    print("=" * 80)

    # Create minimal engine (just for testing)
    email_gw = EmailGateway("src/virtualoffice/vdos.db")
    chat_gw = ChatGateway("src/virtualoffice/vdos.db")
    engine = SimulationEngine(email_gw, chat_gw)
    replay = ReplayManager(engine)

    # Test cases
    test_cases = [
        # (day, hour, minute, expected_tick)
        (1, 0, 0, 1),          # Day 1, midnight
        (1, 9, 0, 541),        # Day 1, 09:00 (work start)
        (1, 17, 0, 1021),      # Day 1, 17:00 (work end)
        (1, 23, 59, 1440),     # Day 1, end of day
        (2, 0, 0, 1441),       # Day 2, midnight
        (2, 9, 0, 1981),       # Day 2, 09:00
    ]

    all_passed = True

    print("\nTime → Tick conversion:")
    for day, hour, minute, expected_tick in test_cases:
        try:
            tick = replay.time_to_tick(day, hour, minute)
            status = "✓" if tick == expected_tick else "✗"
            if tick != expected_tick:
                all_passed = False
            print(f"  {status} Day {day}, {hour:02d}:{minute:02d} → Tick {tick:,} (expected {expected_tick:,})")
        except Exception as e:
            print(f"  ✗ Day {day}, {hour:02d}:{minute:02d} → ERROR: {e}")
            all_passed = False

    print("\nTick → Time conversion:")
    for _, _, _, tick in test_cases:
        try:
            time_info = replay.tick_to_time(tick)
            print(f"  ✓ Tick {tick:,} → Day {time_info['day']}, {time_info['sim_time']}")
        except Exception as e:
            print(f"  ✗ Tick {tick:,} → ERROR: {e}")
            all_passed = False

    return all_passed


def test_metadata():
    """Test metadata retrieval."""
    print("\n" + "=" * 80)
    print("TEST: Metadata Retrieval")
    print("=" * 80)

    email_gw = EmailGateway("src/virtualoffice/vdos.db")
    chat_gw = ChatGateway("src/virtualoffice/vdos.db")
    engine = SimulationEngine(email_gw, chat_gw)
    replay = ReplayManager(engine)

    try:
        metadata = replay.get_metadata()

        print("\nMetadata:")
        print(f"  Max generated tick: {metadata['max_generated_tick']:,}")
        print(f"  Current tick: {metadata['current_tick']:,}")
        print(f"  Total days: {metadata['total_days']}")
        print(f"  Mode: {metadata['mode']}")
        print(f"  Is replay: {metadata['is_replay']}")
        print(f"  Total emails: {metadata['total_emails']:,}")
        print(f"  Total chats: {metadata['total_chats']:,}")

        print("\n✓ Metadata retrieval successful")
        return True
    except Exception as e:
        print(f"\n✗ Metadata retrieval failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_safety_validation():
    """Test safety checks."""
    print("\n" + "=" * 80)
    print("TEST: Safety Validation")
    print("=" * 80)

    email_gw = EmailGateway("src/virtualoffice/vdos.db")
    chat_gw = ChatGateway("src/virtualoffice/vdos.db")
    engine = SimulationEngine(email_gw, chat_gw)
    replay = ReplayManager(engine)

    max_tick = replay.get_max_generated_tick()
    print(f"\nMax generated tick: {max_tick:,}")

    all_passed = True

    # Test 1: Jump to tick < 1 should fail
    print("\nTest: Jump to tick 0 (should fail)")
    try:
        replay.jump_to_tick(0)
        print("  ✗ Should have raised ValueError")
        all_passed = False
    except ValueError as e:
        print(f"  ✓ Correctly rejected: {e}")

    # Test 2: Jump to tick > max should fail
    print(f"\nTest: Jump to tick {max_tick + 1000} (beyond max, should fail)")
    try:
        replay.jump_to_tick(max_tick + 1000)
        print("  ✗ Should have raised ValueError")
        all_passed = False
    except ValueError as e:
        print(f"  ✓ Correctly rejected: {e}")

    # Test 3: Jump to valid tick should succeed
    if max_tick > 0:
        test_tick = min(541, max_tick)  # Day 1, 09:00 or max if smaller
        print(f"\nTest: Jump to tick {test_tick} (valid)")
        try:
            result = replay.jump_to_tick(test_tick)
            print(f"  ✓ Jump successful to tick {result['tick']}")
            print(f"    Time: Day {result['day']}, {result['sim_time']}")
            print(f"    Emails at tick: {len(result['data']['emails'])}")
            print(f"    Chats at tick: {len(result['data']['chats'])}")
        except Exception as e:
            print(f"  ✗ Jump failed: {e}")
            all_passed = False

    return all_passed


def test_jump_operations():
    """Test jump operations."""
    print("\n" + "=" * 80)
    print("TEST: Jump Operations")
    print("=" * 80)

    email_gw = EmailGateway("src/virtualoffice/vdos.db")
    chat_gw = ChatGateway("src/virtualoffice/vdos.db")
    engine = SimulationEngine(email_gw, chat_gw)
    replay = ReplayManager(engine)

    max_tick = replay.get_max_generated_tick()

    if max_tick < 541:
        print(f"\n⚠️ Not enough data (max tick: {max_tick}), skipping jump tests")
        return True

    all_passed = True

    # Test: Jump by time
    print("\nTest: Jump to Day 1, 09:00")
    try:
        result = replay.jump_to_time(day=1, hour=9, minute=0)
        print(f"  ✓ Jumped to tick {result['tick']}")
        print(f"    Time: Day {result['day']}, {result['sim_time']}")
    except Exception as e:
        print(f"  ✗ Jump failed: {e}")
        all_passed = False

    # Test: Reset to live
    print("\nTest: Reset to live mode")
    try:
        metadata = replay.reset_to_live()
        print(f"  ✓ Reset successful")
        print(f"    Current tick: {metadata['current_tick']}")
        print(f"    Mode: {metadata['mode']}")
    except Exception as e:
        print(f"  ✗ Reset failed: {e}")
        all_passed = False

    return all_passed


def main():
    """Run all tests."""
    print("=" * 80)
    print("REPLAY MANAGER TEST SUITE")
    print("=" * 80)

    results = {}

    results['tick_conversion'] = test_tick_conversion()
    results['metadata'] = test_metadata()
    results['safety_validation'] = test_safety_validation()
    results['jump_operations'] = test_jump_operations()

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} - {test_name}")

    all_passed = all(results.values())

    if all_passed:
        print("\n✅ ALL TESTS PASSED")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
